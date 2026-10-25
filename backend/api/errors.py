"""Maps domain exceptions to clean HTTP error responses."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.core.logging import get_logger
from backend.services.vision.results import InferenceError, InvalidImageError

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach domain exception handlers to the application."""

    @app.exception_handler(InvalidImageError)
    async def invalid_image_handler(
        request: Request, exc: InvalidImageError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": f"Invalid image: {exc}"},
        )

    @app.exception_handler(InferenceError)
    async def inference_error_handler(
        request: Request, exc: InferenceError
    ) -> JSONResponse:
        logger.error("Inference failed on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": (
                    "Diagnosis service is temporarily unavailable. "
                    "Please retry shortly."
                )
            },
        )
