from fastapi import APIRouter

from .auth_routes import auth_router
from .register_routes import register_router
from .recognize_routes import recognize_router
from .attendance_routes import attendance_router
from .websocket_routes import websocket_router
from .common import update_embeddings_cache, embeddings_cache, limiter, HAS_SLOWAPI

router = APIRouter()
router.include_router(auth_router)
router.include_router(register_router)
router.include_router(recognize_router)
router.include_router(attendance_router)
router.include_router(websocket_router)

__all__ = [
    "router",
    "update_embeddings_cache",
    "embeddings_cache",
    "limiter",
    "HAS_SLOWAPI",
]
