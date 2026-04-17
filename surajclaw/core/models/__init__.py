"""Core models.

Models are split per-file for readability. Django introspects this module
to discover core app models, so every model must be re-exported here.

Models are added in phase order (see the architecture plan). Phase 1 ships
foundation tables: Session, Message, SystemState.
"""
from core.models.audit_log import AuditLog
from core.models.dream_log import DreamLog
from core.models.future_queue import FutureQueue
from core.models.message import Message
from core.models.session import Session
from core.models.system_state import SystemState
from core.models.task import Task

__all__ = [
    "AuditLog",
    "DreamLog",
    "FutureQueue",
    "Message",
    "Session",
    "SystemState",
    "Task",
]
