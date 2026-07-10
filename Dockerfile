FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build

# atlite is pinned to a git branch, so resolving dependencies needs git
# hadolint ignore=DL3008  # git version is irrelevant; uv.lock pins the dep
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# use the image's interpreter so the venv survives the copy into the runtime image
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

# README and LICENSE are referenced by pyproject, hatchling needs them to build the wheel
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm

RUN useradd --create-home app
COPY --from=build --chown=app:app /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# dataset cache lives on the data volume ($TECHNOECONOMICS_CACHE); running from
# it keeps interim CWD-relative cutout paths on the volume too, and creating it
# in the image seeds the named volume's ownership
RUN mkdir /data && chown app:app /data
USER app
WORKDIR /data

EXPOSE 8000
CMD ["uvicorn", "technoeconomics.web.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
