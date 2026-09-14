from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.database import engine, Base
from app.routers import (
    analysis_alarm,
    analysis_model,
    analysis_pipeline,
    analysis_result,
    csv_export,
    display,
    tasks,
)

# Create all tables on startup
Base.metadata.create_all(bind=engine)


def _ensure_columns() -> None:
    """为已存在的表补齐新增列(SQLite 无迁移框架,create_all 不会修改已有表)。

    仅追加缺失列,不改动/删除已有列;失败不阻塞启动。
    """
    additions = {
        "tasks": {"model_code": "VARCHAR(255) NOT NULL DEFAULT ''"},
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name in present:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


_ensure_columns()


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
app.include_router(analysis_model.router)
app.include_router(analysis_result.router)
app.include_router(analysis_alarm.router)
app.include_router(analysis_pipeline.router)
app.include_router(csv_export.router)
app.include_router(display.router)


@app.get("/")
def root():
    return {"message": "PHM Entity API is running"}
