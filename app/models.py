# import re

from sqlalchemy import Boolean, Column, Integer, String, Text

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
    default = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    # @staticmethod
    # def validate_session_id(session_id: str) -> bool:
    #     """Session_id must be composed of alphanumeric characters, hyphens, and underscores."""
    #     return bool(re.fullmatch(r"[A-Za-z0-9\-_]+", session_id))
