The point of this project is to create an online tool for running technoeconomic analyses of plants with time-varying 
inputs and outputs. The first application is in industrial heat.

# TODO
- [x] look at single-node PyPSA and whether it'd made sense here
- [ ] set up framework for development - repo, docker, docs etc. etc.
- [ ] set up skeleton of the architecture above with end-end passthrough so I can hack on the model while testing the frontend
- [ ] simple model
- [ ] iterate by adding features

# Inspiration
- http://model.energy - does the same for energy systems
- https://gitlab.com/marcin/teabag - an experiment for a pure linopy backend - throwaway, but proved the concept
- https://github.com/pypsa/pypsa-eur -  ideas for managing data workflows.

# features
## minimal set
- pick plant location by coords, with map display (useful for electricity prices, onsite solar etc.) 
- pick plant elements/technologies to be included in optimisation from a list of pre-built models:
  - first - industrial plant. then - household. then - district heating luft-style
- generates optimal plant setup
- uses optimal plant setup to run a financial model to get NPV etc.
- displays graphs for the optimal plant;
  - energy balance throughout the year
  - equipment capacities
  - capex/opex shares
  - cash flow, NPV etc.
- shareable result url backend usable on its own - nice API for scripting
- CLI

## extended set 
- other time varying dispatch/capacity optimisation stuff, e.g. time-varying tariffs for consumers
- users can feed in their own timeseries data - electricity prices etc.
- noJS fallback for charts
- address/map click to pick location
- generalisable component framework
- fast solver to do near-real-time solutions e.g. with a slider
- parameter sweeps

# Architecture
## General idea
Still to be decided. 

Current idea is simple MVC:

1. frontend passes a model preset name plus any user changes to backend
2. backend compiles a complete model intermediate representation graph, passes to model
3. model converts intermediate representation to pypsa, solves it, returns results to backend 
4. backend updates db, send results to frontend 
5. frontend displays results to user
6. user tweaks params, back to step 1.

## guiding principles
- as simple as possible
- easy to maintain
- small and performant

## frontend
### web
- jinja templates rendered server-side
- htmx with nojs fallback
- charts: for now server-side svg, later some nice chart lib
- by default exposes only a few params to user (marked in template), but almost any can be dug into if needed
- passes base model name plus any mods to backend:
- navbar:
  - one entry per template
  - about
  - link to docs
- on template page:
  - svg of model, css can cause the components to be greyed out if disabled
  - params to be edited (with option to dive in)
  - solve button
  - reloadable graph which updates on change

```json
{"model": "industrial_heat",
"disabled": ["solar"],
"overrides": {"heat_pump": {"capex": 1000}}
}
```
```
```

#### user flow
1. open website
2. pick components
3. fiddle with technoeconomics
4. solve
5. inspect results
6. iterate

### cli
- typer
- same backend and model
- input is yamls, output is yamls plus png graphs

## deploy
- single docker container

## docs 
- zensical
- short screencast on how to use

## dev
- `ruff` lint + format with docstring check
- precommit to check

## backend
- orchestrates everything - calls model, returns result
- fastapi/pydantic for frontend integration
- htmx polling to get job state
- sqlite for state:
  - stores plantconfig for every run, making runs reproducible-ish
  - for now handwritten sql, no orm
  - detailed results stored as nc, then purged (rerun if asked for job again)
- process pool for running solve jobs, later can update to workers and a job queue if needed
- how to handle rate limiting and multiple users?


### model
- overnight optimisation
- stateless now, later if too slow we can investigate stateful to get warm starts and such
- for now EU, later add US data
- initally industrial low temperature process heat. then - household energy (solar, HPs etc,)
- for now - pypsa with an intermediate representation (PlantConfig)
- component types:
  - input
  - output/demand
  - conversion
  - no feedback components to keep it linear for now, but intermediate rep means could be added in the future
- input types:
  - electricity:
    - but how to deal with locational variability and future scenarios? we could calculate deltas between wholesale electricity price and eurostat/some US body electricity prices and assume same in the future
  - heat
  - gas
- output types:
  - electricity
  - heat
  - whatever other flow quantities needed
- conversion types:
  - lots of options, could really be anything.
  - heat timeseries (should we do heat levels?)
  - electricity timeseries
- how to deal with subsidies? some of them may influence model
- structure
  - components (heat pump etc.) - high-level building blocks
  - templates engine - turns data from backend, which only speaks templates, into a generalised graph of components
  - graph parser - turn a graph into a model for the solver
  - optimiser - for now pypsa, but intermediate rep means it could be sth else later
  - results processor - extraction of data, financial modelling etc.

#### components
##### heat pumps
- most complicated part of model, if we go into process integration (likely we shouldn't). otherwise simple Link/Process with wither a constant or time varyuing COP (e.g. from carnot based on outdoor temp and process heat demand temp)  
- current idea - two HP options:
  - ambient air in, process heat out - lower installation cost, lower COP
  - process heat/district heat in - higher installation cost, higher COP (read paper referenced in Volts)

#### templates

##### industrial heat
- treatment of grid electricity pricing and PPAs difficult in industrial case

##### residential
- heating - heat loss as time-dependent demand, house as storage
- electricity input - pretty simple, just get a sensible TOU tariff
- not sure how to treat vars that have loose constraints such as EVs which just need a charge lvl in the morning - just add as a constraint?

#### parser
- overall config borrows pypsa network representation with carriers and nodes that attach to them - simplifies graph repr massively

```json
{"schema_ver": 1,
"name": "industrial_heat_123123",
"carriers": ["electricity", "heat"]
"components":
  - {"name": "heat_pump", etc. etc.}
} 
```

#### optimiser
- ideally I'd like to get second-scale solve times, so the optimisation can be interactive
- pypsa for now
- optimisation solver highs for open source
- some tricks that may be usedful: 
  - temporal aggregation
  - warm starts (first solve takes a while, subsequent should be fast with minor tweaks)
  - model persistence across runs (only change things that were tweaked to save building time)
  - no milp
- apparently CPU simplex should be faster than GPU PDLP for small problems like mine?  



# notes
## structure
- technoeconomics.frontend_web
- technoeconomics.frontend_cli
- technoeconomics.backend
- technoeconomics.model

## fastapi
- install fastapi with [standard-no-fastapi-cli]
- deployment notes:
  ```markdown
  Configure the app entrypoint in pyproject.toml¶

You can configure where your app is located in a pyproject.toml file like:

[tool.fastapi]
entrypoint = "main:app"

That entrypoint will tell the fastapi command that it should import the app like:

from main import app

If your code was structured like:

.
├── backend
│   ├── main.py
│   ├── __init__.py

Then you would set the entrypoint as:

[tool.fastapi]
entrypoint = "backend.main:app"

which would be equivalent to:

from backend.main import app
```

```

  



