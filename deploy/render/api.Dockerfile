# ESGenuine public API image — read-only, no PyTorch (see DEPLOY.md).
#
# Build context is backend/ (render.yaml: dockerContext ./backend).
#
# Leaves out the two requirements that pull in PyTorch — sentence-transformers and
# spacy-transformers. Only PDF ingest and the /audit/ask Q&A use them, and the public
# deployment disables both (no DATABASE_URL, no LLM keys). Every dashboard read endpoint
# was verified to return 200 with PyTorch absent, at ~190 MB resident against ~340 MB
# with it — which is what lets this run on Render's free 512 MB plan.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN grep -vE '^(sentence-transformers|spacy-transformers)' requirements.txt > requirements-api.txt \
 && pip install --no-cache-dir -r requirements-api.txt \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

COPY src/ ./src/
COPY data/ ./data/
COPY database/ ./database/
RUN mkdir -p uploads parsed

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    API_READ_ONLY=1 \
    PORT=8000

EXPOSE 8000
# One worker: the free plan has 512 MB and one worker needs ~190 MB.
CMD ["sh", "-c", "uvicorn api.server:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
