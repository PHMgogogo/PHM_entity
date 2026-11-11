"""以「时序数据查询」为数据源的训练 / 推理(前端时序面板的「去训练 / 去推理」)。

三方(航新/633)单机没有本地 CSV 表,训练 / 推理的数据只能来自
``POST /csv/query-timeseries``。与 csv_export.py 的 ``/tasks/train``、
``/tasks/infer`` 相比,差别只在取数那一步:

- csv_export: ``table_name`` → CSV 服务导列 → CSV 文本
- 本模块    : ``sortieId`` + ``airplaneType`` → 时序查询 → CSV 文本

取到 CSV 文本后同样 POST 给算法实例的 ``/{instance_id}/{train|infer}``,
算法侧载荷与 csv_export 保持一致。
"""

import csv
import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import (
    ANALYSIS_MODELS_DIR,
    ALGO_BASE,
    CSV_MAPPINGS_ENDPOINT,
    CSV_OVERVIEW_ENDPOINT,
    CSV_TIMESERIES_ENDPOINT,
    INSTANCE_LIST_ENDPOINT,
)
from app.database import get_db
from app.models import AnalysisModel
from app.schemas import AnalysisModelResponse

router = APIRouter(prefix="/api", tags=["timeseries-job"])

# 进程级共享客户端,构造理由与 csv_export 相同(见该模块顶部注释):
# 默认 30s 供取数用;训练 / 推理及模型保存使用显式的长超时。
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0),
    trust_env=False,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)
_ALGO_TIMEOUT = httpx.Timeout(1800.0, connect=10.0)

# 整列下发的列数上限:再宽就退回「仅所选列」,避免作业 CSV 被表宽拖爆
_MAX_DATASET_COLUMNS = 64


class TimeseriesJobRequest(BaseModel):
    """``POST /api/tasks/{train,infer}-timeseries`` 的请求体。

    定位字段沿用 ``POST /csv/query-timeseries`` 的 camelCase(airplaneType /
    sortieId / aircraftNumber / startTime / endTime),作业参数沿用既有
    ``/tasks/train``、``/tasks/infer`` 的 snake_case —— 两段语义不同,不强行统一。
    """

    airplaneType: str = Field(..., description="机型;后端据此路由到唯一平台")
    sortieId: str = Field(..., description="架次标识,取自 /aircraft/sorties 的 sortieKey")
    aircraftNumber: str | None = Field(None, description="机号,仅作路由索引的补充")
    sortieNumber: str | None = Field(None, description="架次号,仅用于模型元数据")
    flightDate: str | None = Field(None, description="飞行日期,仅用于模型元数据")
    sourceType: Literal["local", "external"] | None = Field(
        None, description="数据来源类型,仅用于模型元数据"
    )
    startTime: str | None = Field(None, description="取数起始,留空按架次起止推算")
    endTime: str | None = Field(None, description="取数结束,留空按架次起止推算")
    data_cols: list[str] = Field(..., description="输入列(时序属性名)")
    label_cols: list[str] = Field(
        default_factory=list, description="标签列;留空则由算法把输入列当标签"
    )
    instance_id: str = Field(..., description="承载作业的算法实例")
    batch_size: int = Field(1, ge=1, description="Batch size")
    epoch: int = Field(1, ge=1, description="训练轮数;仅训练使用")
    learning_rate: float = Field(1e-3, gt=0, description="学习率;仅训练使用")
    device: Literal["cpu", "cuda"] = Field("cpu", description="Compute device")
    detach: bool = Field(False, description="True 时异步执行,立即返回空结果")
    task_id: int | None = Field(None, description="发起作业的会话 ID")
    task_name: str | None = Field(None, description="发起作业的会话名称")
    model_name: str | None = Field(None, max_length=255, description="训练成功后保存的模型名称")
    model_description: str | None = Field(
        None, max_length=2000, description="模型备注"
    )


def _upstream_detail(resp: httpx.Response) -> str:
    """取上游响应里人可读的原因:数据服务用 ``message``,算法服务用 ``detail``。"""
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("message", "detail"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"HTTP {resp.status_code}: {resp.text[:200]}"


async def _local_dataset_info(req: TimeseriesJobRequest) -> tuple[str, list[str]]:
    """本地架次绑定数据表的表名与整列名。

    场景模型(起落架、涡扇 RUL 等)的契约是「表单只勾输入列与标签列,但 CSV 里要
    带上仅用于动作/轨迹切分与基线统计的辅助列」(如 ``field.episode``、
    ``field.unit``,模型会忽略多余列)。故这里按架次找到绑定的 csv_xxx 表,把它的
    列名一并取回,由模型自行取用。

    三方架次或任何一步失败时返回空信息:取不到列只影响「能不能带辅助列」,
    不该让作业失败。
    """
    try:
        mappings = (
            await _http_client.get(CSV_MAPPINGS_ENDPOINT, params={"sortieId": req.sortieId})
        ).json()
        if not isinstance(mappings, list):
            return "", []
        # 一个架次可能绑多张表,取 mappingId 最大的一张(与前端 pickDeviceMapping 同规则)
        own = [
            item
            for item in mappings
            if isinstance(item, dict)
            and item.get("csvTableName")
            and (req.aircraftNumber is None or item.get("aircraftNumber") == req.aircraftNumber)
        ]
        if not own:
            return "", []
        mapping = max(own, key=lambda item: item.get("mappingId") or 0)
        table_name = str(mapping.get("csvTableName") or "")

        overview = (
            await _http_client.get(
                CSV_OVERVIEW_ENDPOINT,
                params={"modelCode": req.airplaneType, "mappingId": mapping.get("mappingId")},
            )
        ).json()
        if not isinstance(overview, dict):
            return table_name, []
        # 用 columnTypes 而非 dataColumns:前者与实际能查到的列名一致(见前端 propertyCandidates)
        columns = [
            name for name in (overview.get("columnTypes") or {}) if isinstance(name, str) and name.strip()
        ]
        return table_name, columns if len(columns) <= _MAX_DATASET_COLUMNS else []
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return "", []


async def _fetch_timeseries_csv(req: TimeseriesJobRequest) -> tuple[str, str]:
    """按架次取时序数据,拼成算法侧可直接 read_csv 的文本。

    列集 = 所选列(data_cols + label_cols)∪ 本地表整列集,后者只作补充:
    场景模型靠它拿到切分用的辅助列,通用模型按 data_cols / label_cols 自取。
    所选列在返回里缺一列就报错;补充列拿不到则不阻塞作业。
    """
    selected = [*req.data_cols, *req.label_cols]
    data_table_name, local_columns = await _local_dataset_info(req)
    columns = list(dict.fromkeys([*selected, *local_columns]))
    if not columns:
        raise HTTPException(status_code=400, detail="请至少选择一个数据列")

    query: dict[str, Any] = {
        "airplaneType": req.airplaneType,
        "sortieId": req.sortieId,
        "paralist": columns,
    }
    for field in ("aircraftNumber", "startTime", "endTime"):
        value = getattr(req, field)
        if value:
            query[field] = value

    try:
        resp = await _http_client.post(CSV_TIMESERIES_ENDPOINT, json=query)
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="无法连接时序数据服务")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="时序数据服务响应超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"时序数据查询失败: {_upstream_detail(e.response)}"
        )

    try:
        payload = (resp.json() or {}).get("data") or {}
    except ValueError:
        raise HTTPException(status_code=502, detail="时序数据服务返回了非 JSON 响应")

    parameters = payload.get("parameters") or []
    if not parameters:
        raise HTTPException(status_code=404, detail="该架次没有查询到时序数据")

    values_by_name: dict[str, list[Any]] = {}
    for item in parameters:
        name = str(item.get("name") or "").strip().lower()
        if name:
            values_by_name[name] = item.get("values") or []

    missing = [c for c in selected if c.strip().lower() not in values_by_name]
    if missing:
        raise HTTPException(
            status_code=502, detail="时序数据缺少所选列: " + "、".join(missing)
        )
    present = [c for c in columns if c.strip().lower() in values_by_name]
    if not present:
        raise HTTPException(status_code=404, detail="该架次没有查询到时序数据")

    series = [values_by_name[c.strip().lower()] for c in present]
    row_count = max([len(payload.get("timestamps") or [])] + [len(s) for s in series])

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(present)
    for index in range(row_count):
        writer.writerow([s[index] if index < len(s) else None for s in series])
    return buffer.getvalue(), data_table_name


def _safe_model_filename(name: str) -> str:
    stem = re.sub(r"[^\w.\-]", "_", name.strip(), flags=re.UNICODE).strip("._")
    return f"{stem or 'model'}.pth"


async def _algorithm_metadata(instance_id: str) -> tuple[str, str]:
    """Read the algorithm identity from PMGR; metadata failures must not fail training."""
    try:
        resp = await _http_client.get(INSTANCE_LIST_ENDPOINT, timeout=10.0)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return "", ""
        for item in payload:
            if not isinstance(item, dict) or item.get("id") != instance_id:
                continue
            template = item.get("template") or {}
            algorithm = template.get("algorithm") or {}
            algorithm_id = str(algorithm.get("id") or "")
            return algorithm_id, algorithm_id
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return "", ""


async def _persist_trained_model(
    db: Session,
    req: TimeseriesJobRequest,
    data_table_name: str,
) -> AnalysisModel:
    """Save the loaded model from the worker and register its metadata."""
    model_name = (req.model_name or "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="训练成功后保存模型时必须填写模型名称")

    algorithm_id, algorithm_name = await _algorithm_metadata(req.instance_id)
    saved_at = datetime.now()
    db_model = AnalysisModel(
        name=model_name,
        aircraft_number=(req.aircraftNumber or "").strip(),
        model_code=req.airplaneType.strip(),
        sortie_key=req.sortieId.strip(),
        sortie_number=(req.sortieNumber or "").strip(),
        flight_date=(req.flightDate or "").strip(),
        source_type=req.sourceType or ("local" if data_table_name else "external"),
        data_table_name=data_table_name,
        data_range_start=(req.startTime or "").strip(),
        data_range_end=(req.endTime or "").strip(),
        data_columns=list(req.data_cols),
        label_columns=list(req.label_cols),
        instance_id=req.instance_id,
        task_id=req.task_id,
        task_name=(req.task_name or "").strip(),
        algorithm_id=algorithm_id,
        algorithm_name=algorithm_name,
        path="",
        description=(req.model_description or "").strip(),
        version=f"{saved_at.strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:8]}",
        time=saved_at,
    )
    db.add(db_model)
    db.flush()

    filename = _safe_model_filename(model_name)
    relative_path = Path("analysis_models") / req.instance_id / str(db_model.model_id) / filename
    physical_path = Path(ANALYSIS_MODELS_DIR).resolve() / req.instance_id / str(db_model.model_id) / filename
    physical_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = await _http_client.post(
            f"{ALGO_BASE}/{req.instance_id}/save",
            json={"path": str(physical_path)},
            timeout=_ALGO_TIMEOUT,
        )
        resp.raise_for_status()
        if not physical_path.is_file():
            raise RuntimeError(f"algorithm service returned success but {physical_path} is missing")
    except Exception as exc:
        db.rollback()
        physical_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"训练已完成，但模型保存失败: {exc}",
        ) from exc

    db_model.path = relative_path.as_posix()
    db_model.file_size = physical_path.stat().st_size
    try:
        db.commit()
        db.refresh(db_model)
    except Exception as exc:
        db.rollback()
        physical_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"模型文件已写入，但元数据登记失败: {exc}",
        ) from exc
    return db_model


async def _run_timeseries_job(
    req: TimeseriesJobRequest,
    mode: Literal["train", "infer"],
    db: Session,
) -> Any:
    """取数 → 组 CSV → 交给算法实例,两条链路只差 ``mode`` 与训练专属参数。"""
    if not req.sortieId.strip():
        raise HTTPException(
            status_code=400,
            detail="请提供 sortieId(架次标识,取自 /aircraft/sorties 的 sortieKey)",
        )
    if not req.airplaneType.strip():
        raise HTTPException(status_code=400, detail="请提供 airplaneType(机型)")
    if not req.instance_id.strip():
        raise HTTPException(status_code=400, detail="请选择承载作业的算法实例")

    csv_text, data_table_name = await _fetch_timeseries_csv(req)

    args: dict[str, Any] = {"batch_size": req.batch_size, "device": req.device}
    if mode == "train":
        args["epoch"] = req.epoch
        args["learning_rate"] = req.learning_rate

    payload = {
        "dataset": {
            "content_type": "text_csv",
            "content": csv_text,
            "data_cols": req.data_cols,
            "label_cols": req.label_cols or None,
        },
        "args": args,
        "detach": False if mode == "train" and req.model_name else req.detach,
    }

    try:
        resp = await _http_client.post(
            f"{ALGO_BASE}/{req.instance_id}/{mode}", json=payload, timeout=_ALGO_TIMEOUT
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="无法连接算法服务")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="算法服务响应超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"算法服务返回 {e.response.status_code}: {_upstream_detail(e.response)}",
        )

    result = resp.json()
    if mode == "train" and req.model_name:
        persisted = await _persist_trained_model(db, req, data_table_name)
        return {
            "result": result,
            "model": AnalysisModelResponse.model_validate(persisted).model_dump(mode="json"),
        }
    return result


@router.post("/tasks/train-timeseries")
async def train_with_timeseries(req: TimeseriesJobRequest, db: Session = Depends(get_db)):
    """以时序查询的结果为数据源训练,并把训练结果持久化为业务模型。"""
    if not (req.model_name or "").strip():
        raise HTTPException(
            status_code=400,
            detail="训练必须填写模型名称,训练完成后将自动保存并登记到模型管理",
        )
    return await _run_timeseries_job(req, "train", db)


@router.post("/tasks/infer-timeseries")
async def infer_with_timeseries(req: TimeseriesJobRequest, db: Session = Depends(get_db)):
    """以时序查询的结果为数据源,在算法实例上启动推理。"""
    return await _run_timeseries_job(req, "infer", db)
