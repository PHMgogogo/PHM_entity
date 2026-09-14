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
        model_code=task_in.model_code,
        work_dir=task_in.work_dir,
        is_global=task_in.is_global,
        algo_cols=task_in.algo_cols,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    _write_agents_md(db_task.work_dir)
    return db_task


def _write_agents_md(work_dir: str) -> None:
    """Write an AGENTS.md guide into the task's working directory (UTF-8)."""
    agents_path = Path(work_dir) / "AGENTS.md"
    agents_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "如果用户提到了算法，那大概率指的是实例。\n\n"
        "外部工具都通过 MCP 提供，可用工具如下：\n"
        "- whoami：查询当前会话（session_id）绑定的任务信息，返回 JSON 字符串，"
        "包含 task_id、name、description、session_id、aircraft_id、instance_id、"
        "model_code、work_dir、is_global、algo_cols 等字段。"
        "需要当前实例的 instance_id 等信息时调用该工具获取。\n"
        "- ezagent：AI 驱动的 ezcli 命令行工具，把自然语言指令翻译为 ezcli highlevel "
        "命令并执行，可完成实例的创建（create）、加载模型（load）、训练（train）、"
        "推理（infer）、状态查询（state）、重启（restart）、删除（delete）等操作。"
        "只需用自然语言描述需求即可。\n"
        "【强制要求】运行中的实例不会自动感知算法的变更。只要你修改了当前算法的任何内容"
        "（例如编辑代码文件、新增或删除文件、重新上传算法、更新算法元数据），"
        "你都必须立即调用 ezagent 工具，让它执行 restart 重启当前实例（除非训练任务正在进行），"
        "使变更生效。这是一个必需步骤，不要等到用户要求或询问，也不要省略："
        "改完算法就重启，然后再向用户报告结果。\n"
        "- search_knowledge：搜索知识库，同时执行 Dense 向量检索和 BM25 关键词检索，"
        "通过 RRF 融合排序返回综合最优结果。用户需要知识查询时调用该工具；"
        "如果查不到，你应该用更模糊的检索词多查询几遍，4遍后跳出。"
    )
    agents_path.write_text(content, encoding="utf-8")


def get_task(db: Session, task_id: int) -> Task | None:
    """Get a single task by its primary key."""
    return db.query(Task).filter(Task.task_id == task_id).first()


def get_all_tasks(db: Session) -> list[Task]:
    """Return all tasks."""
    return db.query(Task).all()


def get_task_by_session_id(db: Session, session_id: str) -> Task | None:
    """Get a single task by its session_id. Returns None if not found."""
    return db.query(Task).filter(Task.session_id == session_id).first()


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


def get_visible_tasks(db: Session, aircraft_id: str) -> tuple[list[Task], bool]:
    """该飞机可见的任务集(专属任务 ∪ 全局任务),按 task_id 去重。

    纯数据库查询,不含任何网络调用;``initialization_required`` 的语义与
    ``get_tasks_by_aircraft`` 一致(该飞机无任何专属任务时为 True)。
    """
    return get_tasks_by_aircraft(db, aircraft_id)


def delete_task_record(db: Session, task_id: int) -> None:
    """删除单条 Task 记录并提交。不存在时静默返回。"""
    db_task = db.query(Task).filter(Task.task_id == task_id).first()
    if db_task is None:
        return
    db.delete(db_task)
    db.commit()

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
    # 「清空对话」会换新 session_id 重建会话，此时工作目录下的 AGENTS.md
    # 必须一并重写，否则新会话拿不到实例上下文（同 create_task）。
    session_changed = "session_id" in update_data and update_data["session_id"] != db_task.session_id
    for field, value in update_data.items():
        setattr(db_task, field, value)
    db.commit()
    db.refresh(db_task)
    if session_changed and db_task.work_dir:
        _write_agents_md(db_task.work_dir, db_task.instance_id)
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
