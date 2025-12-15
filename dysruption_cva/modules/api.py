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
from collections import defaultdict
import hmac
import json
import uuid
import aiofiles
import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from .schemas import (
    ConsensusResult,
    ConstitutionHistoryItem,
    ConstitutionInfo,
    InvariantSet,
    IntentEnvelope,
    PatchSet,
    PipelineState,
    PipelineStatus,
    RunConfig,
    RunRequest,
    RunResponse,
    StatusResponse,
    SuccessSpec,
    TriggerScanRequest,
    TriggerScanResponse,
    VerdictResponse,
    VerdictStatus,
    WebSocketMessage,
    RunTelemetry,
)
from .parser import ConstitutionParser, run_extraction
from .tribunal import Tribunal, TribunalVerdict, Verdict
from .watcher_v2 import DirectoryWatcher, run_watcher
from .prompt_synthesizer import PromptSynthesizer, PromptRecommendation, synthesize_fix_prompt
from .file_manager import (
    build_llm_context,
    detect_changed_files,
    get_project_root,
    is_git_repo,
    resolve_imports,
)
from .judge_engine import default_min_constitution, judge_engine
from .coverage_store import get_coverage_map, upsert_coverage
from .router import RouterError, RouterRequest, load_router_config_from_env
from .router import route as route_llm
from .self_heal import SelfHealError
from .self_heal import config_from_env as self_heal_config_from_env
from .self_heal import default_verify_command_from_env
from .self_heal import run_self_heal_patch_loop

# =============================================================================
# APP INITIALIZATION
# =============================================================================

# Security configuration from environment
PRODUCTION_MODE = os.getenv("CVA_PRODUCTION", "false").lower() == "true"
ALLOWED_ORIGINS = os.getenv("CVA_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
MAX_UPLOAD_SIZE_MB = int(os.getenv("CVA_MAX_UPLOAD_MB", "100"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("CVA_RATE_LIMIT", "30"))
API_TOKEN = os.getenv("CVA_API_TOKEN", "")

# Tribunal API configuration
TRIBUNAL_INTENT_TTL_SECONDS = int(os.getenv("CVA_INTENT_TTL_SECONDS", "600"))
TRIBUNAL_TOKEN_BUDGET = int(os.getenv("CVA_TRIBUNAL_TOKEN_BUDGET", "8000"))
TRIBUNAL_MTIME_WINDOW_SECONDS = int(os.getenv("CVA_TRIBUNAL_MTIME_WINDOW_SECONDS", "300"))
TRIBUNAL_RATE_LIMIT_PER_MINUTE = int(os.getenv("CVA_TRIBUNAL_RATE_LIMIT", "60"))
TRIBUNAL_INTENT_LLM_MODEL = os.getenv("CVA_TRIBUNAL_INTENT_MODEL", "openai/gpt-4o-mini")
TRIBUNAL_LLM_TIMEOUT_SECONDS = int(os.getenv("CVA_TRIBUNAL_LLM_TIMEOUT_SECONDS", "45"))

# Where uploads and per-run artifacts are stored.
# In Railway, mount the volume at /app/temp_uploads and set CVA_UPLOAD_ROOT accordingly if needed.
UPLOAD_ROOT = Path(os.getenv("CVA_UPLOAD_ROOT", str(Path(os.getcwd()) / "temp_uploads")))
RUN_ARTIFACTS_ROOT = Path(os.getenv("CVA_RUN_ARTIFACTS_ROOT", str(Path(os.getcwd()) / "run_artifacts")))

# Rate limiting state (simple in-memory, use Redis for production)
_rate_limit_tracker: Dict[str, List[float]] = defaultdict(list)

def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    window = 60.0  # 1 minute window
    
    # Clean old entries
    _rate_limit_tracker[client_ip] = [
        t for t in _rate_limit_tracker[client_ip] if now - t < window
    ]
    
    # Check limit
    if len(_rate_limit_tracker[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return False
    
    _rate_limit_tracker[client_ip].append(now)
    return True


def _get_bearer_or_header_token(request: Request) -> str:
    """Extract auth token from Authorization: Bearer ... or X-API-Token."""
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    header_token = request.headers.get("x-api-token") or request.headers.get("X-API-Token")
    if header_token:
        return header_token.strip()
    return ""


def _require_api_token(request: Request) -> None:
    """Require shared token for sensitive endpoints in production mode."""
    if not PRODUCTION_MODE:
        return

    if not API_TOKEN:
        # Fail closed if production is enabled but token isn't configured.
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: CVA_API_TOKEN must be set when CVA_PRODUCTION=true",
        )

    provided = _get_bearer_or_header_token(request)
    if not provided:
        raise HTTPException(
            status_code=401,
            detail="Missing auth token. Provide Authorization: Bearer <token> or X-API-Token header.",
        )

    if not hmac.compare_digest(provided, API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid auth token")


def _require_tribunal_api_token(request: Request) -> None:
    """Require shared token for Tribunal endpoints.

    Requirement: Bearer API Key is required for POST /api/intent and POST /api/trigger_scan.
    We use CVA_API_TOKEN as the shared key.
    """

    if not API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: CVA_API_TOKEN must be set for Tribunal API",
        )

    provided = _get_bearer_or_header_token(request)
    if not provided:
        raise HTTPException(
            status_code=401,
            detail="Missing auth token. Provide Authorization: Bearer <token> or X-API-Token header.",
        )

    if not hmac.compare_digest(provided, API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid auth token")


def _sanitize_str(value: str, *, max_len: int = 2000) -> str:
    value = value or ""
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_len]


def _tribunal_rate_limit_key(project_id: str, origin: str) -> str:
    # Rate limit by project and origin (requirement). Origin may be empty.
    return f"tribunal:{project_id}:{origin}"


_tribunal_rate_limit_tracker: Dict[str, List[float]] = defaultdict(list)


def check_tribunal_rate_limit(project_id: str, origin: str) -> bool:
    now = time.time()
    window = 60.0
    key = _tribunal_rate_limit_key(project_id, origin)
    _tribunal_rate_limit_tracker[key] = [t for t in _tribunal_rate_limit_tracker[key] if now - t < window]
    if len(_tribunal_rate_limit_tracker[key]) >= TRIBUNAL_RATE_LIMIT_PER_MINUTE:
        return False
    _tribunal_rate_limit_tracker[key].append(now)
    return True


class _TTLStore:
    def __init__(self):
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        async with self._lock:
            self._data[key] = (time.time() + ttl_seconds, value)

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._data:
                return None
            expires_at, value = self._data[key]
            if time.time() > expires_at:
                self._data.pop(key, None)
                return None
            return value

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)


_intent_store = _TTLStore()
_tribunal_run_store = _TTLStore()  # stores status, results, and error details

# Constitution cache: (project_root, commit_hash) -> constitution_text
_constitution_cache: Dict[Tuple[str, str], str] = {}


def _find_constitution_path(project_root: Path) -> Path:
    # Source of truth per requirement: ./.tribunal/constitution.md (or .txt)
    md = project_root / ".tribunal" / "constitution.md"
    txt = project_root / ".tribunal" / "constitution.txt"
    if md.exists():
        return md
    if txt.exists():
        return txt
    return md


def _get_git_commit_for_path(project_root: Path, rel_path: str) -> Optional[str]:
    try:
        from git import Repo

        repo = Repo(str(project_root))
        commits = list(repo.iter_commits(paths=rel_path, max_count=1))
        if commits:
            return commits[0].hexsha
    except Exception:
        return None
    return None


def _get_git_history_for_path(project_root: Path, rel_path: str, max_items: int = 20) -> List[ConstitutionHistoryItem]:
    try:
        from git import Repo

        repo = Repo(str(project_root))
        out: List[ConstitutionHistoryItem] = []
        for c in repo.iter_commits(paths=rel_path, max_count=max_items):
            out.append(
                ConstitutionHistoryItem(
                    commit_hash=c.hexsha,
                    author=str(getattr(c, "author", "") or "") or None,
                    authored_at=str(getattr(c, "authored_datetime", "") or "") or None,
                    subject=str(getattr(c, "summary", "") or "") or None,
                )
            )
        return out
    except Exception:
        return []


def _load_constitution(project_root: Path, commit_hash: Optional[str] = None) -> Tuple[str, ConstitutionInfo]:
    constitution_path = _find_constitution_path(project_root)
    rel = constitution_path.relative_to(project_root).as_posix() if constitution_path.exists() else ".tribunal/constitution.md"

    git_commit = None
    if is_git_repo(project_root) and constitution_path.exists():
        git_commit = _get_git_commit_for_path(project_root, rel)

    cache_key_commit = commit_hash or git_commit or ""
    cache_key = (str(project_root.resolve()), cache_key_commit)

    if cache_key_commit and cache_key in _constitution_cache:
        text = _constitution_cache[cache_key]
        return text, ConstitutionInfo(path=rel, commit_hash=cache_key_commit, snippet_length=min(len(text), 512))

    if constitution_path.exists():
        try:
            text = constitution_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = default_min_constitution()
    else:
        text = default_min_constitution()

    if cache_key_commit:
        _constitution_cache[cache_key] = text

    return text, ConstitutionInfo(path=rel, commit_hash=cache_key_commit or None, snippet_length=min(len(text), 512))


def _is_path_within_root(target_dir: str, allowed_root: Path) -> bool:
    try:
        target = Path(target_dir).resolve()
        root = allowed_root.resolve()
        return target.is_relative_to(root)
    except Exception:
        return False


def _create_run_artifacts(run_id: str, base_config_path: str) -> Tuple[Path, Path]:
    """Create per-run artifacts directory and a derived config.yaml with per-run output paths."""
    run_dir = (RUN_ARTIFACTS_ROOT / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    # Load base config (best-effort)
    base_path = Path(base_config_path)
    if not base_path.is_absolute():
        base_path = (Path(os.getcwd()) / base_path).resolve()

    cfg: Dict[str, Any] = {}
    try:
        if base_path.exists():
            cfg = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        logger.warning(f"Failed to load base config '{base_path}': {e}")
        cfg = {}

    output_cfg = cfg.get("output") or {}
    output_cfg["report_file"] = str(run_dir / "REPORT.md")
    output_cfg["verdict_file"] = str(run_dir / "verdict.json")
    output_cfg["criteria_file"] = str(run_dir / "criteria.json")
    cfg["output"] = output_cfg

    derived_path = run_dir / "config.yaml"
    derived_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    return run_dir, derived_path

app = FastAPI(
    title="Dysruption CVA API",
    description="Consensus Verifier Agent - Multi-Model AI Tribunal for Code Verification",
    version="1.2.0",
    docs_url="/docs" if not PRODUCTION_MODE else None,  # Disable docs in production
    redoc_url="/redoc" if not PRODUCTION_MODE else None,
)

# CORS configuration - restricted in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if PRODUCTION_MODE else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Restrict to needed methods
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
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
        self.cancel_requested: bool = False
        # New fields for prompt synthesis
        self.spec_summary: Optional[str] = None
        self.file_tree: Optional[Dict[str, str]] = None
        self.prompt_recommendation: Optional[Dict[str, Any]] = None

        # Per-run artifact paths (set by pipeline)
        self.artifacts_dir: Optional[str] = None
        self.report_path: Optional[str] = None
        self.verdict_path: Optional[str] = None
        self.criteria_path: Optional[str] = None

    def request_cancel(self) -> None:
        self.cancel_requested = True


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
        # Log handshake details
        logger.info(f"🧨 [WS-HANDSHAKE] Attempting accept for run_id={run_id}")
        logger.info(f"🧨 [WS-HANDSHAKE] Client: {websocket.client}")
        logger.info(f"🧨 [WS-HANDSHAKE] Headers: {dict(websocket.headers)}")
        
        await websocket.accept()
        logger.info(f"🧨 [WS-HANDSHAKE] ACCEPTED SUCCESSFULLY for {run_id}")
        
        if run_id not in self.active_connections:
            self.active_connections[run_id] = set()
        self.active_connections[run_id].add(websocket)
        logger.info(f"WebSocket connected for run {run_id} (total: {len(self.active_connections[run_id])} connections)")

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

    # Create per-run artifacts dir + derived config with per-run output paths.
    artifacts_dir, effective_config_path = _create_run_artifacts(run_id, config.config_path)
    run_state.artifacts_dir = str(artifacts_dir)
    run_state.report_path = str(artifacts_dir / "REPORT.md")
    run_state.verdict_path = str(artifacts_dir / "verdict.json")
    run_state.criteria_path = str(artifacts_dir / "criteria.json")

    # Use derived config for all modules (parser/tribunal/watcher) so outputs are isolated per-run.
    config.config_path = str(effective_config_path)

    class _RunCancelled(Exception):
        pass

    async def _cancel_if_requested(context: str) -> None:
        if not run_state.cancel_requested:
            return

        run_state.state.status = PipelineStatus.ERROR
        run_state.state.current_phase = "cancelled"
        run_state.state.message = "Cancelled by user"
        run_state.state.error = "Cancelled by user"
        run_state.error = "Cancelled by user"

        # Persist run state for history views.
        save_run_history(run_state)

        await ws_manager.broadcast(
            run_id,
            WebSocketMessage(
                type="error",
                run_id=run_id,
                data={"error": "Cancelled by user", "cancelled": True, "context": context},
            ),
        )
        raise _RunCancelled()

    async def update_progress(
        status: PipelineStatus,
        phase: str,
        progress: float,
        message: str,
    ) -> None:
        """Update run state and broadcast to WebSockets."""
        await _cancel_if_requested(f"update_progress:{phase}")
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
        await _cancel_if_requested("before_scanning")
        await update_progress(
            PipelineStatus.SCANNING, "scanning", 10.0, "Scanning project directory..."
        )
        
        # 🔍 DIAGNOSTIC: Log exactly what we're scanning
        logger.info(f"🔴🔴🔴 [TRACE-3] Pipeline scanning config.target_dir: '{config.target_dir}'")

        watcher = DirectoryWatcher(config.target_dir, config.config_path)
        watcher.setup()
        
        # 🔍 DIAGNOSTIC: Log watcher state after setup (uses target_path, not root_dir)
        logger.info(f"🔴🔴🔴 [TRACE-4] Watcher target_path after setup: '{watcher.target_path}'")
        
        file_tree = watcher.run_once()

        await _cancel_if_requested("after_scanning")
        
        # 🔍 DIAGNOSTIC: Log file tree details
        logger.info(f"🔴🔴🔴 [TRACE-5] FileTree has {len(file_tree.files)} files")
        if file_tree.files:
            first_5_paths = list(file_tree.files.keys())[:5]
            logger.info(f"🔴🔴🔴 [TRACE-5] First 5 file paths: {first_5_paths}")

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
        await _cancel_if_requested("before_parsing")
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

        await _cancel_if_requested("after_parsing")

        total_invariants = sum(len(invariants[cat]) for cat in invariants)
        await update_progress(
            PipelineStatus.PARSING,
            "parsing",
            40.0,
            f"Extracted {total_invariants} invariants across 3 categories",
        )

        # Phase 3: Static Analysis
        await _cancel_if_requested("before_static_analysis")
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

        await _cancel_if_requested("after_static_analysis")

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
            report_path, verdict_path = tribunal.save_outputs(run_state.verdict)
            run_state.report_path = report_path
            run_state.verdict_path = verdict_path
            
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
        await _cancel_if_requested("before_judging")
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

        await _cancel_if_requested("after_judging")

        await update_progress(
            PipelineStatus.JUDGING,
            "judging",
            90.0,
            f"Tribunal complete: {verdict.overall_verdict.value} "
            f"({verdict.passed_criteria}/{verdict.total_criteria} passed)"
            + (" [VETO]" if verdict.veto_triggered else ""),
        )

        # Phase 5: Patching (if failed and patches requested)
        await _cancel_if_requested("before_patching")
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

        # Phase 4: Optional self-healing patch loop (strict opt-in; disabled by default).
        # NOTE: This only runs when patches are present AND CVA_SELF_HEAL_ENABLED=true.
        try:
            sh_cfg = self_heal_config_from_env()
            sh_verify = default_verify_command_from_env()
            if (
                sh_cfg.enabled
                and sh_verify
                and run_state.patches
                and run_state.patches.patches
                and run_state.artifacts_dir
            ):

                def provider(i: int):
                    return run_state.patches if i == 1 else None

                run_self_heal_patch_loop(
                    project_root=Path(config.target_dir),
                    run_id=run_id,
                    artifacts_root=RUN_ARTIFACTS_ROOT,
                    patch_provider=provider,
                    verify_command=sh_verify,
                    config=sh_cfg,
                )
        except SelfHealError as e:
            logger.warning(f"Self-heal patch loop skipped/failed: {e}")
        except Exception as e:
            logger.warning(f"Self-heal patch loop unexpected error: {e}")

        # Save outputs
        report_path, verdict_path = tribunal.save_outputs(verdict)
        run_state.report_path = report_path
        run_state.verdict_path = verdict_path

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

    except _RunCancelled:
        return
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
        "version": "1.2.0",
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
        test_file = UPLOAD_ROOT / ".healthcheck"
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


# =============================================================================
# TRIBUNAL API ENDPOINTS
# =============================================================================


@app.get("/api/constitution", response_model=ConstitutionInfo)
async def get_constitution(project_id: Optional[str] = None, commit_hash: Optional[str] = None) -> ConstitutionInfo:
    """Return active constitution metadata.

    Note: If project_id is omitted, this resolves constitution from the server CWD.
    """
    try:
        project_root = get_project_root(UPLOAD_ROOT, project_id) if project_id else Path(os.getcwd()).resolve()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    _, info = _load_constitution(project_root, commit_hash=commit_hash)
    return info


@app.get("/api/constitution/history", response_model=List[ConstitutionHistoryItem])
async def get_constitution_history(project_id: Optional[str] = None) -> List[ConstitutionHistoryItem]:
    """Return git-linked edit history for the constitution file (best-effort)."""
    try:
        project_root = get_project_root(UPLOAD_ROOT, project_id) if project_id else Path(os.getcwd()).resolve()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    constitution_path = _find_constitution_path(project_root)
    rel = constitution_path.relative_to(project_root).as_posix() if constitution_path.exists() else ".tribunal/constitution.md"
    return _get_git_history_for_path(project_root, rel)


def _ensure_success_spec_size_limit(success_spec: Dict[str, Any]) -> None:
    raw = json.dumps(success_spec, ensure_ascii=False).encode("utf-8")
    if len(raw) > 128 * 1024:
        raise HTTPException(status_code=413, detail="success_spec exceeds 128KB")


@app.post("/api/intent", status_code=202)
async def post_intent(payload: IntentEnvelope, request: Request) -> Dict[str, Any]:
    """Inject per-run intent (Success Spec) into the ephemeral run-state store."""
    _require_tribunal_api_token(request)

    project_id = _sanitize_str(payload.project_id, max_len=128)
    origin = _sanitize_str(request.headers.get("origin", ""), max_len=256)
    if not check_tribunal_rate_limit(project_id, origin):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    success_spec_dict = payload.success_spec.model_dump()
    _ensure_success_spec_size_limit(success_spec_dict)

    key = str(payload.run_id)
    await _intent_store.set(key, payload, ttl_seconds=TRIBUNAL_INTENT_TTL_SECONDS)

    # Initialize run status store for this run_id
    await _tribunal_run_store.set(
        key,
        {"status": "intent_received", "project_id": project_id, "created_at": datetime.now().isoformat()},
        ttl_seconds=max(TRIBUNAL_INTENT_TTL_SECONDS, 600),
    )

    return {"run_id": key, "status": "accepted", "ttl_seconds": TRIBUNAL_INTENT_TTL_SECONDS}


@app.get("/api/intent/{run_id}")
async def get_intent(run_id: str, request: Request) -> Dict[str, Any]:
    """Retrieve stored intent for a run_id."""
    _require_api_token(request)
    stored = await _intent_store.get(run_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Intent not found or expired")
    # Return dict to keep response stable even if model changes.
    return stored.model_dump()


async def _emit_initiator_webhook(
    *,
    callback_url: str,
    callback_bearer_token: Optional[str],
    payload: Dict[str, Any],
) -> None:
    try:
        import httpx

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if callback_bearer_token:
            headers["Authorization"] = f"Bearer {callback_bearer_token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(callback_url, json=payload, headers=headers)
    except Exception as e:
        logger.warning(f"Initiator webhook failed: {e}")


def _verdicts_url_for_run(run_id: str) -> str:
    base = os.getenv("CVA_PUBLIC_BASE_URL", "").rstrip("/")
    path = f"/api/verdicts/{run_id}"
    return f"{base}{path}" if base else path


async def _run_tribunal_scan(run_id: str, mode: str) -> None:
    """Background scan job: diff/full detection -> import resolution -> token-budget context -> judge -> persist -> webhook."""

    def _est_tokens(text: str) -> int:
        # Deterministic heuristic: ~4 chars per token.
        return max(0, (len(text or "") + 3) // 4)

    scan_started_at = datetime.now().isoformat()
    t0 = time.time()

    stored_intent = await _intent_store.get(run_id)
    if not stored_intent:
        await _tribunal_run_store.set(run_id, {"status": "failed", "error_details": "Intent missing/expired"}, ttl_seconds=3600)
        return

    intent: IntentEnvelope = stored_intent
    project_id = _sanitize_str(intent.project_id, max_len=128)

    await _tribunal_run_store.set(run_id, {"status": "running", "mode": mode, "project_id": project_id}, ttl_seconds=3600)

    try:
        project_root = get_project_root(UPLOAD_ROOT, project_id)
        if not project_root.exists() or not project_root.is_dir():
            raise HTTPException(status_code=404, detail="Project root not found")

        constitution_text, constitution_info = _load_constitution(project_root, commit_hash=intent.commit_hash)

        diff_start = time.time()
        diff_result = detect_changed_files(
            project_root,
            mode,
            mtime_window_seconds=TRIBUNAL_MTIME_WINDOW_SECONDS,
        )
        diff_ms = int((time.time() - diff_start) * 1000)

        # Resolve imports (best-effort)
        skipped_imports: List[str] = []
        import_files: List[str] = []
        imp_start = time.time()
        try:
            imp_res = resolve_imports(project_root, diff_result.changed_files, depth=2)
            import_files = imp_res.resolved_files
            skipped_imports = imp_res.skipped_imports
        except Exception as e:
            skipped_imports = [f"import_resolution_error:{e}"]
            import_files = []
        import_ms = int((time.time() - imp_start) * 1000)

        # Deterministic lane should not be budget-limited: read ALL changed+import files (bounded per file)
        all_file_texts: Dict[str, str] = {}
        for rel in (diff_result.changed_files + import_files):
            try:
                abs_path = (project_root / rel).resolve()
                if not abs_path.exists() or not abs_path.is_file():
                    continue
                raw = abs_path.read_bytes()
                if len(raw) > 512 * 1024:
                    raw = raw[:512 * 1024]
                all_file_texts[rel] = raw.decode("utf-8", errors="replace")
            except Exception:
                continue

        # Coverage-aware, risk-prioritized packing for model-assisted checks.
        # Use a simple SQLite coverage log to boost previously-uncovered changed files.
        coverage_db_path = (RUN_ARTIFACTS_ROOT / "coverage.db").resolve()
        prior = get_coverage_map(coverage_db_path, project_id)
        uncovered_changed = [p for p in diff_result.changed_files if p not in prior]

        ctx_start = time.time()
        ctx = build_llm_context(
            project_root,
            changed_files=diff_result.changed_files,
            import_files=import_files,
            forced_files=uncovered_changed,
            constitution_text=constitution_text,
            token_budget=TRIBUNAL_TOKEN_BUDGET,
        )
        ctx_ms = int((time.time() - ctx_start) * 1000)

        # LLM context uses the budgeted snippets directly (supports header/slice coverage).
        llm_file_texts: Dict[str, str] = {}
        # Keep order stable: constitution, manifest, then files as added.
        for key in ["__constitution__", "__manifest__"]:
            if key in ctx.file_snippets:
                llm_file_texts[key] = ctx.file_snippets[key]
        for rel in (ctx.included_changed_files + ctx.included_import_files):
            if rel in ctx.file_snippets:
                llm_file_texts[rel] = ctx.file_snippets[rel]

        # Phase 3: route Lane 2 (local/open) → Lane 3 (frontier) if needed.
        # This selects the model string used for the LLM checks.
        router_decision = None
        llm_model_to_use = TRIBUNAL_INTENT_LLM_MODEL
        try:
            router_cfg = load_router_config_from_env(legacy_model=TRIBUNAL_INTENT_LLM_MODEL)
            allow_escalation = os.getenv("CVA_ALLOW_LANE3_ESCALATION", "true").lower() == "true"
            router_decision = await route_llm(
                request=RouterRequest(lane="lane2", token_budget=TRIBUNAL_TOKEN_BUDGET, allow_escalation=allow_escalation),
                lane2_candidates=router_cfg.get("lane2", []),
                lane3_candidates=router_cfg.get("lane3", []),
            )
            llm_model_to_use = router_decision.model
        except RouterError as e:
            raise RuntimeError(f"RouterError: {e}")

        # Judge
        try:
            output = await judge_engine(
                file_texts=llm_file_texts,
                file_texts_for_deterministic=all_file_texts,
                constitution_text=constitution_text,
                skipped_imports=skipped_imports,
                token_count=ctx.token_count,
                token_budget_partial=ctx.partial,
                success_spec=intent.success_spec.model_dump(),
                llm_model=llm_model_to_use,
                llm_timeout_seconds=TRIBUNAL_LLM_TIMEOUT_SECONDS,
                llm_enabled=True,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("LLM timeout")

        # Persist verdicts
        run_dir = (RUN_ARTIFACTS_ROOT / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        verdicts_path = run_dir / "tribunal_verdicts.json"
        # Update coverage DB for files included in model-assisted checks.
        try:
            upsert_coverage(
                coverage_db_path,
                project_id=project_id,
                run_id=run_id,
                rel_paths=[p for p in (ctx.included_changed_files + ctx.included_import_files) if p and not p.startswith("__")],
                coverage_kind="mixed",
            )
        except Exception:
            pass

        # Phase 0 telemetry (no behavior change): persist structured rollups + timing.
        llm_prompt_text = "\n".join([f"# FILE: {p}\n{t}" for p, t in llm_file_texts.items()])
        llm_input_tokens_est = _est_tokens(llm_prompt_text)
        stable_text = "\n".join(
            [
                f"# FILE: {k}\n{llm_file_texts.get(k, '')}"
                for k in ["__constitution__", "__manifest__"]
                if k in llm_file_texts
            ]
        )
        stable_tokens_est = _est_tokens(stable_text)
        variable_tokens_est = max(0, llm_input_tokens_est - stable_tokens_est)

        # Coverage rollups
        header_covered_count = sum(1 for k, v in ctx.coverage_kinds.items() if not str(k).startswith("__") and v == "header")
        full_text_covered_count = sum(1 for k, v in ctx.coverage_kinds.items() if not str(k).startswith("__") and v == "full")
        slice_covered_count = sum(1 for k, v in ctx.coverage_kinds.items() if not str(k).startswith("__") and v == "slice")
        included_files_count = len([k for k in llm_file_texts.keys() if not str(k).startswith("__")])

        candidate_unique = sorted(set((diff_result.changed_files or []) + (import_files or [])))
        unknown_files = [p for p in candidate_unique if p and (p not in ctx.coverage_kinds) and (p not in ctx.truncated_files)]

        run_final_at = datetime.now().isoformat()
        total_ms = int((time.time() - t0) * 1000)
        ttff_ms = int(output.timings.get("ttff_ms", 0) or 0)

        telemetry = RunTelemetry(
            run_id=run_id,
            project_id=project_id,
            mode=mode,
            coverage={
                "included_files_count": included_files_count,
                "header_covered_count": int(header_covered_count),
                "full_text_covered_count": int(full_text_covered_count),
                "slice_covered_count": int(slice_covered_count),
                "truncated_files": [p for p in (ctx.truncated_files or []) if not str(p).startswith("__")],
                "unknown_files": unknown_files,
                "changed_files_total": int(ctx.changed_files_total),
                "changed_files_fully_covered_count": int(ctx.changed_files_fully_covered_count),
                "changed_files_header_covered_count": int(ctx.changed_files_header_covered_count),
                "changed_files_unknown_count": int(ctx.changed_files_unknown_count),
                "fully_covered_percent_of_changed": float(ctx.fully_covered_percent_of_changed),
                "forced_files_count": int(len(uncovered_changed or [])),
                "skip_reasons": ctx.skip_reasons or {},
            },
            cost={
                "lane1_deterministic_tokens": 0,
                "lane2_llm_input_tokens_est": int(llm_input_tokens_est),
                "lane2_llm_stable_prefix_tokens_est": int(stable_tokens_est),
                "lane2_llm_variable_suffix_tokens_est": int(variable_tokens_est),
            },
            cache={
                "cached_vs_uncached": "unknown",
                "reason": "stable_prefix_split_no_provider_signal",
                "intent": "stable_prefix_split",
                "provider_cache_signal": None,
            },
            latency={
                "run_started_at": scan_started_at,
                "run_final_at": run_final_at,
                "ttff_ms": int(ttff_ms),
                "time_to_final_ms": int(total_ms),
                "diff_detection_ms": int(diff_ms),
                "import_resolution_ms": int(import_ms),
                "context_build_ms": int(ctx_ms),
                "llm_latency_ms": output.metrics.llm_latency_ms,
                "lane2_llm_batch_size": int(output.llm_batch.get("batch_size", 1) or 1) if getattr(output, "llm_batch", None) else 1,
                "lane2_llm_batch_mode": str(output.llm_batch.get("mode", "single")) if getattr(output, "llm_batch", None) else "single",
                "lane2_llm_per_item_latency_ms": list(output.llm_batch.get("per_item_latency_ms", [])) if getattr(output, "llm_batch", None) else None,
            },
            skipped={
                "skipped_imports": output.skipped_imports,
            },
            router=(
                {
                    "lane_requested": router_decision.lane_requested,
                    "lane_used": router_decision.lane_used,
                    "provider": router_decision.provider,
                    "model": router_decision.model,
                    "reason": router_decision.reason,
                    "fallback_chain": router_decision.fallback_chain,
                }
                if router_decision
                else None
            ),
        ).model_dump()

        verdict_payload: Dict[str, Any] = {
            "run_id": run_id,
            "project_id": project_id,
            "mode": mode,
            "constitution": constitution_info.model_dump(),
            "diff_detection": {"detection": diff_result.detection, "changed_files": diff_result.changed_files, "time_ms": diff_ms},
            "token_budget": {"budget": TRIBUNAL_TOKEN_BUDGET, "token_count": output.metrics.token_count, "partial": output.partial, "truncated_files": ctx.truncated_files, "included_constitution": ctx.included_constitution},
            "coverage_audit": {
                "forced_uncovered_changed_files": uncovered_changed,
                "llm_included_files": list(llm_file_texts.keys()),
                "coverage_kinds": ctx.coverage_kinds,
                "deterministic_files_scanned": len(all_file_texts),
            },
            "routing": (
                {
                    "lane_requested": router_decision.lane_requested,
                    "lane_used": router_decision.lane_used,
                    "provider": router_decision.provider,
                    "model": router_decision.model,
                    "reason": router_decision.reason,
                    "fallback_chain": router_decision.fallback_chain,
                }
                if router_decision
                else None
            ),
            "telemetry": telemetry,
            "skipped_imports": output.skipped_imports,
            "unevaluated_rules": output.unevaluated_rules,
            "metrics": {
                "scan_time_ms": output.metrics.scan_time_ms,
                "token_count": output.metrics.token_count,
                "llm_latency_ms": output.metrics.llm_latency_ms,
                "violations_count": output.metrics.violations_count,
            },
            "verdicts": output.verdicts,
            "created_at": datetime.now().isoformat(),
        }
        verdicts_path.write_text(json.dumps(verdict_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        verdict_summary = {
            "partial": output.partial,
            "counts": {
                "constitution": len([v for v in output.verdicts if v.get("type") == "constitution"]),
                "intent": len([v for v in output.verdicts if v.get("type") == "intent"]),
                "total": len(output.verdicts),
            },
        }

        await _tribunal_run_store.set(
            run_id,
            {"status": "complete", "verdict_summary": verdict_summary, "verdicts_path": str(verdicts_path)},
            ttl_seconds=3600,
        )

        # Emit webhook/callback (optional)
        if intent.initiator and intent.initiator.callback_url:
            await _emit_initiator_webhook(
                callback_url=intent.initiator.callback_url,
                callback_bearer_token=intent.initiator.callback_bearer_token,
                payload={
                    "run_id": run_id,
                    "status": "complete",
                    "verdict_summary": verdict_summary,
                    "verdicts_url": _verdicts_url_for_run(run_id),
                },
            )

    except Exception as e:
        error_details = _sanitize_str(str(e), max_len=2000)
        await _tribunal_run_store.set(run_id, {"status": "failed", "error_details": error_details, "mode": mode}, ttl_seconds=3600)

        # Best-effort persist a failure artifact with telemetry for Phase 0.
        try:
            run_dir = (RUN_ARTIFACTS_ROOT / run_id).resolve()
            run_dir.mkdir(parents=True, exist_ok=True)
            verdicts_path = run_dir / "tribunal_verdicts.json"

            run_final_at = datetime.now().isoformat()
            total_ms = int((time.time() - t0) * 1000)

            telemetry = RunTelemetry(
                run_id=run_id,
                project_id=str(project_id) if "project_id" in locals() else "",
                mode=mode,
                coverage={
                    "included_files_count": 0,
                    "header_covered_count": 0,
                    "full_text_covered_count": 0,
                    "slice_covered_count": 0,
                    "truncated_files": [],
                    "unknown_files": [],
                    "changed_files_total": 0,
                    "changed_files_fully_covered_count": 0,
                    "changed_files_header_covered_count": 0,
                    "changed_files_unknown_count": 0,
                    "fully_covered_percent_of_changed": 0.0,
                    "forced_files_count": 0,
                    "skip_reasons": {},
                },
                cost={
                    "lane1_deterministic_tokens": 0,
                    "lane2_llm_input_tokens_est": 0,
                    "lane2_llm_stable_prefix_tokens_est": 0,
                    "lane2_llm_variable_suffix_tokens_est": 0,
                },
                cache={
                    "cached_vs_uncached": "unknown",
                    "reason": "stable_prefix_split_no_provider_signal",
                    "intent": "stable_prefix_split",
                    "provider_cache_signal": None,
                },
                latency={
                    "run_started_at": scan_started_at,
                    "run_final_at": run_final_at,
                    "ttff_ms": 0,
                    "time_to_final_ms": int(total_ms),
                    "lane2_llm_batch_size": 0,
                    "lane2_llm_batch_mode": None,
                    "lane2_llm_per_item_latency_ms": None,
                },
                skipped={
                    "skipped_imports": [],
                },
                error=error_details,
            ).model_dump()

            verdicts_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "mode": mode,
                        "status": "failed",
                        "error_details": error_details,
                        "telemetry": telemetry,
                        "created_at": run_final_at,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

        # Best-effort webhook (optional)
        if intent.initiator and intent.initiator.callback_url:
            try:
                await _emit_initiator_webhook(
                    callback_url=intent.initiator.callback_url,
                    callback_bearer_token=intent.initiator.callback_bearer_token,
                    payload={
                        "run_id": run_id,
                        "status": "failed",
                        "verdict_summary": None,
                        "verdicts_url": _verdicts_url_for_run(run_id),
                    },
                )
            except Exception:
                pass


@app.post("/api/trigger_scan", response_model=TriggerScanResponse, status_code=202)
async def trigger_scan(payload: TriggerScanRequest, request: Request) -> TriggerScanResponse:
    _require_tribunal_api_token(request)

    stored_intent = await _intent_store.get(str(payload.run_id))
    if not stored_intent:
        raise HTTPException(status_code=404, detail="Intent not found or expired")

    intent: IntentEnvelope = stored_intent
    project_id = _sanitize_str(intent.project_id, max_len=128)
    origin = _sanitize_str(request.headers.get("origin", ""), max_len=256)
    if not check_tribunal_rate_limit(project_id, origin):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    run_id_str = str(payload.run_id)
    asyncio.create_task(_run_tribunal_scan(run_id_str, payload.mode.value))

    # Initial response is always partial=false, real partial is in the final verdict payload.
    return TriggerScanResponse(
        run_id=payload.run_id,
        status="queued",
        verdicts_url=_verdicts_url_for_run(run_id_str),
        partial=False,
        skipped_imports=[],
        unevaluated_rules=[],
        metrics={"scan_time_ms": 0, "token_count": 0, "llm_latency_ms": None, "violations_count": 0},
    )


@app.get("/api/verdicts/{run_id}")
async def get_verdicts(run_id: str, request: Request) -> Dict[str, Any]:
    _require_api_token(request)
    # Return persisted verdict payload if present
    run_dir = (RUN_ARTIFACTS_ROOT / run_id).resolve()
    verdicts_path = run_dir / "tribunal_verdicts.json"
    if verdicts_path.exists():
        try:
            return json.loads(verdicts_path.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to read verdicts")

    status = await _tribunal_run_store.get(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Verdicts not found")
    return status


@app.post("/api/retry/{run_id}", status_code=202)
async def retry_scan(run_id: str, request: Request) -> Dict[str, Any]:
    _require_tribunal_api_token(request)
    status = await _tribunal_run_store.get(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Run not found")

    if status.get("status") != "failed":
        raise HTTPException(status_code=409, detail="Only failed runs can be retried")

    mode = status.get("mode") or "diff"
    asyncio.create_task(_run_tribunal_scan(run_id, mode))
    return {"run_id": run_id, "status": "queued", "mode": mode}


@app.post("/upload")
async def upload_files(
    request: Request,
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(...),
    upload_id: Optional[str] = Form(None)
) -> Dict[str, Any]:
    """
    Upload files for analysis. Supports batching via upload_id.
    
    Security features:
    - Rate limiting per client IP
    - File size limits
    - Path sanitization
    
    - If upload_id is None: Creates new session.
    - If upload_id is provided: Appends to existing session.
    """
    _require_api_token(request)

    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded. Please wait before making more requests."
        )
    
    # Validate or create upload_id
    if upload_id:
        # Security check: Alphanumeric only to prevent traversal
        if not upload_id.isalnum():
             raise HTTPException(status_code=400, detail="Invalid upload_id")
        # Use existing directory
        temp_dir = UPLOAD_ROOT / upload_id
        if not temp_dir.exists():
             # If it doesn't exist (expired?), create it
             temp_dir.mkdir(parents=True, exist_ok=True)
    else:
        # Create new session
        upload_id = str(uuid.uuid4())[:8]
        temp_dir = UPLOAD_ROOT / upload_id
        temp_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Upload {upload_id}: Processing batch of {len(files)} files")
    
    saved_count = 0
    
    try:
        # Iterate through files and paths (they should match by index)
        total_size = 0
        max_size_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
        
        for i, file in enumerate(files):
            # Get relative path from form data, or fallback to filename
            rel_path = paths[i] if i < len(paths) else file.filename
            
            # Sanitize path to prevent directory traversal
            clean_rel_path = rel_path.lstrip("/").lstrip("\\").replace("..", "")
            
            # Additional path sanitization: remove any remaining path traversal attempts
            clean_rel_path = "/".join(
                part for part in clean_rel_path.replace("\\", "/").split("/")
                if part and part != ".."
            )
            
            # Construct full path
            file_path = temp_dir / clean_rel_path
            
            # Ensure parent directories exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save file using streaming with size limit check
            file_size = 0
            async with aiofiles.open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    file_size += len(chunk)
                    total_size += len(chunk)
                    
                    # Check size limits
                    if total_size > max_size_bytes:
                        raise HTTPException(
                            status_code=413, 
                            detail=f"Upload size exceeds limit of {MAX_UPLOAD_SIZE_MB}MB"
                        )
                    
                    await f.write(chunk)
            
            saved_count += 1
            
        logger.info(f"Upload {upload_id}: Batch complete, saved {saved_count} files ({total_size / 1024 / 1024:.1f}MB)")
        
        return {
            "upload_id": upload_id,
            "path": str(temp_dir.absolute()),
            "count": saved_count,
            "message": f"Successfully uploaded batch of {saved_count} files"
        }
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        # Sanitize error message for production
        error_msg = "Upload failed due to an internal error" if PRODUCTION_MODE else f"Upload failed: {str(e)}"
        raise HTTPException(status_code=500, detail=error_msg)



@app.post("/run", response_model=RunResponse)
async def start_run(
    run_request: RunRequest, 
    request: Request,
    background_tasks: BackgroundTasks
) -> RunResponse:
    """
    Start a new verification run.

    Initiates the CVA pipeline in the background and returns a run_id
    for tracking progress via /status or /ws endpoints.
    """
    _require_api_token(request)

    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded. Please wait before making more requests."
        )
    
    target_dir = run_request.target_dir.strip()
    
    # 🔍 DIAGNOSTIC: Log exactly what the API received
    logger.info(f"🔴🔴🔴 [TRACE-1] /run API received target_dir: '{target_dir}'")
    logger.info(f"🔴🔴🔴 [TRACE-1] Full request: {run_request.model_dump()}")
    
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

    # PRODUCTION LOCKDOWN: only allow scanning uploaded projects.
    if PRODUCTION_MODE:
        if not _is_path_within_root(target_dir, UPLOAD_ROOT):
            raise HTTPException(
                status_code=400,
                detail=(
                    "In production, scanning is restricted to uploaded projects only. "
                    "Upload a project first, then pass the returned temp_uploads path to /run."
                ),
            )

    # =========================================================================
    # START THE RUN
    # =========================================================================
    
    # Generate run ID
    run_id = str(uuid.uuid4())[:8]
    
    # 🔍 DIAGNOSTIC: Verify path exists right before creating config
    logger.info(f"🔴🔴🔴 [TRACE-2] Creating config for run {run_id}")
    logger.info(f"🔴🔴🔴 [TRACE-2] target_dir = '{target_dir}'")
    logger.info(f"🔴🔴🔴 [TRACE-2] os.path.exists = {os.path.exists(target_dir)}")
    logger.info(f"🔴🔴🔴 [TRACE-2] os.path.isdir = {os.path.isdir(target_dir)}")
    
    # List first 10 items in directory for verification
    try:
        items = os.listdir(target_dir)[:10]
        logger.info(f"🔴🔴🔴 [TRACE-2] First 10 items in dir: {items}")
    except Exception as e:
        logger.error(f"🔴🔴🔴 [TRACE-2] Failed to list dir: {e}")

    # Create run config
    config = RunConfig(
        target_dir=target_dir,
        spec_path=run_request.spec_path or "spec.txt",
        spec_content=run_request.spec_content,  # Pass constitution text if provided
        config_path="config.yaml",
        generate_patches=run_request.generate_patches,
        watch_mode=run_request.watch_mode,
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
async def get_status(run_id: str, request: Request) -> StatusResponse:
    """
    Get current status of a verification run.

    Returns the current phase, progress percentage, and any messages.
    """
    _require_api_token(request)
    run_state = get_run(run_id)

    return StatusResponse(run_id=run_id, state=run_state.state)


@app.get("/verdict/{run_id}", response_model=VerdictResponse)
async def get_verdict(run_id: str, request: Request) -> VerdictResponse:
    """
    Get the final verdict of a verification run.

    Only available after the run is complete. Returns the consensus result,
    any generated patches, AND the raw report/diff content for frontend download.
    """
    _require_api_token(request)
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
        
        # Load per-run REPORT.md content if it exists
        try:
            report_path = Path(run_state.report_path) if run_state.report_path else None
            if report_path and report_path.exists():
                report_markdown = report_path.read_text(encoding="utf-8")
                logger.info(f"Loaded per-run REPORT.md: {len(report_markdown)} chars")
        except Exception as e:
            logger.warning(f"Could not load per-run REPORT.md: {e}")
    
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
async def get_fix_prompt(run_id: str, request: Request) -> Dict[str, Any]:
    """
    Generate a synthesized fix prompt for a failed verification run.
    
    Returns a comprehensive, actionable prompt that can be given to an AI
    coding assistant (Claude, GPT-4, Copilot) to fix the identified issues.
    
    Only available after verification is complete and has issues to fix.
    """
    _require_api_token(request)
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
async def cancel_run(run_id: str, request: Request) -> Dict[str, Any]:
    """Cancel a running verification (if possible)."""
    _require_api_token(request)
    run_state = get_run(run_id)

    if run_state.state.status in (PipelineStatus.COMPLETE, PipelineStatus.ERROR):
        return {
            "run_id": run_id,
            "cancelled": False,
            "message": "Run already completed or errored",
        }

    run_state.request_cancel()
    run_state.state.status = PipelineStatus.ERROR
    run_state.state.error = "Cancelled by user"
    run_state.error = "Cancelled by user"

    # Best-effort notify connected clients immediately
    await ws_manager.broadcast(
        run_id,
        WebSocketMessage(
            type="error",
            run_id=run_id,
            data={"error": "Cancelled by user", "cancelled": True},
        ),
    )

    return {
        "run_id": run_id,
        "cancelled": True,
        "message": "Run cancellation requested",
    }


@app.get("/runs")
async def list_runs(request: Request) -> Dict[str, Any]:
    """List all verification runs."""
    _require_api_token(request)
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
    logger.info(f"🔌 [WS] Connection attempt for run_id: {run_id}")

    # In production, require an API token in the query string.
    # Note: browser WebSocket APIs cannot set custom headers reliably.
    if PRODUCTION_MODE:
        token = websocket.query_params.get("token", "")
        if not token or token != (API_TOKEN or ""):
            try:
                await websocket.close(code=1008)
            except Exception:
                pass
            return
    
    try:
        await ws_manager.connect(websocket, run_id)
        logger.info(f"✅ [WS] Connection ACCEPTED for run_id: {run_id}")
    except Exception as e:
        logger.error(f"❌ [WS] Connection FAILED for {run_id}: {e}")
        import traceback
        traceback.print_exc()
        return

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
            logger.info(f"📤 [WS] Sent initial state for {run_id}")
        else:
            # Send acknowledgment even if no run exists yet
            await websocket.send_text(json.dumps({
                "type": "connected",
                "run_id": run_id,
                "message": "WebSocket connected, waiting for run to start"
            }))
            logger.info(f"📤 [WS] Sent connection ack for {run_id} (no run exists yet)")

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
                    logger.warning(f"🔌 [WS] Keepalive failed for {run_id}, closing")
                    break

    except WebSocketDisconnect:
        logger.info(f"🔌 [WS] Client disconnected: {run_id}")
        ws_manager.disconnect(websocket, run_id)
    except Exception as e:
        logger.error(f"❌ [WS] Error for {run_id}: {e}")
        import traceback
        traceback.print_exc()
        ws_manager.disconnect(websocket, run_id)


# =============================================================================
# STARTUP/SHUTDOWN EVENTS
# =============================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize on startup."""
    logger.info("CVA API v1.2 starting up...")
    logger.info("Endpoints: /run, /status/{run_id}, /verdict/{run_id}, /ws/{run_id}")

    # Ensure runtime directories exist (important on Railway + ephemeral filesystems).
    try:
        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        RUN_ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create runtime dirs: {e}")

    logger.info(
        "Startup config: production=%s port=%s upload_root=%s run_artifacts_root=%s",
        PRODUCTION_MODE,
        os.getenv("PORT", ""),
        str(UPLOAD_ROOT),
        str(RUN_ARTIFACTS_ROOT),
    )


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
    import os
    import uvicorn

    uvicorn.run(
        "modules.api:app",
        # Safer default for local runs; production/Railway binds via start.sh.
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8001")),
        reload=True,
        log_level="info",
    )
