"""The form <-> plant boundary.

The form is the user's source of truth for a model's editable parameters.

- [`plant_to_form`][technoeconomics.web.forms.plant_to_form] turns a plant into the
  per-component field descriptors the page renders, recursing into dataset parameters so a
  `Sinusoidal` price exposes ``price.mean``, ``price.amplitude``, ... as separate inputs.
- [`form_to_plant`][technoeconomics.web.forms.form_to_plant] writes a submission back
  *functionally*: serialise the plant to its plain dict, overlay the submitted scalars onto
  that dict by dotted path, and rebuild. The datasets are frozen, so editing the dict (not
  the objects) is the simple path -- and it reuses the plant's `to_dict`/`from_dict`, whose
  dotted shape (e.g. ``grid.price.mean``) is exactly the pydantic dump of the plant.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from technoeconomics.data import Dataset
from technoeconomics.model.plant import Plant

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# Component fields that are never user-editable in the form.
_HIDDEN_FIELDS = frozenset({"id", "enabled", "plot_color"})


@dataclass
class Param:
    """One editable scalar leaf of a component (possibly nested inside a dataset)."""

    path: str  # dotted overlay path into the serialised plant, e.g. "grid.price.mean"
    label: str  # the path without the component id, e.g. "price.mean"
    value: float
    advanced: bool  # render under the form's "Advanced" section rather than inline


@dataclass
class ComponentForm:
    """A component rendered as a fieldset: an enable toggle plus its parameters."""

    id: str
    title: str
    enabled: bool
    params: list[Param]
    color: str | None  # the component's carrier colour, for a coloured accent


def _walk(
    prefix: str, value: object, advanced: bool
) -> Iterator[tuple[str, float, bool]]:
    """Yield ``(path, value, advanced)`` for each scalar leaf at or under `value`.

    Recurses into nested datasets, so a `Sinusoidal` (mean/amplitude/period/phase) becomes
    one leaf per field. Booleans are skipped -- they are not numeric inputs.
    """
    if isinstance(value, Dataset):
        for f in fields(value):
            yield from _walk(f"{prefix}.{f.name}", getattr(value, f.name), advanced)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield prefix, float(value), advanced


def plant_to_form(plant: Plant) -> list[ComponentForm]:
    """Describe a plant's editable parameters for rendering, one entry per component."""
    out: list[ComponentForm] = []
    for component in plant.components:
        params: list[Param] = []
        for f in fields(component):
            if f.name in _HIDDEN_FIELDS:
                continue
            value = getattr(component, f.name)
            advanced = bool(f.metadata.get("advanced"))
            for path, leaf, adv in _walk(f"{component.id}.{f.name}", value, advanced):
                params.append(
                    Param(
                        path=path, label=path.split(".", 1)[1], value=leaf, advanced=adv
                    )
                )
        out.append(
            ComponentForm(
                id=component.id,
                title=component.id.replace("_", " ").capitalize(),
                enabled=component.enabled,
                params=params,
                color=str(component.plot_color) if component.plot_color else None,
            )
        )
    return out


def form_to_plant(base: Plant, form: Mapping[str, str]) -> Plant:
    """Overlay a submission onto the plant and rebuild it.

    Field names are dotted paths into the serialised plant (``"<id>.<field>[.<sub>...]"``); a
    component's ``enabled`` checkbox is present only when ticked. We serialise `base`, set
    each component's ``enabled``, overlay every submitted scalar at its path, and rebuild --
    operating on the plain dict rather than the frozen datasets. Keys that don't resolve to a
    leaf (e.g. an unexpected field in a crafted POST) are ignored.

    Args:
        base: The plant supplying the structure and current values.
        form: The submitted form values.

    Returns:
        A new plant with the submission applied.

    Raises:
        ValueError: If a submitted value at a valid path is not a number.
    """
    d = base.to_dict()
    by_id = {c["id"]: c for c in d["components"]}
    for c in d["components"]:
        c["enabled"] = f"{c['id']}.enabled" in form
    for key, val in form.items():
        if key.endswith(".enabled"):
            continue
        cid, *path = key.split(".")
        node = by_id.get(cid)
        if node is None or not path:
            continue
        for k in path[
            :-1
        ]:  # walk to the leaf's parent, skipping keys that don't resolve
            if not isinstance(node, dict) or k not in node:
                node = None
                break
            node = node[k]
        if not isinstance(node, dict) or path[-1] not in node:
            continue
        try:
            node[path[-1]] = float(val)
        except ValueError:
            raise ValueError(f"{key}: {val!r} is not a number") from None
    return Plant.from_dict(d)
