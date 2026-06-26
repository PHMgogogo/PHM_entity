from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import AircraftTasksResponse, TaskCreate, TaskCreateResponse, TaskResponse, TaskUpdate
from fastapi import Query

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("/", response_model=TaskCreateResponse, status_code=201)
def create_task(task_in: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task. Returns the created task's task_id."""
    db_task = crud.create_task(db, task_in=task_in)
    return TaskCreateResponse(task_id=db_task.task_id)


@router.delete("/{task_id}", status_code=200)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task by its task_id."""
    success = crud.delete_task(db, task_id=task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    return {"detail": f"Task {task_id} deleted successfully"}


@router.get("/", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    """List all tasks with all attributes."""
    return crud.get_all_tasks(db)


@router.get("/search", response_model=list[TaskResponse])
def search_tasks(keyword: str = Query(..., min_length=1, description="Keyword to search in name and description"), db: Session = Depends(get_db)):
    """Filter tasks whose name or description contains the keyword."""
    return crud.search_tasks(db, keyword=keyword)


@router.get("/aircraft/{aircraft_id}", response_model=AircraftTasksResponse)
def get_tasks_by_aircraft(aircraft_id: str, db: Session = Depends(get_db)):
    """List tasks for the given aircraft_id unioned with all global tasks.

    The response includes ``initialization_required``, which is True when no task
    belongs to the requested aircraft_id (the returned tasks list may still be
    non-empty because global tasks are always included).
    """
    tasks, initialization_required = crud.get_tasks_by_aircraft(db, aircraft_id=aircraft_id)
    return AircraftTasksResponse(initialization_required=initialization_required, tasks=tasks)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get a single task by its task_id."""
    db_task = crud.get_task(db, task_id=task_id)
    if db_task is None:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    return db_task


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, task_in: TaskUpdate, db: Session = Depends(get_db)):
    """Update a task by its task_id. Only provided fields are updated."""
    db_task = crud.update_task(db, task_id=task_id, task_in=task_in)
    if db_task is None:
        raise HTTPException(status_code=404, detail=f"Task with id {task_id} not found")
    return db_task
