from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base
from app.routers import csv_export, display, tasks

# Create all tables on startup
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期:启动时惰性清理画布快照(过期/超量),失败不阻塞启动。"""
    display.cleanup_canvas_store()
    yield


app = FastAPI(
    title="PHM Entity API",
    description="Backend service for managing task entities with SQLite storage.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(tasks.router)
app.include_router(csv_export.router)
app.include_router(display.router)


@app.get("/")
def root():
    return {"message": "PHM Entity API is running"}
