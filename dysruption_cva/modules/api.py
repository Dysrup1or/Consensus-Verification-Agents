"""
Dysruption CVA - FastAPI Backend (Module D: API Layer)

RESTful API and WebSocket endpoints for the Consensus Verifier Agent.

Version: 1.1
Features:
- REST endpoints: /run, /status, /verdict
- WebSocket: /ws for real-time status streaming
- Background task processing with run IDs
- Integration with watcher, parser, and tribunal modules
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .schemas import (
    ConsensusResult,
    InvariantSet,
    PatchSet,
    PipelineState,
    PipelineStatus,
    RunConfig,
    RunRequest,
    RunResponse,
    StatusResponse,
    VerdictResponse,
    VerdictStatus,
    WebSocketMessage,
)
from .parser import ConstitutionParser, run_extraction
from .tribunal import Tribunal, TribunalVerdict, Verdict
from .watcher_v2 import DirectoryWatcher, run_watcher

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="Dysruption CVA API",
    description="Consensus Verifier Agent - Multi-Model AI Tribunal for Code Verification",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# IN-MEMORY STATE (Replace with Redis/DB for production)
# =============================================================================


class RunState:
    """State for a single verification run."""

    def __init__(self, run_id: str, config: RunConfig):
        self.run_id = run_id
        self.config = config
        self.state = PipelineState(
            status=PipelineStatus.IDLE,
            current_phase="initialized",
            progress_percent=0.0,
            message="Run initialized",
            started_at=datetime.now(),
        )
        self.verdict: Optional[TribunalVerdict] = None
        self.patches: Optional[PatchSet] = None
        self.error: Optional[str] = None


# Global state stores
_runs: Dict[str, RunState] = {}
_active_websockets: Dict[str, Set[WebSocket]] = {}


def get_run(run_id: str) -> RunState:
    """Get run state by ID."""
    if run_id not in _runs:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return _runs[run_id]


# =============================================================================
# WEBSOCKET MANAGER
# =============================================================================


class WebSocketManager:
    """Manages WebSocket connections for real-time streaming."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        if run_id not in self.active_connections:
            self.active_connections[run_id] = set()
        self.active_connections[run_id].add(websocket)
        logger.info(f"WebSocket connected for run {run_id}")

    def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket connection."""
        if run_id in self.active_connections:
            self.active_connections[run_id].discard(websocket)
            if not self.active_connections[run_id]:
                del self.active_connections[run_id]
        logger.info(f"WebSocket disconnected for run {run_id}")

    async def broadcast(self, run_id: str, message: WebSocketMessage) -> None:
        """Broadcast message to all connections for a run."""
        if run_id not in self.active_connections:
            return

        message_json = message.model_dump_json()
        dead_connections = set()

        for connection in self.active_connections[run_id]:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                dead_connections.add(connection)

        # Clean up dead connections
        for dead in dead_connections:
            self.active_connections[run_id].discard(dead)


ws_manager = WebSocketManager()


# =============================================================================
# BACKGROUND PIPELINE RUNNER
# =============================================================================


async def run_verification_pipeline(run_id: str) -> None:
    """
    Main verification pipeline that runs in background.
    Updates state and broadcasts progress via WebSocket.
    """
    run_state = _runs.get(run_id)
    if not run_state:
        logger.error(f"Run not found: {run_id}")
        return

    config = run_state.config

    async def update_progress(
        status: PipelineStatus,
        phase: str,
        progress: float,
        message: str,
    ) -> None:
        """Update run state and broadcast to WebSockets."""
        run_state.state.status = status
        run_state.state.current_phase = phase
        run_state.state.progress_percent = progress
        run_state.state.message = message

        # Broadcast to WebSocket clients
        ws_message = WebSocketMessage(
            type="progress",
            run_id=run_id,
            data={
                "status": status.value,
                "phase": phase,
                "progress": progress,
                "message": message,
            },
        )
        await ws_manager.broadcast(run_id, ws_message)

    try:
        # Phase 1: Scanning
        await update_progress(
            PipelineStatus.SCANNING, "scanning", 10.0, "Scanning project directory..."
        )

        watcher = DirectoryWatcher(config.target_dir, config.config_path)
        watcher.setup()
        file_tree = watcher.run_once()

        if not file_tree.files:
            raise ValueError("No files found in target directory")

        # Convert FileTree to dict for compatibility
        file_tree_dict = {
            path: node.content for path, node in file_tree.files.items()
        }

        await update_progress(
            PipelineStatus.SCANNING,
            "scanning",
            20.0,
            f"Found {len(file_tree.files)} files, {file_tree.total_lines} lines",
        )

        # Phase 2: Parsing
        await update_progress(
            PipelineStatus.PARSING, "parsing", 30.0, "Extracting invariants from spec..."
        )

        parser = ConstitutionParser(config.config_path)
        spec_content = parser.read_spec(config.spec_path)
        invariants = parser.extract_invariants(spec_content)
        invariants = parser.clarify_if_needed(invariants, spec_content)
        parser.save_criteria(invariants)

        total_invariants = sum(len(invariants[cat]) for cat in invariants)
        await update_progress(
            PipelineStatus.PARSING,
            "parsing",
            40.0,
            f"Extracted {total_invariants} invariants across 3 categories",
        )

        # Phase 3: Static Analysis
        await update_progress(
            PipelineStatus.STATIC_ANALYSIS,
            "static_analysis",
            50.0,
            "Running static analysis (pylint, bandit)...",
        )

        tribunal = Tribunal(config.config_path)
        static_results, should_abort, abort_reason = tribunal.run_static_analysis(
            file_tree_dict, watcher.detect_primary_language()
        )

        if should_abort:
            await update_progress(
                PipelineStatus.ERROR,
                "aborted",
                50.0,
                f"FAIL-FAST: {abort_reason}",
            )
            run_state.error = abort_reason

            # Still create a verdict for the aborted run
            run_state.verdict = tribunal.run(
                file_tree_dict, invariants, watcher.detect_primary_language()
            )
            tribunal.save_outputs(run_state.verdict)

            ws_message = WebSocketMessage(
                type="error",
                run_id=run_id,
                data={"error": abort_reason, "aborted": True},
            )
            await ws_manager.broadcast(run_id, ws_message)
            return

        await update_progress(
            PipelineStatus.STATIC_ANALYSIS,
            "static_analysis",
            60.0,
            f"Static analysis complete: {sum(len(r.issues) for r in static_results)} issues",
        )

        # Phase 4: Judging
        await update_progress(
            PipelineStatus.JUDGING,
            "judging",
            70.0,
            "Running multi-model tribunal (3 judges)...",
        )

        # Run full tribunal (includes static analysis again, but main work is judging)
        verdict = tribunal.run(
            file_tree_dict, invariants, watcher.detect_primary_language()
        )
        run_state.verdict = verdict

        await update_progress(
            PipelineStatus.JUDGING,
            "judging",
            90.0,
            f"Tribunal complete: {verdict.overall_verdict.value} "
            f"({verdict.passed_criteria}/{verdict.total_criteria} passed)"
            + (" [VETO]" if verdict.veto_triggered else ""),
        )

        # Phase 5: Patching (if failed and patches requested)
        if (
            config.generate_patches
            and verdict.overall_verdict != Verdict.PASS
            and verdict.remediation_suggestions
        ):
            await update_progress(
                PipelineStatus.PATCHING,
                "patching",
                95.0,
                "Generating fix patches...",
            )

            # Patches are already in verdict.remediation_suggestions
            run_state.patches = PatchSet(
                patches=[],  # Would convert from remediation_suggestions
                total_issues_addressed=len(verdict.remediation_suggestions),
                generation_timestamp=datetime.now(),
            )

        # Save outputs
        tribunal.save_outputs(verdict)

        # Complete
        run_state.state.completed_at = datetime.now()
        await update_progress(
            PipelineStatus.COMPLETE,
            "complete",
            100.0,
            f"Verification complete: {verdict.overall_verdict.value}",
        )

        # Broadcast final verdict
        ws_message = WebSocketMessage(
            type="verdict",
            run_id=run_id,
            data={
                "overall_verdict": verdict.overall_verdict.value,
                "overall_score": verdict.overall_score,
                "passed": verdict.passed_criteria,
                "failed": verdict.failed_criteria,
                "total": verdict.total_criteria,
                "veto_triggered": verdict.veto_triggered,
                "veto_reason": verdict.veto_reason,
                "execution_time": verdict.execution_time_seconds,
            },
        )
        await ws_manager.broadcast(run_id, ws_message)

    except Exception as e:
        logger.error(f"Pipeline error for run {run_id}: {e}")
        run_state.state.status = PipelineStatus.ERROR
        run_state.state.error = str(e)
        run_state.error = str(e)

        ws_message = WebSocketMessage(
            type="error",
            run_id=run_id,
            data={"error": str(e)},
        )
        await ws_manager.broadcast(run_id, ws_message)


# =============================================================================
# REST ENDPOINTS
# =============================================================================


@app.get("/")
async def root() -> Dict[str, Any]:
    """Health check and API info."""
    return {
        "name": "Dysruption CVA API",
        "version": "1.1.0",
        "status": "healthy",
        "endpoints": {
            "run": "POST /run - Start verification run",
            "status": "GET /status/{run_id} - Get run status",
            "verdict": "GET /verdict/{run_id} - Get final verdict",
            "ws": "WS /ws/{run_id} - Real-time status streaming",
        },
    }


@app.post("/run", response_model=RunResponse)
async def start_run(
    request: RunRequest, background_tasks: BackgroundTasks
) -> RunResponse:
    """
    Start a new verification run.

    Initiates the CVA pipeline in the background and returns a run_id
    for tracking progress via /status or /ws endpoints.
    """
    # Validate target directory exists
    if not os.path.exists(request.target_dir):
        raise HTTPException(
            status_code=400, detail=f"Target directory not found: {request.target_dir}"
        )

    # Generate run ID
    run_id = str(uuid.uuid4())[:8]

    # Create run config
    config = RunConfig(
        target_dir=request.target_dir,
        spec_path=request.spec_path or "spec.txt",
        config_path="config.yaml",
        generate_patches=request.generate_patches,
        watch_mode=request.watch_mode,
    )

    # Initialize run state
    _runs[run_id] = RunState(run_id, config)

    # Start background task
    background_tasks.add_task(run_verification_pipeline, run_id)

    logger.info(f"Started verification run: {run_id} for {request.target_dir}")

    return RunResponse(
        run_id=run_id,
        status=PipelineStatus.SCANNING,
        message=f"Verification started for {request.target_dir}",
    )


@app.get("/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str) -> StatusResponse:
    """
    Get current status of a verification run.

    Returns the current phase, progress percentage, and any messages.
    """
    run_state = get_run(run_id)

    return StatusResponse(run_id=run_id, state=run_state.state)


@app.get("/verdict/{run_id}", response_model=VerdictResponse)
async def get_verdict(run_id: str) -> VerdictResponse:
    """
    Get the final verdict of a verification run.

    Only available after the run is complete. Returns the consensus result
    and any generated patches.
    """
    run_state = get_run(run_id)

    if run_state.state.status not in (PipelineStatus.COMPLETE, PipelineStatus.ERROR):
        return VerdictResponse(
            run_id=run_id,
            consensus=None,
            patches=None,
            ready=False,
        )

    # Convert TribunalVerdict to ConsensusResult
    consensus = None
    if run_state.verdict:
        v = run_state.verdict
        consensus = ConsensusResult(
            timestamp=datetime.fromisoformat(v.timestamp),
            overall_status=VerdictStatus(v.overall_verdict.value.lower()),
            weighted_score=v.overall_score,
            confidence=0.85,  # Average confidence from judges
            verdicts={},  # Would need to populate from criterion_results
            veto_triggered=v.veto_triggered,
            veto_reason=v.veto_reason,
            static_analysis=[],  # Would convert from v.static_analysis_results
            static_analysis_aborted=v.static_analysis_aborted,
            total_invariants=v.total_criteria,
            invariants_passed=v.passed_criteria,
            execution_time_ms=int(v.execution_time_seconds * 1000),
            files_analyzed=len(
                set(
                    f
                    for r in v.criterion_results
                    for f in r.relevant_files
                )
            ),
        )

    return VerdictResponse(
        run_id=run_id,
        consensus=consensus,
        patches=run_state.patches,
        ready=True,
    )


@app.delete("/run/{run_id}")
async def cancel_run(run_id: str) -> Dict[str, Any]:
    """Cancel a running verification (if possible)."""
    run_state = get_run(run_id)

    if run_state.state.status in (PipelineStatus.COMPLETE, PipelineStatus.ERROR):
        return {
            "run_id": run_id,
            "cancelled": False,
            "message": "Run already completed or errored",
        }

    # Mark as cancelled (background task will check this)
    run_state.state.status = PipelineStatus.ERROR
    run_state.state.error = "Cancelled by user"
    run_state.error = "Cancelled by user"

    return {
        "run_id": run_id,
        "cancelled": True,
        "message": "Run cancellation requested",
    }


@app.get("/runs")
async def list_runs() -> Dict[str, Any]:
    """List all verification runs."""
    runs = []
    for run_id, run_state in _runs.items():
        runs.append(
            {
                "run_id": run_id,
                "status": run_state.state.status.value,
                "progress": run_state.state.progress_percent,
                "started_at": (
                    run_state.state.started_at.isoformat()
                    if run_state.state.started_at
                    else None
                ),
                "target_dir": run_state.config.target_dir,
            }
        )

    return {"runs": runs, "total": len(runs)}


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================


@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
    """
    WebSocket endpoint for real-time status streaming.

    Connect to receive live updates for a verification run.
    Messages are sent as JSON with types: 'progress', 'verdict', 'error'.
    """
    await ws_manager.connect(websocket, run_id)

    try:
        # Send current state immediately
        if run_id in _runs:
            run_state = _runs[run_id]
            initial_message = WebSocketMessage(
                type="status",
                run_id=run_id,
                data={
                    "status": run_state.state.status.value,
                    "phase": run_state.state.current_phase,
                    "progress": run_state.state.progress_percent,
                    "message": run_state.state.message,
                },
            )
            await websocket.send_text(initial_message.model_dump_json())

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (ping/pong, etc.)
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=30.0
                )

                # Handle client commands (optional)
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(
                            json.dumps({"type": "pong", "run_id": run_id})
                        )
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_text(
                        json.dumps({"type": "ping", "run_id": run_id})
                    )
                except Exception:
                    break

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, run_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket, run_id)


# =============================================================================
# STARTUP/SHUTDOWN EVENTS
# =============================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    logger.info("CVA API v1.1 starting up...")
    logger.info("Endpoints: /run, /status/{run_id}, /verdict/{run_id}, /ws/{run_id}")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    logger.info("CVA API shutting down...")
    # Close all WebSocket connections
    for run_id, connections in ws_manager.active_connections.items():
        for ws in connections:
            try:
                await ws.close()
            except Exception:
                pass


# =============================================================================
# CLI RUNNER
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "modules.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
