"""
Dysruption CVA - FastAPI Backend (Module D: API Layer)

RESTful API and WebSocket endpoints for the Consensus Verifier Agent.

Version: 1.2
Features:
- REST endpoints: /run, /status, /verdict, /prompt
- WebSocket: /ws for real-time status streaming
- Background task processing with run IDs
- Integration with watcher, parser, tribunal, and prompt synthesizer modules
"""

from __future__ import annotations

# Load environment variables from .env file FIRST
import os
from pathlib import Path
from dotenv import load_dotenv

# Find the .env file (in the project root, same level as modules/)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[+] Loaded .env from {env_path}")
else:
    print(f"[!] No .env file found at {env_path}")

import asyncio
import json
import uuid
import aiofiles
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

import yaml
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    File,
    UploadFile,
    Form,
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
from .prompt_synthesizer import PromptSynthesizer, PromptRecommendation, synthesize_fix_prompt

# =============================================================================
# APP INITIALIZATION
# =============================================================================

app = FastAPI(
    title="Dysruption CVA API",
    description="Consensus Verifier Agent - Multi-Model AI Tribunal for Code Verification",
    version="1.2.0",
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

HISTORY_FILE = Path("run_history.json")

def load_run_history() -> Dict[str, RunState]:
    """Load run history from disk."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(HISTORY_FILE.read_text())
        # Note: This is a simplified reconstruction. 
        # In a real app, we'd need full serialization/deserialization logic.
        # For now, we just return empty to avoid complex object reconstruction issues
        # but we keep the file for persistence.
        return {} 
    except Exception as e:
        logger.error(f"Failed to load history: {e}")
        return {}

def save_run_history(run_state: RunState):
    """Append run state to history file."""
    try:
        history = {}
        if HISTORY_FILE.exists():
            try:
                history = json.loads(HISTORY_FILE.read_text())
            except:
                pass
        
        # Serialize run state
        run_data = {
            "run_id": run_state.run_id,
            "status": run_state.state.status.value,
            "verdict": run_state.verdict.overall_verdict.value if run_state.verdict else None,
            "timestamp": datetime.now().isoformat(),
            "target_dir": run_state.config.target_dir
        }
        
        history[run_state.run_id] = run_data
        HISTORY_FILE.write_text(json.dumps(history, indent=2))
    except Exception as e:
        logger.error(f"Failed to save history: {e}")


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
        # New fields for prompt synthesis
        self.spec_summary: Optional[str] = None
        self.file_tree: Optional[Dict[str, str]] = None
        self.prompt_recommendation: Optional[Dict[str, Any]] = None


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
        
        # Store file tree for prompt synthesis later
        run_state.file_tree = file_tree_dict

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
        
        # Use spec_content if provided directly, otherwise read from file
        if config.spec_content:
            spec_content = config.spec_content
            logger.info("Using provided spec content (constitution text)")
        else:
            spec_content = parser.read_spec(config.spec_path)
            logger.info(f"Read spec from file: {config.spec_path}")
        
        # Store spec summary for prompt synthesis later
        run_state.spec_summary = spec_content
        
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
        
        # Yield to event loop before long-running sync operation
        await asyncio.sleep(0)

        tribunal = Tribunal(config.config_path)
        
        # Run static analysis in executor to not block event loop
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            static_results, should_abort, abort_reason = await loop.run_in_executor(
                executor,
                lambda: tribunal.run_static_analysis(file_tree_dict, watcher.detect_primary_language())
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
            # FIX: Pass precomputed results to avoid re-running static analysis (Double Jeopardy)
            run_state.verdict = tribunal.run(
                file_tree_dict, 
                invariants, 
                watcher.detect_primary_language(),
                precomputed_static_results=(static_results, should_abort, abort_reason)
            )
            tribunal.save_outputs(run_state.verdict)
            
            # Save run state to disk immediately
            save_run_history(run_state)

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
        # FIX: Pass precomputed results here too for efficiency
        verdict = tribunal.run(
            file_tree_dict, 
            invariants, 
            watcher.detect_primary_language(),
            precomputed_static_results=(static_results, should_abort, abort_reason)
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
        
        # Save run state to disk
        save_run_history(run_state)
        
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
    """
    Deep Health Check & API Info.
    Verifies file system permissions and API key presence.
    """
    health_status = {
        "name": "Dysruption CVA API",
        "version": "1.1.0",
        "status": "healthy",
        "checks": {
            "filesystem": "unknown",
            "api_keys": "unknown",
        },
        "endpoints": {
            "run": "POST /run - Start verification run",
            "upload": "POST /upload - Upload files for analysis",
            "status": "GET /status/{run_id} - Get run status",
            "verdict": "GET /verdict/{run_id} - Get final verdict",
            "ws": "WS /ws/{run_id} - Real-time status streaming",
        },
    }

    # 1. File System Check
    try:
        test_file = Path(os.getcwd()) / "temp_uploads" / ".healthcheck"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("ok")
        test_file.unlink()
        health_status["checks"]["filesystem"] = "ok"
    except Exception as e:
        health_status["checks"]["filesystem"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # 2. API Key Check
    # Check for common LLM keys. At least one should be present.
    keys_present = []
    for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_API_KEY", "LITELLM_API_KEY"]:
        if os.environ.get(key):
            keys_present.append(key)
    
    if keys_present:
        health_status["checks"]["api_keys"] = "ok"
    else:
        health_status["checks"]["api_keys"] = "missing (OPENAI_API_KEY, etc.)"
        # We don't mark as degraded yet as user might rely on local models, 
        # but it's good info.

    return health_status


@app.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(...),
    upload_id: Optional[str] = Form(None)
) -> Dict[str, Any]:
    """
    Upload files for analysis. Supports batching via upload_id.
    
    - If upload_id is None: Creates new session.
    - If upload_id is provided: Appends to existing session.
    """
    # Validate or create upload_id
    if upload_id:
        # Security check: Alphanumeric only to prevent traversal
        if not upload_id.isalnum():
             raise HTTPException(status_code=400, detail="Invalid upload_id")
        # Use existing directory
        temp_dir = Path(os.getcwd()) / "temp_uploads" / upload_id
        if not temp_dir.exists():
             # If it doesn't exist (expired?), create it
             temp_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Create new session
        upload_id = str(uuid.uuid4())[:8]
        temp_dir = Path(os.getcwd()) / "temp_uploads" / upload_id
        temp_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Upload {upload_id}: Processing batch of {len(files)} files")
    
    saved_count = 0
    
    try:
        # Iterate through files and paths (they should match by index)
        for i, file in enumerate(files):
            # Get relative path from form data, or fallback to filename
            rel_path = paths[i] if i < len(paths) else file.filename
            
            # Sanitize path to prevent directory traversal
            clean_rel_path = rel_path.lstrip("/").lstrip("\\").replace("..", "")
            
            # Construct full path
            file_path = temp_dir / clean_rel_path
            
            # Ensure parent directories exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save file using streaming
            async with aiofiles.open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    await f.write(chunk)
            
            saved_count += 1
            
        logger.info(f"Upload {upload_id}: Batch complete, saved {saved_count} files")
        
        return {
            "upload_id": upload_id,
            "path": str(temp_dir.absolute()),
            "count": saved_count,
            "message": f"Successfully uploaded batch of {saved_count} files"
        }
        
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        # Note: We do NOT delete the dir on error anymore, to allow retrying batches
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")



@app.post("/run", response_model=RunResponse)
async def start_run(
    request: RunRequest, background_tasks: BackgroundTasks
) -> RunResponse:
    """
    Start a new verification run.

    Initiates the CVA pipeline in the background and returns a run_id
    for tracking progress via /status or /ws endpoints.
    """
    target_dir = request.target_dir.strip()
    
    # =========================================================================
    # PATH VALIDATION (Bulletproof security checks)
    # =========================================================================
    
    # Check for empty path
    if not target_dir:
        raise HTTPException(
            status_code=400, 
            detail="Target directory cannot be empty. Please provide an absolute path."
        )
    
    # Check for file picker placeholder (frontend bug prevention)
    if target_dir.startswith('[') and target_dir.endswith(']'):
        raise HTTPException(
            status_code=400,
            detail="Invalid path format. Browser file picker cannot provide actual paths. "
                   "Please manually enter the absolute path to your project (e.g., C:\\Users\\...\\my-project)"
        )
    
    # Check for relative paths (dangerous - resolves to backend CWD)
    if target_dir in ('.', '..') or target_dir.startswith('./') or target_dir.startswith('../'):
        raise HTTPException(
            status_code=400,
            detail="Relative paths are not allowed. Please provide an absolute path "
                   "(e.g., C:\\Users\\...\\my-project or /home/user/projects/my-project)"
        )
    
    # Check for absolute path (Windows or Unix)
    is_absolute_windows = len(target_dir) >= 3 and target_dir[1] == ':' and target_dir[2] in ('\\', '/')
    is_absolute_unix = target_dir.startswith('/')
    
    if not is_absolute_windows and not is_absolute_unix:
        raise HTTPException(
            status_code=400,
            detail=f"Path must be absolute. Received: '{target_dir}'. "
                   "Please use a full path starting with a drive letter (C:\\...) or forward slash (/...)"
        )
    
    # Prevent self-scanning (CVA analyzing its own codebase)
    # BUT: Allow temp_uploads paths - these contain USER-uploaded code, not CVA source
    target_lower = target_dir.lower().replace('/', '\\')
    
    is_temp_upload = 'temp_uploads' in target_lower
    
    if not is_temp_upload:
        # Only check path-based patterns if NOT a temp_upload
        dangerous_patterns = [
            'consensus verifier agent',
            'dysruption_cva',
            'dysruption-ui',
            'cva\\modules',
            'cva/modules',
        ]
        
        for pattern in dangerous_patterns:
            if pattern in target_lower:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot scan the CVA application itself (detected: '{pattern}'). "
                           "Please select your target project directory, not the CVA installation."
                )
    
    # ROBUST CHECK: Look for actual CVA source files regardless of path
    cva_signature_files = [
        os.path.join(target_dir, 'modules', 'tribunal.py'),
        os.path.join(target_dir, 'modules', 'api.py'),
        os.path.join(target_dir, 'cva.py'),
    ]
    
    cva_files_found = [f for f in cva_signature_files if os.path.exists(f)]
    if len(cva_files_found) >= 2:
        raise HTTPException(
            status_code=400,
            detail="Cannot scan the CVA application itself. "
                   "Detected CVA source files in target directory. "
                   "Please select your target project directory, not the CVA installation."
        )
    
    # Validate target directory exists
    if not os.path.exists(target_dir):
        raise HTTPException(
            status_code=400, detail=f"Target directory not found: {target_dir}"
        )
    
    # Validate it's actually a directory
    if not os.path.isdir(target_dir):
        raise HTTPException(
            status_code=400, detail=f"Path is not a directory: {target_dir}"
        )

    # =========================================================================
    # START THE RUN
    # =========================================================================
    
    # Generate run ID
    run_id = str(uuid.uuid4())[:8]

    # Create run config
    config = RunConfig(
        target_dir=target_dir,
        spec_path=request.spec_path or "spec.txt",
        spec_content=request.spec_content,  # Pass constitution text if provided
        config_path="config.yaml",
        generate_patches=request.generate_patches,
        watch_mode=request.watch_mode,
    )

    # Initialize run state
    _runs[run_id] = RunState(run_id, config)

    # Start background task
    background_tasks.add_task(run_verification_pipeline, run_id)

    logger.info(f"Started verification run: {run_id} for {target_dir}")

    return RunResponse(
        run_id=run_id,
        status=PipelineStatus.SCANNING,
        message=f"Verification started for {target_dir}",
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

    Only available after the run is complete. Returns the consensus result,
    any generated patches, AND the raw report/diff content for frontend download.
    """
    run_state = get_run(run_id)

    if run_state.state.status not in (PipelineStatus.COMPLETE, PipelineStatus.ERROR):
        return VerdictResponse(
            run_id=run_id,
            consensus=None,
            patches=None,
            ready=False,
            report_markdown=None,
            patch_diff=None,
        )

    # Convert TribunalVerdict to ConsensusResult
    consensus = None
    report_markdown = None
    patch_diff = None
    
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
        
        # Load REPORT.md content if it exists
        try:
            report_path = Path("REPORT.md")
            if report_path.exists():
                report_markdown = report_path.read_text(encoding="utf-8")
                logger.info(f"Loaded REPORT.md: {len(report_markdown)} chars")
        except Exception as e:
            logger.warning(f"Could not load REPORT.md: {e}")
    
    # Combine all patch diffs into a single string
    if run_state.patches and run_state.patches.patches:
        patch_diff = "\n\n".join(
            f"# {p.file_path}\n{p.unified_diff}" 
            for p in run_state.patches.patches
        )
        logger.info(f"Combined {len(run_state.patches.patches)} patches into diff")

    return VerdictResponse(
        run_id=run_id,
        consensus=consensus,
        patches=run_state.patches,
        ready=True,
        report_markdown=report_markdown,
        patch_diff=patch_diff,
    )


@app.get("/prompt/{run_id}")
async def get_fix_prompt(run_id: str) -> Dict[str, Any]:
    """
    Generate a synthesized fix prompt for a failed verification run.
    
    Returns a comprehensive, actionable prompt that can be given to an AI
    coding assistant (Claude, GPT-4, Copilot) to fix the identified issues.
    
    Only available after verification is complete and has issues to fix.
    """
    run_state = get_run(run_id)

    if run_state.state.status not in (PipelineStatus.COMPLETE, PipelineStatus.ERROR):
        return {
            "run_id": run_id,
            "ready": False,
            "message": "Verification not yet complete",
            "prompt": None,
        }

    if not run_state.verdict:
        return {
            "run_id": run_id,
            "ready": False,
            "message": "No verdict available",
            "prompt": None,
        }

    # Check if already generated
    if run_state.prompt_recommendation:
        return {
            "run_id": run_id,
            "ready": True,
            "message": "Fix prompt generated",
            "prompt": run_state.prompt_recommendation,
        }

    # Check if actually needs fixing
    v = run_state.verdict
    if v.overall_verdict == Verdict.PASS:
        return {
            "run_id": run_id,
            "ready": True,
            "message": "No issues to fix - verification passed!",
            "prompt": {
                "primary_prompt": "✅ Congratulations! Your code passed all verification checks.",
                "priority_issues": [],
                "strategy": "No fixes needed",
                "complexity": "none",
                "alternative_prompts": [],
                "context_files": [],
            },
        }

    # Generate fix prompt using synthesizer
    try:
        # Convert TribunalVerdict to dict for synthesizer
        verdict_data = {
            "overall_verdict": v.overall_verdict.value,
            "overall_score": v.overall_score,
            "veto_triggered": v.veto_triggered,
            "veto_reason": v.veto_reason,
            "criterion_results": [
                {
                    "criterion_type": cr.criterion_type,
                    "criterion_desc": cr.criterion_desc,
                    "average_score": cr.average_score,
                    "veto_triggered": cr.veto_triggered,
                    "relevant_files": cr.relevant_files,
                    "scores": [
                        {
                            "judge_name": s.judge_name,
                            "score": s.score,
                            "issues": s.issues,
                            "suggestions": s.suggestions,
                        }
                        for s in cr.scores
                    ],
                }
                for cr in v.criterion_results
            ],
            "static_analysis_results": [
                {
                    "tool": sar.tool,
                    "file_path": sar.file_path,
                    "issues": sar.issues,
                    "has_critical": sar.has_critical,
                }
                for sar in v.static_analysis_results
            ],
        }

        # Get spec summary
        spec_summary = run_state.spec_summary or "No specification available"

        # Get file tree
        file_tree = run_state.file_tree

        # Synthesize the prompt
        recommendation = synthesize_fix_prompt(
            verdict_data=verdict_data,
            spec_summary=spec_summary,
            file_tree=file_tree,
            config_path=run_state.config.config_path,
        )

        # Cache the result
        run_state.prompt_recommendation = recommendation.to_dict()

        return {
            "run_id": run_id,
            "ready": True,
            "message": "Fix prompt generated successfully",
            "prompt": run_state.prompt_recommendation,
        }

    except Exception as e:
        logger.error(f"Failed to generate fix prompt for run {run_id}: {e}")
        return {
            "run_id": run_id,
            "ready": False,
            "message": f"Failed to generate fix prompt: {str(e)}",
            "prompt": None,
        }


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
