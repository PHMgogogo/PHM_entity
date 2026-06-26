from pydantic import BaseModel, Field
# from pydantic import field_validator
# import re


class TaskCreate(BaseModel):
    """Request schema for creating a task."""
    name: str = Field(..., min_length=1, max_length=255, description="Short text name of the task")
    description: str = Field(default="", description="Long text description of the task")
    session_id: str = Field(
        default="",
        min_length=1,
        max_length=255,
        description="Session identifier composed of letters, digits, hyphens, and underscores",
    )
    aircraft_id: str = Field(
        default="",
        min_length=1,
        max_length=255,
        description="Aircraft identifier composed of letters, digits, hyphens, and underscores",
    )
    instance_id: str = Field(
        default="",
        min_length=1,
        max_length=255,
        description="Instance identifier composed of letters, digits, hyphens, and underscores",
    )
    work_dir: str = Field(
        default="",
        description="Cross-platform filesystem path",
    )
    is_global: bool = Field(default=False, description="Whether this is a global task")
    default: bool = Field(default=False, description="Whether this is the default task for its aircraft")

    # @field_validator("session_id")
    # @classmethod
    # def validate_session_id(cls, v: str) -> str:
    #     if not re.fullmatch(r"[A-Za-z0-9\-_]+", v):
    #         raise ValueError("session_id must contain only letters, digits, hyphens, and underscores")
    #     return v

    # @field_validator("instance_id")
    # @classmethod
    # def validate_instance_id(cls, v: str) -> str:
    #     if not re.fullmatch(r"[A-Za-z0-9\-_]+", v):
    #         raise ValueError("instance_id must contain only letters, digits, hyphens, and underscores")
    #     return v


class TaskResponse(BaseModel):
    """Response schema for a single task."""
    task_id: int
    name: str
    description: str
    session_id: str
    aircraft_id: str
    instance_id: str
    work_dir: str
    is_global: bool
    default: bool

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    """Request schema for updating a task — all fields are optional."""
    name: str | None = Field(None, min_length=1, max_length=255, description="Short text name of the task")
    description: str | None = Field(None, description="Long text description of the task")
    session_id: str | None = Field(None, min_length=1, max_length=255, description="Session identifier")
    instance_id: str | None = Field(None, min_length=1, max_length=255, description="Instance identifier")
    work_dir: str | None = Field(None, description="Cross-platform filesystem path")
    aircraft_id: str | None = Field(None, min_length=1, max_length=255, description="Aircraft identifier")
    is_global: bool | None = Field(None, description="Whether this is a global task")
    default: bool | None = Field(None, description="Whether this is the default task for its aircraft")


class TaskCreateResponse(BaseModel):
    """Response schema after creating a task — returns only the task_id."""
    task_id: int


class AircraftTasksResponse(BaseModel):
    """Response schema for querying tasks by aircraft — the union of the
    aircraft's own tasks and all global tasks, plus an initialization flag."""
    initialization_required: bool = Field(
        ...,
        description=(
            "True when no task belongs to the requested aircraft_id; the tasks "
            "list may still be non-empty because global tasks are always included"
        ),
    )
    tasks: list[TaskResponse] = Field(
        default_factory=list,
        description="Tasks for the aircraft unioned with all global tasks (deduplicated by task_id)",
    )
