"""v1 router aggregator. Mount point for every /api/v1/* router."""

from fastapi import APIRouter

from app.api.v1.routers import auth, brand_voices, content, health, improve, meta

v1_router = APIRouter()
v1_router.include_router(health.router)
v1_router.include_router(meta.router)
v1_router.include_router(auth.router)
v1_router.include_router(content.router)
v1_router.include_router(improve.router)
v1_router.include_router(brand_voices.router)
