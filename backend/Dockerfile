# ─── HuggingFace Spaces Docker Deployment ────────────────────────────────────
# Build: docker build -t ranqora-backend .
# Run:   docker run -p 7860:7860 --env-file .env ranqora-backend
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# ── Security: Don't run as root ──────────────────────────────────────────────
RUN useradd -m -u 1000 appuser

# ── System dependencies ─────────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies (cached layer) ──────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Pre-download the embedding model during build (not at runtime) ──────────
# This avoids a 30-60s delay on first request in production.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

# ── Copy application code ──────────────────────────────────────────────────
COPY . .

# ── Security: Remove sensitive files from the image ─────────────────────────
RUN rm -f .env .env.local .env.* && \
    rm -f *.log *.jsonl && \
    rm -rf __pycache__ **/__pycache__ .git

# ── Security: Set proper file permissions ────────────────────────────────────
RUN chown -R appuser:appuser /app
USER appuser

# ── HuggingFace Spaces expects port 7860 ────────────────────────────────────
ENV PORT=7860
EXPOSE 7860

# ── Health check ────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# ── Start server ─────────────────────────────────────────────────────────────
# HuggingFace Spaces: must listen on 0.0.0.0:7860
# Workers=1 because embedding model is loaded per-process (shared memory)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$PORT", "--workers", "1", "--timeout-keep-alive","130"]