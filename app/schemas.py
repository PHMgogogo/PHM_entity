from pydantic import BaseModel, Field
from datetime import datetime

# from pydantic import field_validator
# import re


class TaskCreate(BaseModel):
    """Request schema for creating a task."""

    name: str = Field(
        ..., min_length=1, max_length=255, description="Short text name of the task"
    )
    description: str = Field(
        default="", description="Long text description of the task"
    )
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
    default: bool = Field(
        default=False, description="Whether this is the default task for its aircraft"
    )
    algo_cols: list[str] = Field(
        default_factory=list,
        description="Names of each dimension of the instance algorithm's output",
    )

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
    algo_cols: list[str]

    model_config = {"from_attributes": True}


class TaskUpdate(BaseModel):
    """Request schema for updating a task — all fields are optional."""

    name: str | None = Field(
        None, min_length=1, max_length=255, description="Short text name of the task"
    )
    description: str | None = Field(
        None, description="Long text description of the task"
    )
    session_id: str | None = Field(
        None, min_length=1, max_length=255, description="Session identifier"
    )
    instance_id: str | None = Field(
        None, min_length=1, max_length=255, description="Instance identifier"
    )
    work_dir: str | None = Field(None, description="Cross-platform filesystem path")
    aircraft_id: str | None = Field(
        None, min_length=1, max_length=255, description="Aircraft identifier"
    )
    is_global: bool | None = Field(None, description="Whether this is a global task")
    default: bool | None = Field(
        None, description="Whether this is the default task for its aircraft"
    )
    algo_cols: list[str] | None = Field(
        None, description="Names of each dimension of the instance algorithm's output"
    )


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


class AnalysisModel(BaseModel):
    instance_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    path: str
    description: str = ""
    version: str = "1.0.0"
    time: datetime = Field(default_factory=datetime.now)


class AnalysisModelUpsert(BaseModel):
    """Request schema for registering/updating an analysis model without a file.

    ``(instance_id, version)`` acts as the unique key: if the pair already
    exists the record is updated, otherwise a new one is created.
    ``path`` is optional — when registering a model that lives outside the
    managed upload directory (e.g. an external filesystem location), it can be
    supplied explicitly.
    """

    instance_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    version: str = Field(min_length=1, max_length=50)
    description: str = ""
    path: str = ""


class AnalysisModelResponse(BaseModel):
    """Response schema for an analysis model."""

    model_id: int
    instance_id: str
    path: str
    description: str
    version: str
    time: datetime

    model_config = {"from_attributes": True}


class AnalysisResult(BaseModel):
    """Response schema for an analysis result."""

    result_id: int
    instance_id: str
    time: datetime
    csv_path: str
    n_col: int
    n_row: int
    raw_data: str

    model_config = {"from_attributes": True}


class AnalysisResultRegister(BaseModel):
    """Request schema for registering an analysis result without a file.

    仅记录元信息(instance_id / time / raw_data),csv_path 为空、
    n_col / n_row 为 0,文件后续通过 PUT 接口上传。
    """

    instance_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    time: datetime = Field(default_factory=datetime.now)
    raw_data: str = ""


class AnalysisAlarm(BaseModel):
    """Response schema for a single analysis alarm."""

    cols: list[str]
    instance_id: str
    range: tuple[int, int]
    message: str
    alarm_id: int
    raw_data: str
    time: datetime
    level: int


class AnalysisAlarmCreate(BaseModel):
    """Request schema for a single analysis alarm in a batch create
    (POST /api/analysis/alarms).

    alarm_id 由服务端自增分配。
    """

    instance_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    cols: list[str] = Field(default_factory=list)
    range: tuple[int, int]
    message: str = ""
    raw_data: str = ""
    time: datetime = Field(default_factory=datetime.now)
    level: int = Field(default=0, description="Alarm severity level")
    threshold: float = Field(default=0, description="Alarm threshold value")


class AnalysisAlarmDeleteRequest(BaseModel):
    """Request schema for deleting a batch of analysis alarms
    (DELETE /api/analysis/alarms)."""

    alarm_ids: list[int] = Field(min_length=1)


class AnalysisPipelineCreate(BaseModel):
    """Request schema for creating an analysis pipeline."""

    aircraft_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    pipeline_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class AnalysisPipelineUpdate(BaseModel):
    """Request schema for updating an analysis pipeline — all fields are optional."""

    aircraft_id: str | None = Field(None, pattern=r"^[A-Za-z0-9_-]+$")
    pipeline_id: str | None = Field(None, pattern=r"^[A-Za-z0-9_-]+$")


class AnalysisPipelineResponse(BaseModel):
    """Response schema for an analysis pipeline."""

    id: int
    aircraft_id: str
    pipeline_id: str

    model_config = {"from_attributes": True}
