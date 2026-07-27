from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from continum.config import settings
from continum.userui.routes import chat_router, experiments_router, approval_router

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Continum AI Retail Experimentation Engine & MatchView Backend"
)

# Enable CORS for local Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(chat_router)
app.include_router(experiments_router)
app.include_router(approval_router)


@app.get("/health", tags=["Health Check"])
async def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("continum.userui.app:app", host="0.0.0.0", port=8000, reload=True)