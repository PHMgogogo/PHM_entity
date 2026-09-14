"""任务对账:以 instance_id 为核心判据清理失效任务及其 OpenCode 会话。

对账流程:
1. 取该飞机可见的任务集(专属任务 ∪ 全局任务);
2. 查询实例服务获取存活实例集合;
3. 逐个判定任务:instance_id 为空、或不在存活集合中 → 失效;
4. 对失效任务:先尽力删除其 OpenCode 会话,再删除本地记录;
5. 返回存活任务与初始默认标志。

实例服务不可达时降级为「不清理」,原样返回任务,避免误删。
"""
from sqlalchemy.orm import Session

from app import crud
from app.models import Task
from app.services import instance_client, opencode_client


async def reconcile_aircraft(
    db: Session, aircraft_id: str
) -> tuple[list[Task], bool, bool]:
    """对指定飞机执行对账。

    返回 ``(存活任务, initialization_required, stale_check_failed)``:
    - ``存活任务``:清理后仍有效的任务列表;
    - ``initialization_required``:该飞机是否仍无任何专属任务;
    - ``stale_check_failed``:实例服务不可用、本次未执行清理时为 True。
    """
    tasks, _ = crud.get_visible_tasks(db, aircraft_id)

    alive = await instance_client.fetch_alive_instance_ids()
    if alive is None:
        # 降级:无法判定存活状态,不做任何删除,原样返回。
        return tasks, _initialization_required(db, aircraft_id), True

    survivors: list[Task] = []
    for task in tasks:
        if task.instance_id and task.instance_id in alive:
            survivors.append(task)
            continue
        # 失效任务:先删 OpenCode 会话(best-effort),再删本地记录。
        if task.session_id:
            await opencode_client.delete_session(task.session_id, task.work_dir)
        crud.delete_task_record(db, task.task_id)

    return survivors, _initialization_required(db, aircraft_id), False


def _initialization_required(db: Session, aircraft_id: str) -> bool:
    """该飞机是否仍无任何专属任务(删除后重新判定)。"""
    return (
        db.query(Task).filter(Task.aircraft_id == aircraft_id).first() is None
    )
