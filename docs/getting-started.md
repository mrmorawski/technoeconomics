# Getting started
This package simplifies analysing investments into energy infrastructure when the costs of energy are variable and uncertain. With `technoeconomics-app`, you can optimise the energy supply for an application, explore how optimal solutions change under various scenarios, and make smart decisions for your energy future.

We implement:

  - dynamic grid electricity tariffs
  - onsite renewables
  - batteries (electrical and heat)
  - heat pumps
  - electric boilers
  - district heating

We calculate:

  - a mix of investment that will provide lowest total cost during the lifetime of the asset
  - project economics

Currently, we support the following use-cases:

  - low temperature industrial process heat

Support is also planned for:

  - electrified households with heat pumps, EV's, solar panels, battery storage

??? tip

    ## Why is this useful?

    Energy costs, and energy availability, are on everyone's mind these days.

    Oil and gas are expensive, and emit massive amounts of $CO_2$. It's often cheaper to replace them with equipment running on electricity, ideally powered by renewables. But how do you know when that makes sense?

    Calculating how much it costs to run something on fossil fuels is simple:

    - Equipment is cheap
    - You mostly pay for fuel, at a (outside of energy crises) constant price

    However, for electrotech:

    - Electricity prices are dynamic - they change throughout the day and throughout the year
    - The cheapest way to get electricity is to generate it yourself with solar PV, but the output of that also varies
    - Equipment is expensive. To save money, you have to size it right for the application and think about how you're going to finance it

    To make smart decisions, you have to figure out the optimal mix of energy sources and conversion equipment. This is not an easy problem. You need to calculate how much solar you should build, how big a battery, when use gas and when to use storage. You need data on electricity tariffs, solar irradiation, temperature throughout the year, equipment costs etc. `technoeconomics-app` handles that for you.



## Installation and usage
### Web UI
The simplest way to use `technoeconomics-app` is through the Web UI at [https://technoeconomics.app](https://technoeconomics.app)

### CLI/API
We also offer a command line interface.

#### Prerequisites

- [Python 3.12](https://www.python.org/) or newer
- [uv](https://docs.astral.sh/uv/) for dependency management. Install it with:

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

#### Installation

Clone the repository and sync the dependencies:

```bash
git clone https://github.com/mrmorawski/technoeconomics.git
cd technoeconomics
uv sync
```

`uv sync` creates a virtual environment in `.venv` and installs all required dependencies.

You can then run commands inside the environment with `uv run`, for example:

```bash
uv run technoeconomics-app --help
```

Alternatively, activate the environment directly:

```bash
source .venv/bin/activate
```
