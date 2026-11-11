# import re
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    Float,
    JSON,
    UniqueConstraint,
)

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False, default="")
    session_id = Column(
        String(255),
        nullable=False,
        default="",
    )
    aircraft_id = Column(
        String(255),
        nullable=False,
        default="",
    )
    instance_id = Column(
        String(255),
        nullable=False,
        default="",
    )
    model_code = Column(
        String(255),
        nullable=False,
        default="",
        comment="Aircraft model code (机型)",
    )
    work_dir = Column(
        Text,
        nullable=False,
        default="",
        comment="Cross-platform filesystem path",
    )
    is_global = Column(
        "global",
        Boolean,
        nullable=False,
        default=False,
    )
    algo_cols = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Names of each dimension of the instance algorithm's output (JSON array of strings)",
    )

    # @staticmethod
    # def validate_session_id(session_id: str) -> bool:
    #     """Session_id must be composed of alphanumeric characters, hyphens, and underscores."""
    #     return bool(re.fullmatch(r"[A-Za-z0-9\-_]+", session_id))


class AnalysisModel(Base):
    """Database entity corresponding to the ``AnalysisModel`` schema (a machine-learning model)."""

    __tablename__ = "analysis_models"
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "version", name="uq_analysis_model_instance_version"
        ),
    )

    model_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    name = Column(String(255), nullable=False, default="")
    aircraft_number = Column(String(255), nullable=False, default="", index=True)
    model_code = Column(String(255), nullable=False, default="")
    sortie_key = Column(String(255), nullable=False, default="", index=True)
    sortie_number = Column(String(255), nullable=False, default="")
    flight_date = Column(String(50), nullable=False, default="")
    source_type = Column(String(50), nullable=False, default="")
    data_table_name = Column(String(255), nullable=False, default="")
    data_range_start = Column(String(50), nullable=False, default="")
    data_range_end = Column(String(50), nullable=False, default="")
    data_columns = Column(JSON, nullable=False, default=list)
    label_columns = Column(JSON, nullable=False, default=list)
    instance_id = Column(String(255), nullable=False, index=True)
    task_id = Column(Integer, nullable=True)
    task_name = Column(String(255), nullable=False, default="")
    algorithm_id = Column(String(255), nullable=False, default="")
    algorithm_name = Column(String(255), nullable=False, default="")
    path = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    version = Column(String(50), nullable=False, default="1.0.0")
    file_size = Column(Integer, nullable=False, default=0)
    time = Column(DateTime, nullable=False, default=datetime.now)


class AnalysisResult(Base):
    """Database entity corresponding to the ``AnalysisResult`` schema.

    ``n_col`` / ``n_row`` 由上传的 CSV 文件解析得到;未上传文件(仅注册)时
    ``csv_path`` 为空、``n_col`` / ``n_row`` 为 0。
    """

    __tablename__ = "analysis_results"

    result_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    instance_id = Column(String(255), nullable=False, index=True)
    time = Column(DateTime, nullable=False, default=datetime.now)
    csv_path = Column(Text, nullable=False, default="")
    n_col = Column(Integer, nullable=False, default=0)
    n_row = Column(Integer, nullable=False, default=0)
    raw_data = Column(Text, nullable=False, default="")


class AnalysisAlarm(Base):
    """Database entity corresponding to the ``AnalysisAlarm`` schema.

    ``cols`` 以逗号分隔字符串存单个字段(约定列名不含逗号);
    ``range`` 用 ``range_start`` / ``range_end`` 两个字段存储;
    ``level`` 表示告警等级。
    """

    __tablename__ = "analysis_alarms"

    alarm_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    instance_id = Column(String(255), nullable=False, index=True)
    cols = Column(Text, nullable=False, default="")
    range_start = Column(Integer, nullable=False, default=0)
    range_end = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=False, default="")
    raw_data = Column(Text, nullable=False, default="")
    time = Column(DateTime, nullable=False, default=datetime.now)
    level = Column(Integer, nullable=False, default=0)
    threshold = Column(Float, nullable=False, default=0)


class AnalysisPipeline(Base):
    """Database entity for an analysis pipeline.

    ``(aircraft_id, pipeline_id)`` 联合唯一,表示某架飞机关联的某条分析流水线。
    """

    __tablename__ = "analysis_pipelines"
    __table_args__ = (
        UniqueConstraint(
            "aircraft_id", "pipeline_id", name="uq_analysis_pipeline_aircraft_pipeline"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    aircraft_id = Column(String(255), nullable=False, index=True)
    pipeline_id = Column(String(255), nullable=False, index=True)
