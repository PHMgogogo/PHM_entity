import csv
import io
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from app.config import ALGO_BASE, CSV_TIMESERIES_ENDPOINT, CSV_UPSTREAM

router = APIRouter(prefix="/api", tags=["csv"])

# CSV 服务节点与算法服务节点不同(主机:端口 / 路由路径见 app.config)。

# 进程级共享 HTTP 客户端:CSV 服务与算法服务分属不同节点,但 httpx 客户端
# 可同时访问多个主机(连接池与 keep-alive 均按主机隔离),仍共用同一客户端。
# 此前每个请求都 `async with AsyncClient(...)` 两次(CSV 取数 + 算法调用),
# 仅客户端构造每次就耗 ~2s(默认建 SSL 上下文加载证书库 + trust_env 读代理,
# 而目标是 http LAN 地址,均用不上)。改为启动期构造一次,从热路径移除。
# trust_env=False:只访问 LAN http 主机,无需代理 / .netrc 查找。
# 默认超时 30s(CSV 取数用);算法训练 / 推理较慢,在请求级用 timeout= 覆盖为 120s。
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0),
    trust_env=False,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)
# 算法训练 / 推理请求级超时:训练可能较久,放宽到 120s
_ALGO_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# ── Pydantic schemas ────────────────────────────────────────────────

class TrainRequest(BaseModel):
    """Request body for POST /api/tasks/train."""
    table_name: str = Field(..., description="Table name to export CSV data from")
    data_cols: list[str] = Field(..., description="Column names used as model inputs")
    label_cols: list[str] = Field(default_factory=list, description="Column names used as labels")
    instance_id: str = Field(..., description="Algorithm instance identifier")
    batch_size: int = Field(1, ge=1, description="Batch size for training")
    epoch: int = Field(1, ge=1, description="Number of training epochs")
    learning_rate: float = Field(1e-3, gt=0, description="Learning rate")
    detach: bool = Field(False, description="Run training asynchronously when True")
    device: Literal["cpu", "cuda"] = Field("cpu", description="Compute device")


# ── Training trigger endpoint ───────────────────────────────────────

@router.post("/tasks/train")
async def train_model(req: TrainRequest):
    """Trigger a model training task on the algorithm service.

    Flow:
    1. Fetches CSV data from the upstream CSV service (see ``CSV_UPSTREAM`` in app.config).
    2. POSTs the CSV text to ``{instance_id}/train`` on the algorithm service.
    3. Returns the training result (or ``[]`` when ``detach=True``).
    """
    # ── 1.  Fetch CSV text from upstream CSV service ────────────────
    columns_str = ",".join(req.data_cols + req.label_cols)
    csv_url = CSV_UPSTREAM
    csv_params = {"tableName": req.table_name, "columns": columns_str}

    try:
        csv_resp = await _http_client.get(csv_url, params=csv_params)
        csv_resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to CSV service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CSV service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"CSV service returned {e.response.status_code}: {e.response.text[:500]}",
        )
    csv_text = csv_resp.text

    # ── 2.  POST to algorithm /train ───────────────────────────────
    train_url = f"{ALGO_BASE}/{req.instance_id}/train"
    train_payload = {
        "dataset": {
            "content_type": "text_csv",
            "content": csv_text,
            "data_cols": req.data_cols,
            "label_cols": req.label_cols if req.label_cols else None,
        },
        "args": {
            "epoch": req.epoch,
            "batch_size": req.batch_size,
            "learning_rate": req.learning_rate,
            "device": req.device,
        },
        "detach": req.detach,
    }

    try:
        train_resp = await _http_client.post(train_url, json=train_payload, timeout=_ALGO_TIMEOUT)
        train_resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to algorithm service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Algorithm service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Algorithm service returned {e.response.status_code}: {e.response.text[:500]}",
        )

    return train_resp.json()


# ── Inference trigger endpoint ──────────────────────────────────────

class InferRequest(BaseModel):
    """Request body for POST /api/tasks/infer."""
    table_name: str = Field(..., description="Table name to export CSV data from")
    data_cols: list[str] = Field(..., description="Column names used as model inputs")
    label_cols: list[str] = Field(default_factory=list, description="Column names used as labels")
    instance_id: str = Field(..., description="Algorithm instance identifier")
    batch_size: int = Field(1, ge=1, description="Batch size for inference")
    detach: bool = Field(False, description="Run inference asynchronously when True")
    device: Literal["cpu", "cuda"] = Field("cpu", description="Compute device")


class TimeseriesJobBase(BaseModel):
    """Common request fields for time-series backed training and inference."""

    airplaneType: str = Field(..., min_length=1, description="Aircraft model code")
    sortieId: str = Field(..., min_length=1, description="Sortie key")
    aircraftNumber: str | None = Field(None, description="Aircraft number")
    startTime: str | None = Field(None, description="Inclusive start time")
    endTime: str | None = Field(None, description="Inclusive end time")
    data_cols: list[str] = Field(..., min_length=1, description="Input columns")
    label_cols: list[str] = Field(default_factory=list, description="Label columns")
    instance_id: str = Field(..., min_length=1, description="Algorithm instance identifier")
    batch_size: int = Field(1, ge=1, description="Batch size")
    detach: bool = Field(False, description="Run asynchronously when True")
    device: Literal["cpu", "cuda"] = Field("cpu", description="Compute device")


class TimeseriesTrainRequest(TimeseriesJobBase):
    """Request body for POST /api/tasks/train-timeseries."""

    epoch: int = Field(1, ge=1, description="Number of training epochs")
    learning_rate: float = Field(1e-3, gt=0, description="Learning rate")


class TimeseriesInferRequest(TimeseriesJobBase):
    """Request body for POST /api/tasks/infer-timeseries."""


@router.post("/tasks/infer")
async def infer_model(req: InferRequest):
    """Trigger a model inference task on the algorithm service.

    Flow:
    1. Fetches CSV data from the upstream CSV service (see ``CSV_UPSTREAM`` in app.config).
    2. POSTs the CSV text to ``{instance_id}/infer`` on the algorithm service.
    3. Returns the inference result (or ``[]`` when ``detach=True``).
    """
    # ── 1.  Fetch CSV text from upstream CSV service ────────────────
    columns_str = ",".join(req.data_cols + req.label_cols)
    csv_url = CSV_UPSTREAM
    csv_params = {"tableName": req.table_name, "columns": columns_str}

    try:
        csv_resp = await _http_client.get(csv_url, params=csv_params)
        csv_resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to CSV service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CSV service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"CSV service returned {e.response.status_code}: {e.response.text[:500]}",
        )
    csv_text = csv_resp.text

    # ── 2.  POST to algorithm /infer ───────────────────────────────
    infer_url = f"{ALGO_BASE}/{req.instance_id}/infer"
    infer_payload = {
        "dataset": {
            "content_type": "text_csv",
            "content": csv_text,
            "data_cols": req.data_cols,
            "label_cols": req.label_cols if req.label_cols else None,
        },
        "args": {
            "batch_size": req.batch_size,
            "device": req.device,
        },
        "detach": req.detach,
    }

    try:
        infer_resp = await _http_client.post(infer_url, json=infer_payload, timeout=_ALGO_TIMEOUT)
        infer_resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to algorithm service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Algorithm service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Algorithm service returned {e.response.status_code}: {e.response.text[:500]}",
        )

    return infer_resp.json()


# ── Time-series backed training / inference ─────────────────────────

def _requested_timeseries_columns(req: TimeseriesJobBase) -> list[str]:
    """Return data and label columns in request order, without duplicates."""
    columns: list[str] = []
    seen: set[str] = set()
    for raw in req.data_cols + req.label_cols:
        name = raw.strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        columns.append(name)
    return columns


def _timeseries_response_to_csv(payload: dict[str, Any], columns: list[str]) -> str:
    """Convert the unified time-series response into the CSV expected by algorithms."""
    if payload.get("code") != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Time-series service returned: {payload.get('message') or payload.get('error') or 'unknown error'}",
        )

    data = payload.get("data") or {}
    values_by_name: dict[str, list[Any]] = {}
    for parameter in data.get("parameters") or []:
        name = str(parameter.get("name") or "").strip()
        if name:
            values_by_name[name.casefold()] = list(parameter.get("values") or [])

    missing = [column for column in columns if column.casefold() not in values_by_name]
    if missing:
        raise HTTPException(
            status_code=502,
            detail=f"Time-series response is missing requested columns: {', '.join(missing)}",
        )

    selected_values = [values_by_name[column.casefold()] for column in columns]
    row_count = max((len(values) for values in selected_values), default=0)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for row_index in range(row_count):
        writer.writerow(
            [
                values[row_index] if row_index < len(values) else ""
                for values in selected_values
            ]
        )
    return output.getvalue()


async def _fetch_timeseries_job_csv(req: TimeseriesJobBase) -> str:
    columns = _requested_timeseries_columns(req)
    if not columns:
        raise HTTPException(status_code=422, detail="At least one data or label column is required")

    query: dict[str, Any] = {
        "airplaneType": req.airplaneType,
        "sortieId": req.sortieId,
        "paralist": columns,
    }
    if req.aircraftNumber:
        query["aircraftNumber"] = req.aircraftNumber
    if req.startTime:
        query["startTime"] = req.startTime
    if req.endTime:
        query["endTime"] = req.endTime

    try:
        response = await _http_client.post(CSV_TIMESERIES_ENDPOINT, json=query)
        response.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to time-series service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Time-series service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Time-series service returned {e.response.status_code}: {e.response.text[:500]}",
        )

    try:
        payload = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Time-series service returned invalid JSON")

    return _timeseries_response_to_csv(payload, columns)


async def _run_timeseries_job(req: TimeseriesJobBase, mode: Literal["train", "infer"]):
    csv_text = await _fetch_timeseries_job_csv(req)
    payload = {
        "dataset": {
            "content_type": "text_csv",
            "content": csv_text,
            "data_cols": req.data_cols,
            "label_cols": req.label_cols if req.label_cols else None,
        },
        "args": {
            "batch_size": req.batch_size,
            "device": req.device,
        },
        "detach": req.detach,
    }
    if isinstance(req, TimeseriesTrainRequest):
        payload["args"].update(
            {
                "epoch": req.epoch,
                "learning_rate": req.learning_rate,
            }
        )

    algorithm_url = f"{ALGO_BASE}/{req.instance_id}/{mode}"
    try:
        response = await _http_client.post(
            algorithm_url,
            json=payload,
            timeout=_ALGO_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to algorithm service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Algorithm service timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Algorithm service returned {e.response.status_code}: {e.response.text[:500]}",
        )

    return response.json()


@router.post("/tasks/train-timeseries")
async def train_timeseries_model(req: TimeseriesTrainRequest):
    """Train an algorithm instance using data from the unified time-series API."""
    return await _run_timeseries_job(req, "train")


@router.post("/tasks/infer-timeseries")
async def infer_timeseries_model(req: TimeseriesInferRequest):
    """Run inference using data from the unified time-series API."""
    return await _run_timeseries_job(req, "infer")
