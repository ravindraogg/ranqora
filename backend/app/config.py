import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file in development (ignored in production Docker — use HF Secrets)
load_dotenv()

# ─── Environment Detection ──────────────────────────────────────
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development") == "production"
IS_HF_SPACE = os.getenv("SPACE_ID") is not None  # HuggingFace auto-sets this

# ─── HuggingFace ─────────────────────────────────────────────────
HUGGINGFACE_API_URL = "https://huggingface.co/api/datasets"

# ─── Embedding ───────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

# ─── Retrieval Limits ────────────────────────────────────────────
MAX_DATASETS_TO_FETCH = 700
TOP_K_RESULTS = 12

# ─── API Keys (loaded from env — never hardcoded) ───────────────
# In HuggingFace Spaces: Settings → Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
KAGGLE_API_TOKEN = os.getenv("KAGGLE_API_TOKEN", "")
KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "")
KAGGLE_KEY = os.getenv("KAGGLE_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ─── Graph Database (Phase 4) ───────────────────────────────────
# In HF Spaces: Neo4j is optional. Falls back to in-memory NetworkX.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "datasetgraph")

# ─── CORS Origins (restrict in production) ──────────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# ─── Rate Limiting ──────────────────────────────────────────────
# Max requests per IP per minute (0 = disabled)
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30" if IS_PRODUCTION else "0"))

# ─── Startup Validation ────────────────────────────────────────
def validate_config():
    """Log warnings for missing credentials at startup."""
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY (LLM features disabled)")
    if not KAGGLE_API_TOKEN and not (KAGGLE_USERNAME and KAGGLE_KEY):
        missing.append("KAGGLE_API_TOKEN or KAGGLE_USERNAME+KAGGLE_KEY (Kaggle search disabled)")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN (GitHub rate limit: 10 req/min)")

    if missing:
        logger.warning("Missing env vars: " + " | ".join(missing))
    
    if IS_PRODUCTION and ALLOWED_ORIGINS == ["*"]:
        logger.warning("SECURITY: CORS allow_origins='*' in production. Set ALLOWED_ORIGINS env var.")
    
    logger.info(f"Environment: {'production' if IS_PRODUCTION else 'development'} | HF Space: {IS_HF_SPACE}")

validate_config()