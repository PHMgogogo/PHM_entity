from fastapi import FastAPI

from app.database import engine, Base
from app.routers import csv_export, tasks

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PHM Entity API",
    description="Backend service for managing task entities with SQLite storage.",
    version="0.1.0",
)

app.include_router(tasks.router)
app.include_router(csv_export.router)


@app.get("/")
def root():
    return {"message": "PHM Entity API is running"}
