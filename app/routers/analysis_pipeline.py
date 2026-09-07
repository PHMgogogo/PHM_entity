from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import (
    AnalysisPipelineCreate,
    AnalysisPipelineResponse,
    AnalysisPipelineUpdate,
)

router = APIRouter(prefix="/api/analysis/pipelines", tags=["analysis_pipelines"])


@router.post("/", response_model=AnalysisPipelineResponse, status_code=201)
def create_analysis_pipeline(
    payload: AnalysisPipelineCreate, db: Session = Depends(get_db)
):
    """Create a new analysis pipeline. (aircraft_id, pipeline_id) 联合唯一,重复返回 409。"""
    try:
        return crud.create_analysis_pipeline(db, pipeline_in=payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"AnalysisPipeline with aircraft_id={payload.aircraft_id!r} "
                f"and pipeline_id={payload.pipeline_id!r} already exists"
            ),
        )


@router.get("/", response_model=list[AnalysisPipelineResponse])
def list_analysis_pipelines(
    aircraft_id: str | None = Query(
        None, pattern=r"^[A-Za-z0-9_-]*$", description="Filter by aircraft_id"
    ),
    db: Session = Depends(get_db),
):
    """List all analysis pipelines; optionally filter by aircraft_id."""
    if aircraft_id:
        return crud.get_analysis_pipelines_by_aircraft(db, aircraft_id=aircraft_id)
    return crud.get_all_analysis_pipelines(db)


@router.get("/{pipeline_id}", response_model=AnalysisPipelineResponse)
def get_analysis_pipeline(pipeline_id: int, db: Session = Depends(get_db)):
    """Get a single analysis pipeline by its id."""
    db_pipeline = crud.get_analysis_pipeline(db, pipeline_id=pipeline_id)
    if db_pipeline is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisPipeline with id {pipeline_id} not found"
        )
    return db_pipeline


@router.put("/{pipeline_id}", response_model=AnalysisPipelineResponse)
def update_analysis_pipeline(
    pipeline_id: int, payload: AnalysisPipelineUpdate, db: Session = Depends(get_db)
):
    """Update an analysis pipeline by its id. Only provided fields are updated."""
    try:
        db_pipeline = crud.update_analysis_pipeline(
            db, pipeline_id=pipeline_id, pipeline_in=payload
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="AnalysisPipeline with the same (aircraft_id, pipeline_id) already exists",
        )
    if db_pipeline is None:
        raise HTTPException(
            status_code=404, detail=f"AnalysisPipeline with id {pipeline_id} not found"
        )
    return db_pipeline


@router.delete("/{pipeline_id}", status_code=200)
def delete_analysis_pipeline(pipeline_id: int, db: Session = Depends(get_db)):
    """Delete an analysis pipeline by its id."""
    success = crud.delete_analysis_pipeline(db, pipeline_id=pipeline_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"AnalysisPipeline with id {pipeline_id} not found"
        )
    return {"detail": f"AnalysisPipeline {pipeline_id} deleted successfully"}
