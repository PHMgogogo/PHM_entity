from pathlib import Path

from sqlalchemy.orm import Session

from app.models import AnalysisPipeline, Task
from app.schemas import (
    AnalysisPipelineCreate,
    AnalysisPipelineUpdate,
    TaskCreate,
    TaskUpdate,
)


def create_task(db: Session, task_in: TaskCreate) -> Task:
    """Create a new task and return it."""
    db_task = Task(
        name=task_in.name,
        description=task_in.description,
        session_id=task_in.session_id,
        aircraft_id=task_in.aircraft_id,
        instance_id=task_in.instance_id,
        work_dir=task_in.work_dir,
        is_global=task_in.is_global,
        default=task_in.default,
        algo_cols=task_in.algo_cols,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    _write_agents_md(db_task.work_dir, db_task.instance_id)
    return db_task


def _write_agents_md(work_dir: str, instance_id: str) -> None:
    """Write an AGENTS.md guide into the task's working directory (UTF-8)."""
    agents_path = Path(work_dir) / "AGENTS.md"
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"当前实例的instance_id为{instance_id}，"
        "你可以通过调用工具实现对当前目录下实例的"
        "启动，停止，重启，训练，推理，状态获取等操作。"
        "如果用户提到了算法，那大概率指的是实例。"
        "如果用户需要知识查询，请调用knowledge_retrieval工具。"
        "如果查不到，你应该用更模糊的检索词多查几遍，4遍跳出"
    )
    agents_path.write_text(content, encoding="utf-8")


def get_task(db: Session, task_id: int) -> Task | None:
    """Get a single task by its primary key."""
    return db.query(Task).filter(Task.task_id == task_id).first()


def get_all_tasks(db: Session) -> list[Task]:
    """Return all tasks."""
    return db.query(Task).all()


def search_tasks(db: Session, keyword: str) -> list[Task]:
    """Return tasks whose name or description contains the keyword (case-insensitive)."""
    pattern = f"%{keyword}%"
    return (
        db.query(Task)
        .filter(
            Task.name.ilike(pattern) | Task.description.ilike(pattern)
        )
        .all()
    )


def get_tasks_by_aircraft(db: Session, aircraft_id: str) -> tuple[list[Task], bool]:
    """Return the union of tasks for the given aircraft_id and all global tasks.

    Returns ``(tasks, initialization_required)`` where ``initialization_required``
    is True when no task belongs to the given aircraft_id — the returned list may
    still be non-empty because global tasks are always included. Tasks that are
    both global and belong to the aircraft are deduplicated by ``task_id``.
    """
    aircraft_tasks = db.query(Task).filter(Task.aircraft_id == aircraft_id).all()
    initialization_required = len(aircraft_tasks) == 0

    seen_ids = {task.task_id for task in aircraft_tasks}
    tasks = list(aircraft_tasks)
    for task in db.query(Task).filter(Task.is_global.is_(True)).all():
        if task.task_id not in seen_ids:
            tasks.append(task)
            seen_ids.add(task.task_id)
    return tasks, initialization_required

def delete_task(db: Session, task_id: int) -> bool:
    """Delete a task by its primary key. Returns True if deleted, False if not found."""
    db_task = db.query(Task).filter(Task.task_id == task_id).first()
    if db_task is None:
        return False
    db.delete(db_task)
    db.commit()
    return True


def update_task(db: Session, task_id: int, task_in: TaskUpdate) -> Task | None:
    """Update a task by its primary key with the provided fields. Returns the updated task, or None if not found."""
    db_task = db.query(Task).filter(Task.task_id == task_id).first()
    if db_task is None:
        return None
    update_data = task_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_task, field, value)
    db.commit()
    db.refresh(db_task)
    return db_task


def create_analysis_pipeline(
    db: Session, pipeline_in: AnalysisPipelineCreate
) -> AnalysisPipeline:
    """Create a new analysis pipeline and return it."""
    db_pipeline = AnalysisPipeline(
        aircraft_id=pipeline_in.aircraft_id,
        pipeline_id=pipeline_in.pipeline_id,
    )
    db.add(db_pipeline)
    db.commit()
    db.refresh(db_pipeline)
    return db_pipeline


def get_analysis_pipeline(db: Session, pipeline_id: int) -> AnalysisPipeline | None:
    """Get a single analysis pipeline by its primary key."""
    return (
        db.query(AnalysisPipeline)
        .filter(AnalysisPipeline.id == pipeline_id)
        .first()
    )


def get_all_analysis_pipelines(db: Session) -> list[AnalysisPipeline]:
    """Return all analysis pipelines."""
    return db.query(AnalysisPipeline).all()


def get_analysis_pipelines_by_aircraft(
    db: Session, aircraft_id: str
) -> list[AnalysisPipeline]:
    """Return all analysis pipelines for the given aircraft_id."""
    return (
        db.query(AnalysisPipeline)
        .filter(AnalysisPipeline.aircraft_id == aircraft_id)
        .all()
    )


def update_analysis_pipeline(
    db: Session, pipeline_id: int, pipeline_in: AnalysisPipelineUpdate
) -> AnalysisPipeline | None:
    """Update an analysis pipeline by its primary key with the provided fields.
    Returns the updated pipeline, or None if not found."""
    db_pipeline = get_analysis_pipeline(db, pipeline_id)
    if db_pipeline is None:
        return None
    update_data = pipeline_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_pipeline, field, value)
    db.commit()
    db.refresh(db_pipeline)
    return db_pipeline


def delete_analysis_pipeline(db: Session, pipeline_id: int) -> bool:
    """Delete an analysis pipeline by its primary key.
    Returns True if deleted, False if not found."""
    db_pipeline = get_analysis_pipeline(db, pipeline_id)
    if db_pipeline is None:
        return False
    db.delete(db_pipeline)
    db.commit()
    return True
