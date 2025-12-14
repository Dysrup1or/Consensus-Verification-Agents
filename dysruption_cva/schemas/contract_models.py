from __future__ import annotations

from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class Initiator(BaseModel):
    callback_url: str = Field(..., min_length=8)
    callback_bearer_token: Optional[str] = None


class SuccessSpec(BaseModel):
    # Catalyze (Promptly) fields
    intent_summary: Optional[str] = Field(default=None, max_length=2000)
    key_constraints: List[str] = Field(default_factory=list)
    expected_behavior: Optional[str] = Field(default=None, max_length=2000)

    # Legacy/minimal contract fields
    acceptance_criteria: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("key_constraints", "acceptance_criteria")
    @classmethod
    def _limit_list_sizes(cls, v: List[str]) -> List[str]:
        if not v:
            return []
        return [str(x)[:500] for x in v[:50]]


class IntentEnvelope(BaseModel):
    run_id: UUID
    project_id: str = Field(..., min_length=1, max_length=128)
    initiator: Optional[Initiator] = None
    commit_hash: Optional[str] = Field(default=None, max_length=64)
    success_spec: SuccessSpec


class TriggerScanMode(str, Enum):
    DIFF = "diff"
    FULL = "full"


class TriggerScanRequest(BaseModel):
    run_id: UUID
    mode: TriggerScanMode = TriggerScanMode.DIFF


class TriggerScanResponse(BaseModel):
    run_id: UUID
    status: str
    verdicts_url: Optional[str] = None


class TribunalVerdictType(str, Enum):
    SECURITY = "security"
    STABILITY = "stability"
    PERFORMANCE = "performance"
    COMPLIANCE = "compliance"
    QUALITY = "quality"


class TribunalSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TribunalVerdictItem(BaseModel):
    id: str
    type: TribunalVerdictType
    rule_id: str
    severity: TribunalSeverity
    file: Optional[str] = None
    line_start: int = Field(..., ge=1)
    line_end: int = Field(..., ge=1)
    message: str
    suggested_fix: Optional[str] = None
    auto_fixable: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)


class VerdictStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class VerdictResponse(BaseModel):
    run_id: UUID
    status: VerdictStatus
    verdicts: List[TribunalVerdictItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
