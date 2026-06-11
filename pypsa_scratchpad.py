"""
super simple exploration of converting a plant into a pypsa model
just local solar, grid electricity, heat pump, constant heat demand
"""

import logging

import atlite
import matplotlib.pyplot as plt
import pandas as pd
import pypsa

logging.basicConfig(level=logging.INFO)

SNAPSHOTS = pd.date_range("2013-01-01", "2013-12-31 23:00:00", freq="h")
BOUNDS = (-5, -5, 5, 5)
ELECTRICITY_COST = 120  # EUR/MWh
SOLAR_COST = 600000  # EUR/Mw
HP_COP = 2
HP_COST = 1000000 * HP_COP  # EUR/MWth
BATTERY_COST = 120000  # EUR/MW
O_M_FRACTION = 0.02
HEAT_DEMAND = 1
GRID_CONN_COST = 1000
LOCATION = (0, 0)
DISCOUNT_RATE = 0.05


def annual_cost(overnight_cost, lifetime_years):
    """Annualise overnight capex (EUR/MW) and fold in fixed yearly O&M."""
    crf = pypsa.costs.annuity(DISCOUNT_RATE, lifetime_years)
    return overnight_cost * (crf + O_M_FRACTION)


c = atlite.Cutout(
    bounds=BOUNDS, time=SNAPSHOTS, path="scratchpad_cutout.nc", module="era5-edh"
)

c.prepare()

pv = c.pv(
    panel="CSi",
    orientation="latitude_optimal",
    tracking=None,
    aggregate_time=None,
)

pv_point = pv.sel(x=LOCATION[0], y=LOCATION[1], method="nearest").to_pandas()  # ty: ignore[unresolved-attribute]

n = pypsa.Network()
# pypsa has an invalid signature in set_snapshots, but DatetimeIndex works here, it's even in the docs
n.set_snapshots(snapshots=SNAPSHOTS)  # ty: ignore[invalid-argument-type]
n.add("Bus", ["heat", "electricity"], carrier=["heat", "electricity"])
n.add(
    "Carrier",
    ["electricity", "heat", "battery_storage", "solar", "grid", "heat_pump"],
    color=["black", "red", "yellow", "orange", "grey", "green"],
)
n.add("Load", "heat_demand", bus="heat", carrier="heat", p_set=HEAT_DEMAND)
n.add(
    "Process",
    "heat_pump",
    bus0="electricity",
    bus1="heat",
    carrier="heat_pump",
    rate0=-1,
    rate1=HP_COP,
    p_nom_extendable=True,
    capital_cost=annual_cost(HP_COST / HP_COP, 20),
    marginal_cost=0,  # O&M is a fixed cost, folded into capital_cost via annuity()
)
n.add(
    "Generator",
    "solar",
    bus="electricity",
    carrier="solar",
    p_max_pu=pv_point,
    capital_cost=annual_cost(SOLAR_COST, 25),
    marginal_cost=0,  # sunlight is free; O&M lives in capital_cost
    p_nom_extendable=True,
)
n.add(
    "Generator",
    "grid",
    bus="electricity",
    carrier="grid",
    p_nom_extendable=True,
    capital_cost=GRID_CONN_COST,
    marginal_cost=ELECTRICITY_COST,
)
n.add(
    "StorageUnit",
    name="battery_electric",
    bus="electricity",
    carrier="battery_storage",
    max_hours=3,
    capital_cost=annual_cost(BATTERY_COST, 15),
    p_nom_extendable=True,
    cyclic_state_of_charge=True,
)

n.optimize(solver_name="highs")

tsc = (
    pd.concat([n.statistics.capex(), n.statistics.opex()], axis=1).sum(axis=1).div(1e3)
)
tsc

print(f"Total system cost\n{tsc}\nOptimal capacity\n{n.statistics.optimal_capacity()}")


n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="electricity")
n.buses_t.marginal_price.plot(figsize=(7, 2))
plt.show()
