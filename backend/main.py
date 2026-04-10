import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import datetime
import os

from backend.api.routes import router
from backend.database.db import init_db, get_all_embeddings

# ====================== LOGGING CONFIG ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("face-attendance")

# ====================== GLOBAL CACHE ======================
embeddings_cache: list = []

# ====================== LIFESPAN ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo database
    logger.info("🚀 Khởi tạo database...")
    init_db()
    
    # Load embeddings cache
    logger.info("📥 Đang load embeddings từ database...")
    global embeddings_cache
    embeddings_cache.clear()
    embeddings_cache.extend(get_all_embeddings())
    
    logger.info(f"✅ Đã load {len(embeddings_cache)} embeddings vào cache")
    
    yield
    
    logger.info("👋 Application shutdown")

# ====================== FASTAPI APP ======================
app = FastAPI(
    title="Face Attendance System",
    description="Hệ thống điểm danh bằng nhận diện khuôn mặt",
    version="1.0.0",
    lifespan=lifespan
)

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
        "embeddings_count": len(embeddings_cache)
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "embeddings_count": len(embeddings_cache),
        "timestamp": datetime.now().isoformat()
    }