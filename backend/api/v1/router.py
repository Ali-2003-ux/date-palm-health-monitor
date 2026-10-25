"""Aggregated /api/v1 router."""

from fastapi import APIRouter

from backend.api.v1 import auth, inspections, palms

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(palms.router)
api_router.include_router(inspections.router)
