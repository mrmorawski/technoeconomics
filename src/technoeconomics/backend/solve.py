"""Build, optimise, and read out a plant -- the one solve path shared by web and CLI."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from technoeconomics.backend.results import numbers, plots

if TYPE_CHECKING:
    from technoeconomics.backend.preset import Preset
    from technoeconomics.model.plant import Plant

log = logging.getLogger(__name__)


def solve(plant: Plant, preset: Preset) -> dict:
    """Build a plant's network, optimise it, and read out the preset's results.

    Synchronous and side-effect free apart from `logging`: the web captures those
    log records for its console, the CLI lets them print, the server keeps them for
    debugging. The same calls serve all three.

    Args:
        plant: The plant to solve.
        preset: The preset whose `numbers` and `plots` to compute from the solution.

    Returns:
        ``{"numbers": [...], "plots": [...]}`` -- ready for the page.

    Raises:
        RuntimeError: If the optimisation does not reach an optimal solution.
    """
    log.info("Building network…")
    n = plant.build_network()
    log.info("Solving…")
    status, condition = n.optimize(solver_name="highs")
    if status != "ok":
        raise RuntimeError(f"solve failed: status={status}, condition={condition}")
    n.sanitize()  # assign colours to any carriers that lack one
    return {
        "numbers": numbers(n, list(preset.numbers)),
        "plots": plots(n, list(preset.plots)),
    }
