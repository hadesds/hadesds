from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from devpulse.admin_dashboard.routes import api, public
from devpulse.config import get_settings
from devpulse.observability.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    s = get_settings()
    app = FastAPI(title="DevPulse AI", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list(), allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    app.include_router(public)
    app.include_router(api)

    dist = Path(s.frontend_dist)
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Não encontrado"}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
