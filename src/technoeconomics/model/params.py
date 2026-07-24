"""The preset-author vocabulary: everything a parameter annotation needs, one import.

Preset authors describe a component or dataset field with a single `Param` annotation
carrying markers from this module -- unit, bounds, visibility -- and never import
``typing``, ``pydantic``, or ``annotated_types`` themselves:

```python
from technoeconomics.model.params import Advanced, Ge, Hidden, Param, Unit

period: Param[float, Gt(0), Unit("h")] = 24.0
capex: Param[Param[Scalar, Ge(0)] | ScalarDataset, Unit("EUR/MW"), Advanced] = 400.0
bus: Param[str, Hidden]
```

`Param` is `typing.Annotated` under a friendlier name, so type checkers see the plain
value type; the bounds (`Ge`/`Gt`/`Le`/`Lt`) are ``annotated_types`` re-exports, so
pydantic enforces them natively with per-field error locations.

Bounds constrain **user-supplied scalars only** -- their job is helpful input
validation, and pydantic cannot guarantee what a dataset will compute. On a field that
can also hold a dataset, the bound therefore goes on the *scalar branch* of the union
(``Param[Scalar, Ge(0)] | ScalarDataset``), never on the union itself: pydantic applies
an outer bound to whatever the union yields and raises a bare `TypeError` when that is
a dataset value. The form-spec generator ([`technoeconomics.web.spec`][]) reads the
scalar-branch bound as the field's effective bound, and propagates it (with the unit)
to the [`Magnitude`][technoeconomics.model.params.Magnitude] leaves of a dataset in
that field -- those leaves are user-supplied scalars too, checked by the solve
endpoint's spec-loop since they sit outside pydantic's reach.

A propagated bound constrains **each leaf it lands on, not the value the dataset
computes**. ``load: Param[Param[Scalar, Ge(0)] | SeriesDataset, Unit("MW")]`` holding a
`Sinusoidal` bounds ``mean >= 0`` and ``amplitude >= 0`` -- it does not stop
``mean=1, amplitude=100`` from resolving to a series that dips to -99 MW. Bounds are
input hygiene; a dataset that has a resolved-value invariant has to enforce it itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from annotated_types import Ge, Gt, Le, Lt

__all__ = [
    "Advanced",
    "Ge",
    "Gt",
    "Hidden",
    "Label",
    "Le",
    "Lt",
    "Magnitude",
    "Param",
    "Unit",
]

Param = Annotated
"""``typing.Annotated`` under an author-friendly name: ``Param[float, Ge(0), Unit("h")]``."""


@dataclass(frozen=True)
class Unit:
    """The unit a numeric field is displayed and edited in (e.g. ``Unit("EUR/MWh")``).

    On a component's dataset field the unit is *per-use*: it propagates to the leaves the
    dataset marks [`Magnitude`][technoeconomics.model.params.Magnitude], so one dataset
    class can serve as a price in one field and a demand in another.

    Attributes:
        text: The display text, e.g. ``"EUR/MWh"``.
    """

    text: str


@dataclass(frozen=True)
class Label:
    """The human-readable name a field is shown under (e.g. ``Label("COP")``).

    Without one the form derives a label from the field's path (``round_trip_efficiency``,
    ``price.mean``), which cannot produce an initialism or a properly cased phrase.

    On a component field holding a dataset the label is a *prefix*: the form renders each
    leaf as ``"<field label> <leaf label>"`` (so ``Label("Heat demand")`` over a `Sinusoidal`
    gives "Heat demand mean", "Heat demand amplitude", ...), where the leaf label is the
    dataset field's own `Label` if it has one, else its name.

    Attributes:
        text: The display text, e.g. ``"Round-trip efficiency"``.
    """

    text: str


@dataclass(frozen=True)
class _Flag:
    """A singleton visibility/role marker; compare by identity (``marker is Advanced``).

    Attributes:
        name: The marker's display name, for reprs and error messages.
    """

    name: str


Advanced = _Flag("Advanced")
"""Render this field under the form's "Advanced" section rather than inline."""

Hidden = _Flag("Hidden")
"""Exclude this field from the form entirely (bus references, non-input plumbing).

A hidden field gets no spec path, so it is not addressable by a submission at all: it keeps
whatever the preset gave it.
"""

Magnitude = _Flag("Magnitude")
"""Mark a dataset field as carrying the dataset's magnitude.

A magnitude leaf takes its unit and bounds from the field *holding* the dataset (the
use), not from the dataset class -- ``mean`` is EUR/MWh in a price field and MW in a
demand field.
"""
