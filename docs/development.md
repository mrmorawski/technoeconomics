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
