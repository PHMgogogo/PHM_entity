import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ANALYSIS_MODELS_DIR
from app.database import get_db
from app.models import AnalysisModel
from app.schemas import AnalysisModelResponse, AnalysisModelUpsert

router = APIRouter(prefix="/api/analysis/models", tags=["analysis_models"])


# ── 路径与文件名辅助 ────────────────────────────────────────────────

def _resolve_physical_path(db_path: str) -> Path:
    """把数据库中的逻辑 path 解析为物理文件路径。

    数据库 path 存逻辑路径(如 ``analysis_models/instance_id/<id>/<file>``,
    相对 data/ 目录),物理位置即 ``{ANALYSIS_MODELS_DIR}/instance_id/...``。
    绝对路径原样使用。
    """
    p = Path(db_path)
    if p.is_absolute():
        return p
    return Path(ANALYSIS_MODELS_DIR).parent / p


def _cleanup_empty_dirs(start: Path) -> None:
    """删除空的父目录,向上直到模型存储根目录(不含根目录本身)。"""
    root = Path(ANALYSIS_MODELS_DIR).resolve()
    cur = start.resolve()
    if not cur.is_relative_to(root):
        return
    while cur != root:
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def _sanitize_filename(filename: str | None) -> str:
    """只保留文件基名并过滤不安全字符,防路径穿越。"""
    if not filename:
        return "model.pth"
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if name in {".", ".."}:
        return "model.pth"
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "model.pth"


# ── 上传模型(POST, multipart/form-data)─────────────────────────────

@router.post("/", response_model=AnalysisModelResponse, status_code=201)
async def upload_model(
    instance_id: str = Form(..., pattern=r"^[A-Za-z0-9_-]+$"),
    version: str = Form(..., min_length=1, max_length=50),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传一个新的分析模型。

    - 信息保存到数据库;(instance_id, version) 联合唯一,重复返回 409。
    - 模型文件保存到 ``{ANALYSIS_MODELS_DIR}/instance_id/<model_id>/<filename>``,
      path 不允许由客户端传入,固定为 ``analysis_models/instance_id/<model_id>/<filename>``。
    """
    filename = _sanitize_filename(file.filename)
    db_model = AnalysisModel(
        instance_id=instance_id,
        version=version,
        description=description,
        path="",  # 占位,拿到自增 model_id 后再回填
    )
    db.add(db_model)
    try:
        db.flush()  # 触发自增,拿到 model_id
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Model with instance_id={instance_id!r} and version={version!r} already exists",
        )

    rel_path = f"analysis_models/{instance_id}/{db_model.model_id}/{filename}"
    physical_path = _resolve_physical_path(rel_path)
    physical_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with physical_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
    except Exception:
        db.rollback()
        physical_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to save model file: {filename}")
    finally:
        await file.close()

    db_model.path = rel_path
    db.commit()
    db.refresh(db_model)
    return db_model


# ── 注册 / 更新(PUT, JSON, 无文件)──────────────────────────────────

@router.put("/", response_model=AnalysisModelResponse)
def upsert_model(payload: AnalysisModelUpsert, db: Session = Depends(get_db)):
    """注册一个无文件的分析模型,或更新已有记录。

    (instance_id, version) 作为唯一键:已存在则更新 description / path,否则新建。
    path 允许显式传入外部路径(如模型文件不在本地上传目录内);不传则为空。
    """
    db_model = (
        db.query(AnalysisModel)
        .filter(
            AnalysisModel.instance_id == payload.instance_id,
            AnalysisModel.version == payload.version,
        )
        .first()
    )
    if db_model is None:
        db_model = AnalysisModel(
            instance_id=payload.instance_id,
            version=payload.version,
            description=payload.description,
            path=payload.path,
        )
        db.add(db_model)
    else:
        db_model.description = payload.description
        db_model.path = payload.path
    db.commit()
    db.refresh(db_model)
    return db_model


# ── 查询(GET)与删除(DELETE)─────────────────────────────────────────

@router.get("/", response_model=list[AnalysisModelResponse])
def list_models(db: Session = Depends(get_db)):
    """返回所有分析模型。"""
    return db.query(AnalysisModel).all()


@router.get("/{model_id}")
def get_model(
    model_id: int,
    mode: Literal["abs_path", "file"] = Query(
        "abs_path",
        description="abs_path: 返回模型文件的绝对路径;file: 直接返回模型文件",
    ),
    db: Session = Depends(get_db),
):
    """获取指定 model_id 的分析模型。

    mode 为 ``abs_path`` 时返回模型文件的绝对路径;为 ``file`` 时以附件形式返回模型文件。
    """
    db_model = (
        db.query(AnalysisModel).filter(AnalysisModel.model_id == model_id).first()
    )
    if db_model is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisModel with id {model_id} not found"
        )
    if not db_model.path:
        raise HTTPException(
            status_code=404,
            detail=f"AnalysisModel {model_id} has no file (registered without a file)",
        )

    physical = _resolve_physical_path(db_model.path)
    if not physical.is_file():
        raise HTTPException(
            status_code=404, detail=f"Model file not found on disk: {physical}"
        )

    if mode == "abs_path":
        return {"model_id": db_model.model_id, "path": str(physical)}
    return FileResponse(physical, filename=physical.name)


@router.delete("/{model_id}", status_code=200)
def delete_model(model_id: int, db: Session = Depends(get_db)):
    """删除分析模型:删除数据库条目;若 path 指向的本地文件存在则一并删除。"""
    db_model = (
        db.query(AnalysisModel).filter(AnalysisModel.model_id == model_id).first()
    )
    if db_model is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisModel with id {model_id} not found"
        )

    stored_path = db_model.path
    if stored_path:
        physical = _resolve_physical_path(stored_path)
        if physical.is_file():
            physical.unlink()
        _cleanup_empty_dirs(physical.parent)

    db.delete(db_model)
    db.commit()
    return {"detail": f"AnalysisModel {model_id} deleted successfully"}
