<!-- TODO:: add local web server launch info --->

# Development

## Environment with `uv`

The project uses [`uv`](https://docs.astral.sh/uv/) for dependency and
environment management. The `dev` dependency group includes the tooling needed
to work on the project (linting, type checking, docs).

Sync the environment, including dev dependencies:

```bash
uv sync
```

Run any project command inside the managed environment with `uv run`:

```bash
uv run python -m technoeconomics
```

## Pre-commit hooks

If you want to contribute to this repository, please set up [`pre-commit`](https://pre-commit.com).

```bash
uv run pre-commit install --install-hooks
uv run pre-commit install --hook-type commit-msg
```

The hooks run automatically on every commit. To run them against the whole
repository on demand:

```bash
uv run pre-commit run --all-files
```

## Style

### Documentation

All docstrings follow the Google docstring convention. Example docstring:

```python
def lcoe(capex: float, opex: float, energy: float, rate: float = 0.07):
  """Compute levelised cost of energy.

    Args:
        capex: Capital expenditure (EUR)
        opex: Annual operating expenditure (EUR/yr)
        energy: Annual energy yield (MWh/yr)
        rate: Discount rate as a decimal fraction (_)

    Returns:
        LCOE (EUR/Mwh)

    Raises:
        ValueError: If ``energy`` is negative

```

For an exhaustive specification of this docstring style, see the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).

## Documentation

### Local

We use [zensical](https://zensical.org/) for documentation. To build it the docs, simply run:

```bash
uv run zensical build
```

And to serve them and inspect locally:

```bash
uv run zensical serve --dev-addr localhost:CHOSEN_PORT
```

### Online

Online docs are built by a GitHub CI, `.github/workflows/docs.yml` and published under [https://mrmorawski.github.io/technoeconomics](https://mrmorawski.github.io/technoeconomics).
