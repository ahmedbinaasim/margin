FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_NO_CACHE_DIR=on

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# System libs needed by trafilatura (lxml), httpx (h2), and torch (sentence-transformers).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first to maximize Docker layer cache.
# By default we DO NOT install the `fallback` extra — torch + sentence-transformers
# adds ~2GB. Build with `--build-arg WITH_FALLBACK=1` to include the offline path.
ARG WITH_FALLBACK=0
COPY pyproject.toml ./
RUN uv venv /opt/venv && \
    if [ "$WITH_FALLBACK" = "1" ]; then \
      UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --no-dev --no-install-project --extra fallback; \
    else \
      UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --no-dev --no-install-project; \
    fi

ENV PATH="/opt/venv/bin:$PATH"

# Copy source and install the package itself.
COPY src ./src
RUN UV_PROJECT_ENVIRONMENT=/opt/venv uv pip install --no-deps .

# Pre-download the local fallback model only when WITH_FALLBACK was used.
RUN if [ "$WITH_FALLBACK" = "1" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')" || true; \
    fi

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3); sys.exit(0 if r.status==200 else 1)"

CMD ["uvicorn", "margin_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
