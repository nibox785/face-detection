import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
<<<<<<< HEAD
from datetime import datetime, timezone
import datetime
=======
from datetime import datetime
>>>>>>> 9b321e4968c99f488f7cef3ad04a52b68b0efbf2
import os
import numpy as np

from backend.database.db import init_db
from backend.api.routes import router, update_embeddings_cache, embeddings_cache, limiter, HAS_SLOWAPI
from backend.services.faiss_search import FAISSEmbeddingIndex

# ====================== LOGGING CONFIG ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("face-attendance")

# ====================== GLOBAL FAISS INDEX ======================
faiss_index: FAISSEmbeddingIndex = None


def warmup_ai_models():
    """Warm up detect/embedding models to reduce first-request latency."""
    enabled = os.getenv("MODEL_WARMUP_ENABLED", "1").strip() in {"1", "true", "True"}
    if not enabled:
        logger.info("⏭️ MODEL_WARMUP_ENABLED=0 -> skip model warm-up")
        return

    # Keep test runs fast and deterministic.
    if os.getenv("PYTEST_CURRENT_TEST"):
        logger.info("⏭️ Pytest detected -> skip model warm-up")
        return

    try:
        logger.info("🔥 Warming up AI models (detect + embedding)...")
        from face_engine.facenet.detect import detect_faces
        from face_engine.facenet.embedding import get_embedding

        dummy_frame = np.zeros((160, 160, 3), dtype=np.uint8)
        detect_faces(dummy_frame)

        dummy_face = np.full((160, 160, 3), 127, dtype=np.uint8)
        get_embedding(dummy_face)
        logger.info("✅ AI model warm-up completed")
    except Exception as e:
        logger.warning(f"⚠️ AI model warm-up skipped due to error: {str(e)}")

def init_faiss_index():
    """Initialize FAISS index with current embeddings cache"""
    global faiss_index
    try:
        faiss_index = FAISSEmbeddingIndex(dim=512)
        if embeddings_cache:
            faiss_index.build(embeddings_cache)
            logger.info(f"✅ FAISS index initialized with {len(embeddings_cache)} embeddings")
        else:
            logger.warning("⚠️ FAISS index created but no embeddings yet")
    except Exception as e:
        logger.error(f"❌ Failed to initialize FAISS index: {str(e)}")
        faiss_index = None

# ====================== LIFESPAN ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo database
    logger.info("🚀 Khởi tạo database...")
    init_db()
    
    # Load embeddings cache
    logger.info("📥 Đang load embeddings từ database...")
    update_embeddings_cache()
    
    # Initialize FAISS index
    logger.info("⚡ Initializing FAISS index...")
    init_faiss_index()

    # Warm up AI models to avoid cold-start latency on first request
    warmup_ai_models()
    
    yield
    
    logger.info("👋 Application shutdown")

# ====================== FASTAPI APP ======================
app = FastAPI(
    title="Face Attendance System",
    description="Hệ thống điểm danh bằng nhận diện khuôn mặt",
    version="1.0.0",
    lifespan=lifespan
)

# ⚠️ Register rate limiter if available
if HAS_SLOWAPI and limiter:
    app.state.limiter = limiter
    logger.info("✅ Rate limiter registered (60 req/min per IP)")
else:
    logger.warning("⚠️ Rate limiting not available - consider installing slowapi")

# ====================== CORS CONFIG ======================
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',')
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"✅ CORS configured for origins: {ALLOWED_ORIGINS}")

# Include routes
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": "Face Attendance API is running",
        "version": "1.0.0",
        "status": "healthy",
        "embeddings_count": len(embeddings_cache),
        "faiss_index": faiss_index.get_index_info() if faiss_index else {"status": "not_initialized"}
    }


@app.get("/debug/faiss-info")
async def faiss_info():
    """Get FAISS index information"""
    if faiss_index is None:
        return {"status": "not_initialized"}
    return {
        "status": "active",
        "info": faiss_index.get_index_info()
    }



@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "embeddings_count": len(embeddings_cache),
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat()
    }