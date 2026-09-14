# syntax=docker/dockerfile:1
# ESGenuine API — Hugging Face Docker Space (see DEPLOY.md).
#
# Builds the FastAPI backend from the private GitHub repo. GITHUB_TOKEN (a fine-grained,
# read-only token stored as a Space secret) is mounted only for the clone step, so it
# never lands in an image layer. The public deployment is read-only: no DATABASE_URL
# (accounts and ingest disabled), no service-role key, no LLM keys.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN --mount=type=secret,id=GITHUB_TOKEN,mode=0444,required=true \
    git clone --depth 1 "https://x-access-token:$(cat /run/secrets/GITHUB_TOKEN)@github.com/iamnishaant/ESGenuine.git" /tmp/repo \
 && cp -r /tmp/repo/backend/. /app/ \
 && rm -rf /tmp/repo /app/ESG_Reports /app/tests

# CPU-only PyTorch first — the default PyPI wheel drags in the multi-GB CUDA stack —
# then the pinned requirements, which find torch already satisfied.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.txt \
      https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HF_HOME=/app/.cache \
    PORT=7860

# Bake the pinned embedding model into the image so a cold start does not download it.
RUN python -c "from model_config import load_embedder; load_embedder()"

# Spaces run the container as uid 1000.
RUN mkdir -p uploads parsed && useradd -m -u 1000 user && chown -R user /app
USER user

EXPOSE 7860
CMD ["sh", "-c", "uvicorn api.server:app --app-dir src --host 0.0.0.0 --port ${PORT:-7860} --workers 1"]
