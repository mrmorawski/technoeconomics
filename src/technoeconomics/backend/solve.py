"""Build, optimise, and read out a plant -- the one solve path shared by web and CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from technoeconomics.backend.results import numbers, plots
from technoeconomics.progress import emit

if TYPE_CHECKING:
    from technoeconomics.backend.preset import Preset
    from technoeconomics.model.plant import Plant


def solve(plant: Plant, preset: Preset) -> dict:
    """Build a plant's network, optimise it, and read out the preset's results.

    Reports progress per phase via [`progress.emit`][technoeconomics.progress.emit], which the
    caller (e.g. the web session) may stream to the user; unheard when no sink is bound.

    Args:
        plant: The plant to solve.
        preset: The preset whose `numbers` and `plots` to compute from the solution.

    Returns:
        ``{"numbers": [...], "plots": [...]}`` -- ready for the page.

    Raises:
        RuntimeError: If the optimisation does not reach an optimal solution.
    """
    emit("Building network…")
    n = plant.build_network()
    emit("Solving…")
    # TODO: use faster solver config, pdlp, many threads etc.
    status, condition = n.optimize(solver_name="highs")
    if status != "ok":
        raise RuntimeError(f"solve failed: status={status}, condition={condition}")
    n.sanitize()  # TODO: check if necessary
    return {
        "numbers": numbers(n, list(preset.numbers)),
        "plots": plots(n, list(preset.plots)),
    }
