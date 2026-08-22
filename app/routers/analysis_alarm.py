from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AnalysisAlarm as AnalysisAlarmModel
from app.schemas import (
    AnalysisAlarm,
    AnalysisAlarmCreate,
    AnalysisAlarmDeleteRequest,
)

router = APIRouter(prefix="/api/analysis/alarms", tags=["analysis_alarms"])


def _to_response(a: AnalysisAlarmModel) -> AnalysisAlarm:
    """把 ORM 实体转为响应 schema:cols 拆分为列表、range 合并为元组。"""
    return AnalysisAlarm(
        alarm_id=a.alarm_id,
        instance_id=a.instance_id,
        cols=[c for c in a.cols.split(",") if c],
        range=(a.range_start, a.range_end),
        message=a.message,
        raw_data=a.raw_data,
        time=a.time,
        level=a.level,
    )


@router.post("/", response_model=list[AnalysisAlarm], status_code=201)
def create_analysis_alarms(
    payload: list[AnalysisAlarmCreate], db: Session = Depends(get_db)
):
    """批量新增报警:为每个 alarm 分配自增的 alarm_id 主键。"""
    created: list[AnalysisAlarmModel] = []
    for item in payload:
        analysis_alarm = AnalysisAlarmModel(
            instance_id=item.instance_id,
            cols=",".join(item.cols),
            range_start=item.range[0],
            range_end=item.range[1],
            message=item.message,
            raw_data=item.raw_data,
            time=item.time,
            level=item.level,
        )
        db.add(analysis_alarm)
        created.append(analysis_alarm)
    db.commit()
    for analysis_alarm in created:
        db.refresh(analysis_alarm)
    return [_to_response(a) for a in created]


@router.get("/", response_model=list[AnalysisAlarm])
def list_analysis_alarms(
    instance_id: str | None = Query(
        None, pattern=r"^[A-Za-z0-9_-]*$", description="Filter by instance_id"
    ),
    raw_data: str | None = Query(None, description="Filter by raw_data"),
    db: Session = Depends(get_db),
):
    """查询报警;可按 instance_id / raw_data 精确过滤。"""
    query = db.query(AnalysisAlarmModel)
    if instance_id:
        query = query.filter(AnalysisAlarmModel.instance_id == instance_id)
    if raw_data:
        query = query.filter(AnalysisAlarmModel.raw_data == raw_data)
    return [_to_response(a) for a in query.all()]


@router.delete("/", status_code=200)
def delete_analysis_alarms(
    payload: AnalysisAlarmDeleteRequest, db: Session = Depends(get_db)
):
    """按 alarm_id 批量删除报警(不存在的 id 自动跳过)。"""
    deleted = (
        db.query(AnalysisAlarmModel)
        .filter(AnalysisAlarmModel.alarm_id.in_(payload.alarm_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"detail": f"{deleted} alarms deleted"}
