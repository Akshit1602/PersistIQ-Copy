from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from continum.config import settings
from continum.userui.routes import (
    approval_router,
    chat_router,
    datasets_router,
    experiments_router,
    modules_router,
    projects_router,
    suggestions_router,
)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Continum AI Retail Experimentation Engine & MatchView Backend",
)

# Enable CORS for local Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(chat_router)
app.include_router(datasets_router)
app.include_router(experiments_router)
app.include_router(approval_router)
app.include_router(modules_router)
app.include_router(projects_router)
app.include_router(suggestions_router)


@app.get("/health", tags=["Health Check"])
async def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "deploy_target": "databricks" if settings.is_databricks else "local",
    }


# ---------------------------------------------------------------------------
# SPA serving (Databricks Apps)
#
# On Databricks Apps this process serves the built frontend as well as the API,
# so the SPA is same-origin. Registered LAST so every /api/* route and /health
# above still win, and guarded on the build existing so local dev — where Vite
# serves the frontend on its own port and frontend/dist may be absent — starts
# normally.
# ---------------------------------------------------------------------------
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_spa(path: str):
        requested = _DIST / path
        if path and requested.is_file():
            return FileResponse(requested)
        # Unknown paths fall through to index.html so client-side routing works.
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("continum.userui.app:app", host="0.0.0.0", port=8000, reload=True)
