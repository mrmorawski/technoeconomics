The point of this project is to create an online tool for running technoeconomic analyses of plants with time-varying 
input and output commands. The first application is in industrial heat.

# Inspiration
- http://model.energy - does the same for energy systems
- https://gitlab.com/marcin/teabag - an experiment for a pure linopy backend - throwaway, but proved the concept

# Architecture
## General idea
Still to be decided. But I'd like to have a backend that calculates an optimal plant given a set of technoeconomic assumptions,
and a frontend that lets the user control assumptions and input data, and then displays result.

## backend
- solver: highs to keep it open source
- framework: either raw linopy or single PyPSA node
- fastapi/pydantic passes data to solver
- sqlite for state + queue (if solving slow)

## frontend
### web
- something dead simple as base, maybe plain HTML + jinja
- nice charts with some fancy TS charting library

### cli
- typer
- same backend as web

## deploy
- single docker container

## docs 
- zensical
- short screencast on how to use

## dev
- `ruff` lint + format with docstring chech
- precommit to check

# features
## minimal set
- web elements: server etc. etc. - no idea
- pick plant location by coords, with map display (useful for electricity prices, onsite solar etc.) 
- pick plant elements/technologies to be included in optimisation. possibly from a template, with some sort of input/output/conversion flow
- backend usable on its own - nice API for scripting
- generates optimal plant setup 
- uses optimal plant setup to run a financial model to get NPV etc.
- displays graphs for the optimal plant;
  - energy balance throughout the year
  - equipment capacities
  - capex/opex shares
  - cash flow, NPV etc.

## extended set 
- other time varying dispatch/capacity optimisation stuff, e.g. time-varying tariffs for consumers
- noJS fallback for charts
- address/map click to pick location
- generalisable component framework
- fast solver to do near-real-time solutions e.g. with a slider (maybe GPU-based)

# user flow
## model
1. open website
2. pick components
3. fiddle with technoeconomics
4. solve
5. inspect results

# notes
## structure
- technoeconomics.frontend_web
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


# TODO
- [ ] look at single-node PyPSA and whether it'd made sense here
- [ ] learn fastapi, set up super simple server and frontend
- [ ] go through pydantic tutorial 
- [ ] decide on data model plus arch for fastapi



