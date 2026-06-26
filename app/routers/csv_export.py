from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

router = APIRouter(prefix="/api", tags=["csv"])

# ── upstream addresses ──────────────────────────────────────────────
CSV_UPSTREAM = "http://192.168.31.13:8001"
ALGO_BASE = "http://192.168.31.13:8001"

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
    1. Fetches CSV data from the upstream CSV service at ``192.168.31.13:8001``.
    2. POSTs the CSV text to ``{instance_id}/train`` on the algorithm service.
    3. Returns the training result (or ``[]`` when ``detach=True``).
    """
    # ── 1.  Fetch CSV text from upstream CSV service ────────────────
    columns_str = ",".join(req.data_cols + req.label_cols)
    csv_url = f"{CSV_UPSTREAM}/api/csv/export-columns"
    csv_params = {"tableName": req.table_name, "columns": columns_str}
    # print(f"Fetching CSV from {csv_url} with params {csv_params}...")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            csv_resp = await client.get(csv_url, params=csv_params)
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
    # print(f"Sending training request to {train_url} with payload: {train_payload}")
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        try:
            train_resp = await client.post(train_url, json=train_payload)
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


@router.post("/tasks/infer")
async def infer_model(req: InferRequest):
    """Trigger a model inference task on the algorithm service.

    Flow:
    1. Fetches CSV data from the upstream CSV service at ``192.168.31.13:8001``.
    2. POSTs the CSV text to ``{instance_id}/infer`` on the algorithm service.
    3. Returns the inference result (or ``[]`` when ``detach=True``).
    """
    # ── 1.  Fetch CSV text from upstream CSV service ────────────────
    columns_str = ",".join(req.data_cols + req.label_cols)
    csv_url = f"{CSV_UPSTREAM}/api/csv/export-columns"
    csv_params = {"tableName": req.table_name, "columns": columns_str}

    # print(f"Fetching CSV from {csv_url} with params {csv_params}...")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            csv_resp = await client.get(csv_url, params=csv_params)
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

    # print(f"Sending inference request to {infer_url} with payload: {infer_payload}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
        try:
            infer_resp = await client.post(infer_url, json=infer_payload)
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
