# ESGenuine backend — multi-stage build (improve_rating B2).
# Targets hosted Supabase (production-first; no local Postgres — see
# external_evaluation_notes.md: single container is right-sized for this corpus).
#
#   docker build -t esgenuine-backend -f backend/Dockerfile backend/
#   docker run --env-file .env -p 8000:8000 esgenuine-backend
#
# Model weights: the small spaCy model is baked in (needed at request time by the
# parser). The heavyweight models (sentence-transformers embedder, en_core_web_trf
# NER, DistilBERT NLI — lazy-loaded by design) download on first use; mount
# /root/.cache as a volume (see docker-compose.yml) so they persist across restarts.

# ── builder: compile wheels once ────────────────────────────────────────────────
FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
# Single resolver pass: a second `pip install --prefix` can't see the first one's
# packages, so it re-resolved the model wheel's old spacy pin and overwrote numpy 2.x
# with 1.26 under numpy-2-built scipy/sklearn (ImportError: numpy._core.multiarray).
# Model wheel 3.8.0 matches requirements' spacy==3.8.11 (same as the host venv).
# Generous network settings: the torch stack pulls multi-hundred-MB wheels and a
# single PyPI read-timeout otherwise kills the whole layer.
RUN PIP_DEFAULT_TIMEOUT=180 pip install --no-cache-dir --prefix=/install --retries 10 \
      -r requirements.txt \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# ── runtime: slim image, no build toolchain ─────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

# curl for the container healthcheck; nothing else beyond libs pip brings.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY src/ ./src/
COPY data/ ./data/
COPY database/ ./database/

# uploads/parsed are runtime artifacts — volumes in compose, created here for bare runs
RUN mkdir -p uploads parsed

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8000

# Bind to $PORT when the host injects one (Render/Railway/Fly/Cloud Run all do);
# default 8000 for local/compose. The healthcheck follows the same variable.
ENV PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS "http://localhost:${PORT}/health" | grep -q '"ready": *true' || exit 1

# 2 workers: job state lives in the DB (commit e67b323), so multi-worker is safe.
# Shell form so ${PORT} expands at runtime (exec form does no substitution).
CMD ["sh", "-c", "uvicorn api.server:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
