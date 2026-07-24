"""Compute the results of a solved plant for the frontend."""

from __future__ import annotations

from enum import StrEnum, auto
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import pypsa


class Number(StrEnum):
    """A headline number a preset can request."""

    PROJECT_COST = auto()


class Plot(StrEnum):
    """A chart a preset can request."""

    ENERGY_BALANCE = auto()


def numbers(network: pypsa.Network, requested: list[Number]) -> list[dict]:
    """Compute the requested headline numbers from a solved network.

    Args:
        network: A solved, sanitised PyPSA network.
        requested: The numbers to compute, in display order.

    Returns:
        One ``{"label", "value", "unit"}`` dict per requested number.
    """
    return [_number(network, n) for n in requested]


def plots(network: pypsa.Network, requested: list[Plot]) -> list[dict]:
    """Compute the requested charts as identified ECharts options.

    Args:
        network: A solved, sanitised PyPSA network.
        requested: The plots to compute, in display order.

    Returns:
        ``{"id", "option"}`` dicts, where ``option`` is ready for
        ``echarts.init(el).setOption(option)`` and ``id`` is stable across solves so the
        client can update each chart in place. One request may yield several charts -- an
        energy balance gives one per bus carrier.

    Raises:
        ValueError: If a requested plot is unknown.
    """
    out: list[dict] = []
    for p in requested:
        match p:
            case Plot.ENERGY_BALANCE:
                out.extend(_energy_balance(network))
            case _:
                raise ValueError(f"unknown plot: {p}")
    return out


def _number(network: pypsa.Network, n: Number) -> dict:
    """Compute one headline number."""
    match n:
        case Number.PROJECT_COST:
            return {
                "label": "Annual system cost",
                "value": float(network.objective),  # ty: ignore[invalid-argument-type]
                "unit": "EUR/a",
            }
        case _:
            raise ValueError(f"unknown number: {n}")


def _energy_balance(network: pypsa.Network) -> list[dict]:
    """An identified stacked-area chart per bus carrier, at full time resolution.

    Each entry is ``{"id": "balance_<carrier>", "option": <echarts option>}``; the id is
    stable across solves so the client can update the carrier's chart in place.

    Series are addressed by a ``<pypsa component>:<carrier>`` key rather than by carrier alone.
    The key is unique by construction (it is the balance's own MultiIndex), which both the
    dataset dimension names and the series ids need: a duplicate dimension name would make
    ``encode.y`` resolve to whichever column came first, and a duplicate series id would break
    the client's id-keyed merge. The carrier stays the display name.
    """
    balance = network.statistics.energy_balance(aggregate_time=False)
    charts: list[dict] = []
    for carrier in dict.fromkeys(network.buses.carrier):
        # energy_balance leaves NaN where a component does not contribute at a timestep;
        # for a stacked balance that is simply zero flow. Fill it, both so the area stacks
        # correctly and because NaN serialises to a bare `NaN` token that is invalid JSON.
        wide = balance.xs(carrier, level="bus_carrier").T.fillna(0.0)
        columns = list(wide.columns)
        keys = [f"{comp}:{comp_carrier}" for comp, comp_carrier in columns]
        labels = [comp_carrier for _comp, comp_carrier in columns]
        # One shared dataset: a header row, then [iso_time, *values_per_series] rows.
        source: list[list] = [["time", *keys]]
        for time, row in zip(wide.index, wide.to_numpy().tolist()):
            source.append([time.isoformat(), *row])
        series = [
            {
                "id": key,
                "name": label,
                "type": "line",
                "stack": "balance",
                "stackStrategy": "samesign",  # supply stacks up, demand stacks down
                "symbol": "none",
                # Dispatch is piecewise-constant: the value at snapshot t holds across the
                # whole interval and then jumps. "end" holds y at the current point until the
                # next snapshot's x (`start` would hold the *next* value, shifting everything
                # one interval early). Interpolating instead would draw ramps that are not in
                # the solution, and read as near-vertical streaks wherever dispatch switches.
                # `smooth` is off by default too, but say so: a curve here would be fiction.
                "step": "end",
                "smooth": False,
                "encode": {"x": "time", "y": key},
                **_series_style(_color(network, label)),
            }
            for key, label in zip(keys, labels)
        ]
        charts.append(
            {
                "id": f"balance_{carrier}",
                "option": _stacked_area(
                    title=f"{carrier.capitalize()} balance",
                    y_label="Power [MW]",
                    source=source,
                    series=series,
                    initial_range=_first_week_of_may(wide.index),
                ),
            }
        )
    return charts


def _first_week_of_may(index: pd.DatetimeIndex) -> tuple[str, str] | None:
    """ISO timestamps bounding the first week of May, for the default chart zoom.

    Returns ``(start, end)`` (as ISO strings the time axis parses), or None if the
    horizon does not span that week (then the chart just opens fully zoomed out).
    """
    may_1 = pd.Timestamp(f"{index[0].year}-05-01")
    if index[0] <= may_1 <= index[-1]:
        return (may_1.isoformat(), (may_1 + pd.Timedelta(days=7)).isoformat())
    return None


def _color(network: pypsa.Network, carrier: str) -> str | None:
    """A carrier's plot colour as a plain string (PlotColor is a StrEnum), or None."""
    color = network.carriers.color.get(carrier)
    return str(color) if color else None


def _series_style(color: str | None) -> dict:
    """ECharts styling for one series: fill only, in the carrier's colour when it has one.

    No stroke, deliberately. A stacked band's outline is drawn along its *top*, which sits at
    the running stack total -- so a component contributing nothing still strokes a line across
    the chart at whatever that total happens to be, and a step riser strokes a full-height
    vertical wherever a flow jumps. Both are artefacts of the outline, not of the data: zrender
    skips a zero-width stroke entirely (`Path.hasStroke`), leaving a band of no height drawing
    nothing at all, which is what a component sitting at zero should look like.

    The fill is nearly opaque because it is now the only thing separating one band from the
    next; at the old 0.6 the stack read as mud without its outlines.
    """
    area: dict = {"opacity": 0.85}
    extra: dict = {}
    if color is not None:
        area["color"] = extra["color"] = color
    return {"lineStyle": {"width": 0}, "areaStyle": area, **extra}


def _stacked_area(
    title: str,
    y_label: str,
    source: list[list],
    series: list[dict],
    initial_range: tuple[str, str] | None = None,
) -> dict:
    """Assemble a stepped stacked-area ECharts option over a time axis.

    Built-in `dataZoom` (an inside wheel/drag zoom plus a slider) lets the user zoom and
    pan; axis labels are forced to ``YYYY-MM-DD``. `initial_range`, when given, opens the
    chart zoomed to that ``(start, end)`` window.
    """
    zoom = {}
    if initial_range is not None:
        zoom = {"startValue": initial_range[0], "endValue": initial_range[1]}
    return {
        "title": {"text": title, "left": "center", "top": 0},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 28, "type": "scroll"},
        "grid": {"left": 55, "right": 25, "top": 70, "bottom": 70},
        "dataset": {"source": source},
        "xAxis": {
            "type": "time",
            "axisLabel": {"formatter": "{yyyy}-{MM}-{dd}"},
        },
        "yAxis": {"type": "value", "name": y_label},
        "dataZoom": [
            {"type": "inside", **zoom},
            {"type": "slider", "bottom": 10, **zoom},
        ],
        "series": series,
    }
