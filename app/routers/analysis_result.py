import csv as csv_module
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import ANALYSIS_RESULTS_DIR
from app.database import get_db
from app.models import AnalysisResult as AnalysisResultModel
from app.schemas import AnalysisResult, AnalysisResultRegister

router = APIRouter(prefix="/api/analysis/results", tags=["analysis_results"])


# ── 路径与文件辅助 ──────────────────────────────────────────────────

def _resolve_physical_path(db_path: str) -> Path:
    """把数据库中的逻辑 csv_path 解析为物理文件路径。

    数据库 csv_path 存逻辑路径(如 ``analysis_results/instance_id/<id>/<file>``,
    相对 data/ 目录),物理位置即 ``{ANALYSIS_RESULTS_DIR}/instance_id/...``。
    绝对路径原样使用。
    """
    p = Path(db_path)
    if p.is_absolute():
        return p
    return Path(ANALYSIS_RESULTS_DIR).parent / p


def _cleanup_empty_dirs(start: Path) -> None:
    """删除空的父目录,向上直到结果存储根目录(不含根目录本身)。"""
    root = Path(ANALYSIS_RESULTS_DIR).resolve()
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
        return "result.csv"
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if name in {".", ".."}:
        return "result.csv"
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "result.csv"


def _parse_csv(path: Path) -> tuple[int, int]:
    """读取 CSV 文件,返回 (n_col, n_row);解析失败时返回 (0, 0)。

    n_row 为总行数,n_col 为所有行中最大的列数。
    """
    n_row = 0
    n_col = 0
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            for row in csv_module.reader(f):
                n_row += 1
                n_col = max(n_col, len(row))
    except (UnicodeDecodeError, OSError, csv_module.Error):
        return 0, 0
    return n_col, n_row


async def _save_upload(upload: UploadFile, physical: Path) -> None:
    """把上传文件流式写入 physical 路径。"""
    physical.parent.mkdir(parents=True, exist_ok=True)
    try:
        with physical.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                out.write(chunk)
    except Exception:
        physical.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


# ── 上传(POST /upload, multipart/form-data)─────────────────────────

@router.post("/upload", response_model=AnalysisResult, status_code=201)
async def upload_result(
    instance_id: str = Form(..., pattern=r"^[A-Za-z0-9_-]+$"),
    csv_file: UploadFile = File(...),
    time: datetime = Form(default_factory=datetime.now),
    raw_data: str = Form(""),
    db: Session = Depends(get_db),
):
    """上传一个新的分析结果。

    CSV 保存到 ``{ANALYSIS_RESULTS_DIR}/instance_id/<result_id>/<filename>``,
    自动解析 n_col / n_row;返回 result_id、csv_path 等完整信息。
    """
    filename = _sanitize_filename(csv_file.filename)
    db_result = AnalysisResultModel(
        instance_id=instance_id,
        time=time,
        csv_path="",  # 占位,拿到自增 result_id 后再回填
        n_col=0,
        n_row=0,
        raw_data=raw_data,
    )
    db.add(db_result)
    db.flush()  # 触发自增,拿到 result_id

    rel_path = f"analysis_results/{instance_id}/{db_result.result_id}/{filename}"
    physical = _resolve_physical_path(rel_path)
    try:
        await _save_upload(csv_file, physical)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save csv file: {filename}")

    n_col, n_row = _parse_csv(physical)
    db_result.csv_path = rel_path
    db_result.n_col = n_col
    db_result.n_row = n_row
    db.commit()
    db.refresh(db_result)
    return db_result


# ── 注册(POST /register, JSON, 无文件)──────────────────────────────

@router.post("/register", response_model=AnalysisResult, status_code=201)
def register_result(payload: AnalysisResultRegister, db: Session = Depends(get_db)):
    """先注册一个分析结果的元信息(无文件),返回 result_id。

    csv_path 为空、n_col / n_row 为 0,文件后续通过 PUT 接口上传。
    """
    db_result = AnalysisResultModel(
        instance_id=payload.instance_id,
        time=payload.time,
        csv_path="",
        n_col=0,
        n_row=0,
        raw_data=payload.raw_data,
    )
    db.add(db_result)
    db.commit()
    db.refresh(db_result)
    return db_result


# ── 更新(PUT /{result_id}, multipart/form-data)─────────────────────

@router.put("/{result_id}", response_model=AnalysisResult)
async def update_result(
    result_id: int,
    csv_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """更新指定 result_id 的分析结果文件。

    新文件写入同目录并重新解析 n_col / n_row,time 刷新为当前时间;
    instance_id / raw_data 保持不变。若旧文件存在且文件名不同,一并删除。
    """
    db_result = (
        db.query(AnalysisResultModel)
        .filter(AnalysisResultModel.result_id == result_id)
        .first()
    )
    if db_result is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisResult with id {result_id} not found"
        )

    old_path = db_result.csv_path
    filename = _sanitize_filename(csv_file.filename)
    rel_path = f"analysis_results/{db_result.instance_id}/{db_result.result_id}/{filename}"
    physical = _resolve_physical_path(rel_path)
    try:
        await _save_upload(csv_file, physical)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save csv file: {filename}")

    if old_path and old_path != rel_path:
        old_physical = _resolve_physical_path(old_path)
        if old_physical.is_file():
            old_physical.unlink()

    n_col, n_row = _parse_csv(physical)
    db_result.csv_path = rel_path
    db_result.n_col = n_col
    db_result.n_row = n_row
    db_result.time = datetime.now()
    db.commit()
    db.refresh(db_result)
    return db_result


# ── 查询(GET)与删除(DELETE)─────────────────────────────────────────

@router.get("/", response_model=list[AnalysisResult])
def list_results(
    instance_id: str | None = Query(
        None, pattern=r"^[A-Za-z0-9_-]*$", description="Filter by instance_id"
    ),
    db: Session = Depends(get_db),
):
    """返回所有分析结果;指定 instance_id 时只返回该实例的结果。"""
    query = db.query(AnalysisResultModel)
    if instance_id:
        query = query.filter(AnalysisResultModel.instance_id == instance_id)
    return query.all()


@router.get("/{result_id}")
def get_result(result_id: int, db: Session = Depends(get_db)):
    """获取指定 result_id 的分析结果 CSV 文件,以附件形式返回。"""
    db_result = (
        db.query(AnalysisResultModel)
        .filter(AnalysisResultModel.result_id == result_id)
        .first()
    )
    if db_result is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisResult with id {result_id} not found"
        )
    if not db_result.csv_path:
        raise HTTPException(
            status_code=404,
            detail=f"AnalysisResult {result_id} has no csv file (registered without a file)",
        )

    physical = _resolve_physical_path(db_result.csv_path)
    if not physical.is_file():
        raise HTTPException(
            status_code=404, detail=f"Csv file not found on disk: {physical}"
        )
    return FileResponse(physical, filename=physical.name)


@router.delete("/{result_id}", status_code=200)
def delete_result(result_id: int, db: Session = Depends(get_db)):
    """删除分析结果:删除数据库条目;若 csv_path 指向的本地文件存在则一并删除。"""
    db_result = (
        db.query(AnalysisResultModel)
        .filter(AnalysisResultModel.result_id == result_id)
        .first()
    )
    if db_result is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisResult with id {result_id} not found"
        )

    if db_result.csv_path:
        physical = _resolve_physical_path(db_result.csv_path)
        if physical.is_file():
            physical.unlink()
        _cleanup_empty_dirs(physical.parent)

    db.delete(db_result)
    db.commit()
    return {"detail": f"AnalysisResult {result_id} deleted successfully"}
