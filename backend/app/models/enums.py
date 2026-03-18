from __future__ import annotations

from enum import Enum


class UserStatus(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"


class AccessStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"
    DELETED = "deleted"


class AccessType(str, Enum):
    TEST = "test"
    PAID = "paid"


class HealthStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNREACHABLE = "unreachable"
    ERROR = "error"


class AuditActorType(str, Enum):
    ADMIN = "admin"
    SYSTEM = "system"
    BOT = "bot"

