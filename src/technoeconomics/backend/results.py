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
    """
    balance = network.statistics.energy_balance(aggregate_time=False)
    charts: list[dict] = []
    for carrier in dict.fromkeys(network.buses.carrier):
        # energy_balance leaves NaN where a component does not contribute at a timestep;
        # for a stacked balance that is simply zero flow. Fill it, both so the area stacks
        # correctly and because NaN serialises to a bare `NaN` token that is invalid JSON.
        wide = balance.xs(carrier, level="bus_carrier").T.fillna(0.0)
        names = [comp_carrier for _comp, comp_carrier in wide.columns]
        # One shared dataset: a header row, then [iso_time, *values_per_series] rows.
        source = [["time", *names]]
        for time, row in zip(wide.index, wide.to_numpy().tolist(), strict=True):
            source.append([time.isoformat(), *row])
        series = [
            {
                "name": name,
                "type": "line",
                "stack": "balance",
                "stackStrategy": "samesign",  # supply stacks up, demand stacks down
                "symbol": "none",
                "encode": {"x": "time", "y": name},
                **_series_style(_color(network, name)),
            }
            for name in names
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
    """ECharts styling for one series.

    A thin line and a translucent fill, plus the carrier colour (line/area/legend) when
    the carrier has one, else ECharts' default palette.
    """
    line: dict = {"width": 1}
    area: dict = {"opacity": 0.6}
    extra: dict = {}
    if color is not None:
        line["color"] = area["color"] = extra["color"] = color
    return {"lineStyle": line, "areaStyle": area, **extra}


def _stacked_area(
    title: str,
    y_label: str,
    source: list[list],
    series: list[dict],
    initial_range: tuple[str, str] | None = None,
) -> dict:
    """Assemble a stacked-area ECharts option over a time axis.

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
