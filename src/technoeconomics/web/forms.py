"""The form <-> plant boundary.

The form is the user's source of truth for a model's editable parameters.

- [`plant_to_form`][technoeconomics.web.forms.plant_to_form] turns a plant into field
  descriptors the preset page renders.
- [`form_to_plant`][technoeconomics.web.forms.form_to_plant] writes a submission back
  onto a fresh preset plant (the structure) and returns it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

from technoeconomics.data import Dataset
from technoeconomics.model.plant import Plant
from technoeconomics.model.structure import Bus

# Component fields that are never user-editable in the form.
_HIDDEN_FIELDS = frozenset({"id", "enabled", "plot_color"})


def _scalar_field_names(component: object) -> list[str]:
    """Names of a component's editable scalar (float) parameters.

    Bus references, datasets/series, booleans, and the identity/colour fields are
    excluded.
    """
    names: list[str] = []
    for field in fields(component):  # ty: ignore[invalid-argument-type]
        if field.name in _HIDDEN_FIELDS:
            continue
        value = getattr(component, field.name)
        if isinstance(value, (Bus, Dataset, bool)):
            continue
        if isinstance(value, (int, float)):
            names.append(field.name)
    return names


@dataclass
class FormField:
    """One editable scalar parameter of a component."""

    name: str  # e.g. "heat_pump.cop"
    label: str  # e.g. "cop"
    value: float


@dataclass
class ComponentForm:
    """A component rendered as a fieldset: an enable toggle plus scalar inputs."""

    id: str
    title: str
    enabled: bool
    fields: list[FormField]
    color: str | None  # the component's carrier colour, for a coloured accent


def plant_to_form(plant: Plant) -> list[ComponentForm]:
    """Describe a plant's editable parameters for rendering, one entry per component."""
    out: list[ComponentForm] = []
    for component in plant.components:
        form_fields = [
            FormField(
                name=f"{component.id}.{name}",
                label=name,
                value=float(getattr(component, name)),
            )
            for name in _scalar_field_names(component)
        ]
        out.append(
            ComponentForm(
                id=component.id,
                title=component.id.replace("_", " ").capitalize(),
                enabled=component.enabled,
                fields=form_fields,
                color=str(component.plot_color) if component.plot_color else None,
            )
        )
    return out


def form_to_plant(plant: Plant, form: Mapping[str, str]) -> Plant:
    """Write a submission onto a fresh preset plant and return it.

    Form fields are named ``"<component_id>.<field>"``; a component's ``enabled``
    checkbox is present only when ticked. The edited scalars are set directly on the
    plant's (mutable) components.

    Args:
        plant: A fresh plant (from the preset) supplying the structure and defaults.
        form: The submitted form values.

    Returns:
        The same plant, with the submission applied.

    Raises:
        ValueError: If a submitted value is not a number.
    """
    for component in plant.components:
        component.enabled = f"{component.id}.enabled" in form
        for name in _scalar_field_names(component):
            key = f"{component.id}.{name}"
            if key in form:
                setattr(component, name, float(form[key]))
    return plant
