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
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
 && pip install --no-cache-dir --prefix=/install \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

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

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:8000/health | grep -q '"ready": *true' || exit 1

# 2 workers: job state lives in the DB (commit e67b323), so multi-worker is safe.
CMD ["uvicorn", "api.server:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
