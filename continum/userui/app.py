from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from continum.config import settings
from continum.userui.routes import chat_router, experiments_router, approval_router

app = FastAPI(
    title=settings.APP_NAME,
    version="0.2.0",
    description="Backend serving layer for MatchView Copilot & Retail Experimentation Assistant."
)

# Enable CORS for MatchView App UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust origin URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(chat_router)
app.include_router(experiments_router)
app.include_router(approval_router)


@app.get("/health")
async def health_check():
    return {"status": "online", "app": settings.APP_NAME, "version": "0.2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("continum.userui.app:app", host="0.0.0.0", port=8000, reload=True)