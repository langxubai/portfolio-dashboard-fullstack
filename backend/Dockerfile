FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Use the Python runtime provided by the base image instead of downloading the
# older version from .python-version inside the Linux container.
ENV UV_PYTHON=/usr/local/bin/python3.11

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Increase HTTP timeout to prevent download failures (default is 30s)
ENV UV_HTTP_TIMEOUT=300

# Use Tsinghua PyPI mirror for faster and more stable downloads in China if needed
# ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Add the rest of the project source code and install it
# Installing separately from its dependencies allows optimal layer caching
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# py-mini-racer 0.6.0 ships a working AArch64 glibc library under an incorrect
# filename. AkShare looks for libmini_racer.glibc.so, so expose the packaged ARM
# binary under the name expected by its loader. The binary is verified as
# AArch64 during development; this block is a no-op on amd64.
RUN if [ "$(uname -m)" = "aarch64" ]; then \
      racer_dir="$(find /app/.venv/lib -type d -path '*/site-packages/py_mini_racer' -print -quit)"; \
      if [ -n "$racer_dir" ] && [ -f "$racer_dir/armlibmini_racer.glibc.so" ]; then \
        ln -sf armlibmini_racer.glibc.so "$racer_dir/libmini_racer.glibc.so"; \
      fi; \
    fi

EXPOSE 8000

# Run the FastAPI application
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
