"""
API Endpoints for Autonomous Remediation Agent

Provides REST and WebSocket endpoints for:
- Triggering remediation runs
- Monitoring progress
- Viewing history
- Managing kill switch
- Configuration
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from pydantic import BaseModel, Field

from .engine import RemediationEngine, RemediationConfig, create_engine
from .models import (
    ApprovalLevel,
    RemediationEvent,
    RemediationEventType,
    RemediationRun,
    RemediationStatus,
)
from .safety import (
    is_kill_switch_active,
    activate_kill_switch,
    deactivate_kill_switch,
    SafetyConfig,
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class TriggerRemediationRequest(BaseModel):
    """Request to trigger remediation."""
    verdict: Dict[str, Any] = Field(..., description="Tribunal verdict to remediate")
    config: Optional[Dict[str, Any]] = Field(None, description="Optional config override")
    auto_apply: bool = Field(True, description="Auto-apply fixes if approved")


class TriggerRemediationResponse(BaseModel):
    """Response from triggering remediation."""
    run_id: str
    status: str
    message: str


class RemediationRunResponse(BaseModel):
    """Response containing run details."""
    id: str
    verdict_id: Optional[str]
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    iterations: int
    issues_count: int
    fixes_applied: int
    fixes_reverted: int
    health_state: Optional[str]
    error: Optional[str]


class KillSwitchRequest(BaseModel):
    """Request to toggle kill switch."""
    active: bool
    reason: Optional[str] = None
    actor: str = "api"


class KillSwitchResponse(BaseModel):
    """Response for kill switch status."""
    active: bool
    reason: Optional[str]
    activated_at: Optional[str]
    activated_by: Optional[str]


class ApproveFixRequest(BaseModel):
    """Request to approve a fix."""
    fix_id: str
    run_id: str
    approved: bool
    reviewer: str = "user"
    comment: Optional[str] = None


class ConfigResponse(BaseModel):
    """Current configuration."""
    enabled: bool
    auto_apply: bool
    max_iterations: int
    safety: Dict[str, Any]


# =============================================================================
# ROUTER SETUP
# =============================================================================


router = APIRouter(prefix="/api/remediation", tags=["remediation"])

# Global state (would be dependency-injected in production)
_engine: Optional[RemediationEngine] = None
_active_runs: Dict[str, RemediationRun] = {}
_ws_connections: Set[WebSocket] = set()


def get_engine() -> RemediationEngine:
    """Get or create the remediation engine."""
    global _engine
    if _engine is None:
        # Would be configured via dependency injection in production
        from ..api import get_config, get_db_path  # type: ignore
        
        config_data = get_config().get("remediation", {})
        config = RemediationConfig.from_dict(config_data)
        
        _engine = RemediationEngine(
            project_root=Path.cwd(),
            config=config,
            db_path=get_db_path(),
        )
        
        # Register WebSocket event listener
        _engine.events.add_async_listener(_broadcast_event)
    
    return _engine


async def _broadcast_event(event: RemediationEvent):
    """Broadcast event to all WebSocket connections."""
    if not _ws_connections:
        return
    
    message = json.dumps({
        "type": event.type.value,
        "run_id": event.run_id,
        "timestamp": event.timestamp.isoformat(),
        "data": event.data,
    })
    
    dead_connections = set()
    for ws in _ws_connections:
        try:
            await ws.send_text(message)
        except Exception:
            dead_connections.add(ws)
    
    _ws_connections.difference_update(dead_connections)


# =============================================================================
# REST ENDPOINTS
# =============================================================================


@router.post("/trigger", response_model=TriggerRemediationResponse)
async def trigger_remediation(
    request: TriggerRemediationRequest,
    background_tasks: BackgroundTasks,
) -> TriggerRemediationResponse:
    """
    Trigger a remediation run.
    
    Accepts a tribunal verdict and starts autonomous remediation.
    Returns immediately with run_id; use WebSocket or polling for progress.
    """
    engine = get_engine()
    
    # Check kill switch
    active, reason = is_kill_switch_active()
    if active:
        raise HTTPException(
            status_code=423,
            detail=f"Remediation disabled by kill switch: {reason}",
        )
    
    # Generate run ID
    import uuid
    run_id = str(uuid.uuid4())
    
    # Start remediation in background
    async def run_remediation():
        try:
            run = await engine.remediate(request.verdict, run_id)
            _active_runs[run_id] = run
        except Exception as e:
            # Create failed run
            from .models import RemediationStatus
            failed_run = RemediationRun(
                id=run_id,
                status=RemediationStatus.FAILED,
                error=str(e),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
            )
            _active_runs[run_id] = failed_run
    
    background_tasks.add_task(run_remediation)
    
    return TriggerRemediationResponse(
        run_id=run_id,
        status="started",
        message="Remediation started. Use WebSocket or GET /runs/{run_id} to monitor.",
    )


@router.get("/runs/{run_id}", response_model=RemediationRunResponse)
async def get_run(run_id: str) -> RemediationRunResponse:
    """Get details of a remediation run."""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    
    run = _active_runs[run_id]
    
    return RemediationRunResponse(
        id=run.id,
        verdict_id=run.verdict_id,
        status=run.status.value,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        iterations=run.iterations,
        issues_count=len(run.issues),
        fixes_applied=run.fixes_applied,
        fixes_reverted=run.fixes_reverted,
        health_state=run.health_state.value if run.health_state else None,
        error=run.error,
    )


@router.get("/runs", response_model=List[RemediationRunResponse])
async def list_runs(
    status: Optional[str] = None,
    limit: int = 20,
) -> List[RemediationRunResponse]:
    """List recent remediation runs."""
    runs = list(_active_runs.values())
    
    # Filter by status
    if status:
        runs = [r for r in runs if r.status.value == status]
    
    # Sort by start time
    runs.sort(key=lambda r: r.started_at or datetime.min, reverse=True)
    
    # Limit
    runs = runs[:limit]
    
    return [
        RemediationRunResponse(
            id=run.id,
            verdict_id=run.verdict_id,
            status=run.status.value,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else None,
            iterations=run.iterations,
            issues_count=len(run.issues),
            fixes_applied=run.fixes_applied,
            fixes_reverted=run.fixes_reverted,
            health_state=run.health_state.value if run.health_state else None,
            error=run.error,
        )
        for run in runs
    ]


@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str) -> Dict[str, str]:
    """Abort a running remediation."""
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Activate kill switch temporarily
    activate_kill_switch(
        reason=f"Manual abort of run {run_id}",
        activated_by="api",
    )
    
    return {"status": "abort_requested", "run_id": run_id}


@router.post("/approve", response_model=Dict[str, Any])
async def approve_fix(request: ApproveFixRequest) -> Dict[str, Any]:
    """
    Approve or reject a fix awaiting review.
    
    Used when fixes require CONFIRM or MANUAL approval level.
    """
    if request.run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    
    run = _active_runs[request.run_id]
    
    # Find the fix
    fix = next((f for f in run.fixes if f.id == request.fix_id), None)
    if not fix:
        raise HTTPException(status_code=404, detail="Fix not found")
    
    if request.approved:
        # Mark approved and trigger application
        fix.approval_level = ApprovalLevel.AUTO  # Effectively approved
        return {"status": "approved", "fix_id": fix.id}
    else:
        from .models import FixStatus
        fix.status = FixStatus.BLOCKED
        return {"status": "rejected", "fix_id": fix.id}


# =============================================================================
# KILL SWITCH ENDPOINTS
# =============================================================================


@router.get("/kill-switch", response_model=KillSwitchResponse)
async def get_kill_switch() -> KillSwitchResponse:
    """Get current kill switch status."""
    active, reason = is_kill_switch_active()
    
    return KillSwitchResponse(
        active=active,
        reason=reason,
        activated_at=None,  # Would come from DB
        activated_by=None,
    )


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def set_kill_switch(request: KillSwitchRequest) -> KillSwitchResponse:
    """Activate or deactivate the kill switch."""
    if request.active:
        activate_kill_switch(
            reason=request.reason or "Activated via API",
            activated_by=request.actor,
        )
    else:
        deactivate_kill_switch()
    
    active, reason = is_kill_switch_active()
    
    return KillSwitchResponse(
        active=active,
        reason=reason,
        activated_at=datetime.utcnow().isoformat() if active else None,
        activated_by=request.actor if active else None,
    )


# =============================================================================
# CONFIGURATION ENDPOINTS
# =============================================================================


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get current remediation configuration."""
    engine = get_engine()
    config = engine.config
    
    return ConfigResponse(
        enabled=config.enabled,
        auto_apply=config.auto_apply,
        max_iterations=config.max_iterations,
        safety={
            "max_files_per_run": config.safety.blast_radius.max_files_per_run,
            "max_lines_changed": config.safety.blast_radius.max_lines_changed,
            "forbidden_paths": config.safety.blast_radius.forbidden_paths,
            "max_fixes_per_hour": config.safety.rate_limits.max_fixes_per_hour,
            "auto_threshold": config.safety.approval.auto_threshold,
        },
    )


@router.patch("/config")
async def update_config(updates: Dict[str, Any]) -> ConfigResponse:
    """Update remediation configuration (runtime only)."""
    engine = get_engine()
    
    if "enabled" in updates:
        engine.config.enabled = bool(updates["enabled"])
    if "auto_apply" in updates:
        engine.config.auto_apply = bool(updates["auto_apply"])
    if "max_iterations" in updates:
        engine.config.max_iterations = int(updates["max_iterations"])
    
    return await get_config()


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time remediation updates.
    
    Clients receive events as JSON messages with structure:
    {
        "type": "event_type",
        "run_id": "uuid",
        "timestamp": "iso8601",
        "data": {...}
    }
    """
    await websocket.accept()
    _ws_connections.add(websocket)
    
    try:
        # Send current status
        await websocket.send_json({
            "type": "connected",
            "active_runs": len(_active_runs),
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Keep connection alive
        while True:
            try:
                # Wait for messages (ping/pong or commands)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0,
                )
                
                # Handle commands
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif message.get("type") == "subscribe":
                        # Could implement run-specific subscriptions
                        pass
                except json.JSONDecodeError:
                    pass
                    
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
    except WebSocketDisconnect:
        pass
    finally:
        _ws_connections.discard(websocket)


# =============================================================================
# STATS ENDPOINTS
# =============================================================================


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Get remediation statistics."""
    runs = list(_active_runs.values())
    
    total_runs = len(runs)
    completed = sum(1 for r in runs if r.status == RemediationStatus.COMPLETED)
    failed = sum(1 for r in runs if r.status == RemediationStatus.FAILED)
    total_fixes = sum(r.fixes_applied for r in runs)
    total_reverts = sum(r.fixes_reverted for r in runs)
    
    return {
        "total_runs": total_runs,
        "completed_runs": completed,
        "failed_runs": failed,
        "success_rate": completed / total_runs if total_runs > 0 else 0,
        "total_fixes_applied": total_fixes,
        "total_fixes_reverted": total_reverts,
        "revert_rate": total_reverts / total_fixes if total_fixes > 0 else 0,
    }


# =============================================================================
# PATTERNS ENDPOINT (for learning system)
# =============================================================================


@router.get("/patterns")
async def get_patterns() -> List[Dict[str, Any]]:
    """Get learned fix patterns."""
    # TODO: Implement pattern retrieval from database
    return []


@router.post("/patterns/feedback")
async def submit_pattern_feedback(
    pattern_id: str,
    helpful: bool,
    comment: Optional[str] = None,
) -> Dict[str, str]:
    """Submit feedback on a fix pattern."""
    # TODO: Implement pattern feedback
    return {"status": "recorded", "pattern_id": pattern_id}
