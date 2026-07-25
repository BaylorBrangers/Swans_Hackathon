# syntax=docker/dockerfile:1

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# LightGBM requires the GNU OpenMP runtime on Debian-based images.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the uv executable from Astral's official image.
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

WORKDIR /app

# Install dependencies before copying application code so Docker can cache this layer.
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

COPY . .

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
