"""The form spec and the submission boundary: describe editable params, apply user edits.

Two directions across the same spec:

- [`plant_to_spec`][technoeconomics.web.spec.plant_to_spec] turns a plant (the preset
  default) into a **value-free** description of its editable parameters. The client renders
  the form from this spec and binds each input to its path in the plant dict -- the spec
  says *what* is editable and *how* (label, unit, bounds), the values travel separately.
- [`validate_edits`][technoeconomics.web.spec.validate_edits] /
  [`apply_edits`][technoeconomics.web.spec.apply_edits] are the **overlay-solve** boundary.
  The client never posts a plant; it posts ``{preset, overlay: {path: value}, enabled:
  {id: bool}}``. The server rebuilds from the *trusted* preset default and applies only
  whitelisted edits: overlay values at spec paths (any non-spec path is rejected -- structure
  is never client-controlled) and enable toggles on non-fixed components. Because the
  structure is always the preset's, there is no untrusted plant to defend against and no
  structural identity check to run.

The spec generator reads the parameter vocabulary from [`technoeconomics.model.params`][]
off each component's field annotations, recursing into dataset parameters so a `Sinusoidal`
price exposes ``price.mean``, ``price.amplitude``, ... as separate numeric inputs. It is
**total-or-error**: every author-added field must be projectable (a numeric scalar, or a
dataset recursed into) or explicitly marked ``Hidden`` -- anything else raises
[`ProjectionError`][technoeconomics.web.spec.ProjectionError] naming the field, rather than
being silently dropped.

Per-use unit and bound propagation: the unit and (scalar-branch) bounds declared on a
*component's* dataset field propagate to the dataset leaves marked
[`Magnitude`][technoeconomics.model.params.Magnitude] -- so one `Sinusoidal` class serves as
a price (EUR/MWh) in one field and a demand (MW) in another. Intrinsic dataset leaves
(``period``, ``phase``) keep their own class-level unit and bounds. Propagated bounds live
outside pydantic's reach (it cannot apply a component-field marker to a nested dataset field),
so [`validate_edits`][technoeconomics.web.spec.validate_edits] enforces every submitted value
against its spec bound; the rebuilt plant then re-runs the `Plant` validator for class-level
types and bounds.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass, fields
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
)

from annotated_types import Ge, Gt, Le, Lt

from technoeconomics.data import Dataset
from technoeconomics.model.params import Advanced, Hidden, Magnitude, Unit
from technoeconomics.model.plant import Plant

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# Framework fields on every component -- identity/serialisation/role, never editable params.
# They are special-cased (id/enabled/fixed/color surface at the component level of the spec);
# see the totality rule in the module docstring.
_FRAMEWORK_FIELDS = frozenset({"id", "enabled", "fixed", "plot_color"})


class ProjectionError(TypeError):
    """An author-added field is neither projectable (scalar/dataset) nor marked ``Hidden``."""


@dataclass(frozen=True)
class Bound:
    """One numeric bound: its value and whether it is exclusive (``Gt``/``Lt``).

    Attributes:
        value: The bounding number.
        exclusive: True for a strict bound (``Gt``/``Lt``), False for inclusive (``Ge``/``Le``).
    """

    value: float
    exclusive: bool


@dataclass(frozen=True)
class FieldSpec:
    """One editable numeric leaf of a component (possibly nested inside a dataset).

    Value-free: the current value lives in the plant dict, reached by ``path``.

    Attributes:
        path: Id-rooted dotted path into the plant dict, e.g. ``"grid.price.mean"``.
        kind: The input kind; only ``"number"`` in v1 (future kinds are additive).
        label: The path without the component id, e.g. ``"price.mean"``.
        unit: Display/edit unit, e.g. ``"EUR/MWh"``, or None if dimensionless.
        min: Lower bound, or None if unbounded below.
        max: Upper bound, or None if unbounded above.
        step: Suggested input step, or None. (No source in v1; reserved for a future marker.)
        advanced: Render under the form's "Advanced" section rather than inline.
    """

    path: str
    kind: Literal["number"]
    label: str
    unit: str | None
    min: Bound | None
    max: Bound | None
    step: float | None
    advanced: bool


@dataclass(frozen=True)
class ComponentSpec:
    """A component rendered as a fieldset: identity, an optional enable toggle, its params.

    Attributes:
        id: The component's id (the first segment of its params' paths).
        title: Human-readable heading derived from the id.
        color: The component's plot colour (a hex string), or None.
        enabled: Whether the component is currently enabled.
        fixed: If True the component may not be disabled -- the client shows no enable
            toggle and a submission cannot switch it off.
        params: The editable numeric leaves, in declaration order.
    """

    id: str
    title: str
    color: str | None
    enabled: bool
    fixed: bool
    params: list[FieldSpec]


@dataclass(frozen=True)
class _Markers:
    """The parameter markers gathered off one field's annotation."""

    unit: str | None
    min: Bound | None
    max: Bound | None
    advanced: bool
    hidden: bool
    magnitude: bool


def _gather(annotation: object) -> list[object]:
    """Collect every `Annotated` marker on `annotation`, descending through unions.

    A field's markers can sit at the field level (``Param[float, Gt(0), Unit("h")]``) or on
    the scalar branch of a scalar-or-dataset union (``Param[Scalar, Ge(0)] | ScalarDataset``),
    so both `Annotated` metadata and union arms are walked. Each field carries at most one of
    each kind, so a flat list is enough to derive the effective markers.
    """
    found: list[object] = []

    def walk(a: object) -> None:
        origin = get_origin(a)
        if origin is Annotated:
            args = get_args(a)
            found.extend(args[1:])
            walk(args[0])
        elif origin in (Union, types.UnionType):
            for arm in get_args(a):
                walk(arm)

    walk(annotation)
    return found


def _as_float(x: Any) -> float:
    """Coerce an `annotated_types` bound attribute (loosely typed) to a plain float."""
    return float(x)


def _markers(annotation: object) -> _Markers:
    """Derive the effective unit/bounds/visibility markers from a field annotation."""
    gathered = _gather(annotation)
    unit = next((m.text for m in gathered if isinstance(m, Unit)), None)
    lower: Bound | None = None
    upper: Bound | None = None
    for m in gathered:
        if isinstance(m, Ge):
            lower = Bound(_as_float(m.ge), exclusive=False)
        elif isinstance(m, Gt):
            lower = Bound(_as_float(m.gt), exclusive=True)
        elif isinstance(m, Le):
            upper = Bound(_as_float(m.le), exclusive=False)
        elif isinstance(m, Lt):
            upper = Bound(_as_float(m.lt), exclusive=True)
    return _Markers(
        unit=unit,
        min=lower,
        max=upper,
        advanced=any(m is Advanced for m in gathered),
        hidden=any(m is Hidden for m in gathered),
        magnitude=any(m is Magnitude for m in gathered),
    )


def _is_number(value: object) -> bool:
    """True for a real numeric scalar (a bool is not a number here)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _leaves(path: str, value: object, holder: _Markers) -> list[FieldSpec]:
    """Yield the field specs at or under `value`, propagating the holder's unit/bounds.

    A dataset is recursed into: its ``Magnitude`` leaves inherit the holding field's unit and
    bounds (`holder`), while its intrinsic leaves use their own class-level markers. A numeric
    value is one leaf. Anything else is unprojectable and raises.

    Args:
        path: The id-rooted path to `value` (e.g. ``"grid.price"`` or ``"grid.capex"``).
        value: The current value: a `Dataset` to recurse into, or a numeric scalar.
        holder: The markers of the component field holding `value`.

    Raises:
        ProjectionError: If `value` is neither a dataset nor a numeric scalar.
    """
    if isinstance(value, Dataset):
        hints = typing.get_type_hints(type(value), include_extras=True)
        out: list[FieldSpec] = []
        for f in fields(value):
            leaf = getattr(value, f.name)
            if not _is_number(leaf):
                raise ProjectionError(
                    f"{path}.{f.name}: dataset leaf {leaf!r} is not a number"
                )
            m = _markers(hints[f.name])
            unit = holder.unit if m.magnitude else m.unit
            lower = holder.min if m.magnitude else m.min
            upper = holder.max if m.magnitude else m.max
            out.append(
                _spec(
                    f"{path}.{f.name}",
                    unit,
                    lower,
                    upper,
                    holder.advanced or m.advanced,
                )
            )
        return out
    if _is_number(value):
        return [_spec(path, holder.unit, holder.min, holder.max, holder.advanced)]
    raise ProjectionError(
        f"{path}: {value!r} is neither a scalar nor a dataset, and is not marked Hidden"
    )


def _spec(
    path: str,
    unit: str | None,
    lower: Bound | None,
    upper: Bound | None,
    advanced: bool,
) -> FieldSpec:
    """Build a numeric `FieldSpec` for `path`."""
    return FieldSpec(
        path=path,
        kind="number",
        label=path.split(".", 1)[1],
        unit=unit,
        min=lower,
        max=upper,
        step=None,
        advanced=advanced,
    )


def plant_to_spec(plant: Plant) -> list[ComponentSpec]:
    """Describe a plant's editable parameters, one `ComponentSpec` per component.

    Args:
        plant: The plant supplying the structure (which datasets are present, which
            components are fixed).

    Returns:
        The form spec: one entry per component, each carrying its editable numeric leaves.

    Raises:
        ProjectionError: If any author-added field is neither projectable nor ``Hidden``.
    """
    specs: list[ComponentSpec] = []
    for component in plant.components:
        hints = typing.get_type_hints(type(component), include_extras=True)
        params: list[FieldSpec] = []
        for f in fields(component):
            if f.name in _FRAMEWORK_FIELDS:
                continue
            markers = _markers(hints[f.name])
            if markers.hidden:
                continue
            params.extend(
                _leaves(f"{component.id}.{f.name}", getattr(component, f.name), markers)
            )
        specs.append(
            ComponentSpec(
                id=component.id,
                title=component.id.replace("_", " ").capitalize(),
                color=str(component.plot_color) if component.plot_color else None,
                enabled=component.enabled,
                fixed=component.fixed,
                params=params,
            )
        )
    return specs


# --- The overlay-solve submission boundary -------------------------------------------------


def _components(plant: dict[str, object]) -> list[dict[str, object]]:
    """The component dicts of a plant dict (empty if the shape is malformed)."""
    components = plant.get("components")
    if not isinstance(components, list):
        return []
    return cast(
        "list[dict[str, object]]", [c for c in components if isinstance(c, dict)]
    )


def _component(plant: dict[str, object], cid: str) -> dict[str, object] | None:
    """Return the component dict with id `cid`, or None (id-rooted path resolution)."""
    for c in _components(plant):
        if c.get("id") == cid:
            return c
    return None


def _set(plant: dict[str, object], path: str, value: float) -> None:
    """Set the leaf at id-rooted `path` to `value` in place; a no-op if it does not resolve."""
    cid, *rest = path.split(".")
    node: object = _component(plant, cid)
    for k in rest[:-1]:
        if not isinstance(node, dict):
            return
        node = node.get(k)
    if isinstance(node, dict):
        cast("dict[str, object]", node)[rest[-1]] = value


def _bound_errors(field: FieldSpec, value: float) -> list[dict[str, str]]:
    """Return bound-violation errors for one numeric `value` against `field`'s spec bounds."""
    errors: list[dict[str, str]] = []
    low = field.min
    if low is not None:
        ok = value > low.value if low.exclusive else value >= low.value
        if not ok:
            op = ">" if low.exclusive else ">="
            errors.append({"path": field.path, "message": f"must be {op} {low.value}"})
    high = field.max
    if high is not None:
        ok = value < high.value if high.exclusive else value <= high.value
        if not ok:
            op = "<" if high.exclusive else "<="
            errors.append({"path": field.path, "message": f"must be {op} {high.value}"})
    return errors


def validate_edits(
    spec: Iterable[ComponentSpec],
    overlay: Mapping[str, object],
    enabled: Mapping[str, object],
) -> list[dict[str, str]]:
    """Validate a submission's edits against `spec`; return all path-addressed errors.

    An overlay entry must name an editable spec path and carry an in-bounds number; an enabled
    entry must name a component and may switch off only a non-fixed one. Rejecting non-spec
    overlay paths is what keeps structure server-controlled: the client can edit values and
    toggle optional components, nothing else.

    Args:
        spec: The named preset's form spec.
        overlay: Submitted ``{path: value}`` edits (untrusted).
        enabled: Submitted ``{component_id: bool}`` toggles (untrusted).

    Returns:
        One ``{"path", "message"}`` entry per problem, empty if the submission is clean.
    """
    spec = list(spec)
    fields_by_path = {f.path: f for c in spec for f in c.params}
    components_by_id = {c.id: c for c in spec}
    errors: list[dict[str, str]] = []
    for path, value in overlay.items():
        field = fields_by_path.get(path)
        if field is None:
            errors.append({"path": path, "message": "not an editable parameter"})
        elif not _is_number(value):
            errors.append({"path": path, "message": "must be a number"})
        else:
            errors.extend(_bound_errors(field, float(cast("float", value))))
    for cid, want in enabled.items():
        component = components_by_id.get(cid)
        if component is None:
            errors.append({"path": cid, "message": "unknown component"})
        elif not isinstance(want, bool):
            errors.append({"path": cid, "message": "must be true or false"})
        elif component.fixed and not want:
            errors.append({"path": cid, "message": "component cannot be disabled"})
    return errors


def apply_edits(
    plant: Plant, overlay: Mapping[str, object], enabled: Mapping[str, object]
) -> Plant:
    """Rebuild the preset default `plant` with a validated submission's edits applied.

    Overlays each value at its spec path and sets each component's ``enabled`` flag, operating
    on the serialised dict (datasets are frozen), then reparses through `Plant.from_dict` for a
    final class-level type/bound check. Assumes the submission passed
    [`validate_edits`][technoeconomics.web.spec.validate_edits]; unknown overlay paths are
    dropped rather than raising.

    Args:
        plant: The trusted preset default plant.
        overlay: Validated ``{path: value}`` edits.
        enabled: Validated ``{component_id: bool}`` toggles.

    Returns:
        A new plant with the edits applied.
    """
    d = plant.to_dict()
    for path, value in overlay.items():
        if _is_number(value):
            _set(d, path, float(cast("float", value)))
    for cid, want in enabled.items():
        component = _component(d, cid)
        if component is not None and isinstance(want, bool):
            component["enabled"] = want
    return Plant.from_dict(d)
