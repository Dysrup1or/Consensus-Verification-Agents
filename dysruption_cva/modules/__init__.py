# Dysruption CVA Modules
# Version: 1.1 - FastAPI Backend with Veto Protocol

# Core modules
from .watcher import DirectoryWatcher, run_watcher
from .watcher_v2 import (
    DirectoryWatcher as DirectoryWatcherV2,
    SmartDebounceHandler,
    run_watcher as run_watcher_v2,
)
from .parser import ConstitutionParser, run_extraction
from .tribunal import Tribunal, run_adjudication, Verdict

# Pydantic schemas
from .schemas import (
    FileNode,
    FileTree,
    FileMetadata,
    Invariant,
    InvariantCategory,
    InvariantSeverity,
    InvariantSet,
    JudgeVerdict,
    JudgeRole,
    VerdictStatus,
    ConsensusResult,
    Patch,
    PatchSet,
    PipelineStatus,
    PipelineState,
    RunConfig,
    RunRequest,
    RunResponse,
    StatusResponse,
    VerdictResponse,
    WebSocketMessage,
)

# Sandbox runner (stub)
from .sandbox_runner import SandboxRunner, ExecutionResult, ExecutionStatus

# FastAPI app (import separately to avoid circular imports)
# from .api import app

__all__ = [
    # Watcher
    "DirectoryWatcher",
    "run_watcher",
    "DirectoryWatcherV2",
    "SmartDebounceHandler",
    "run_watcher_v2",
    # Parser
    "ConstitutionParser",
    "run_extraction",
    # Tribunal
    "Tribunal",
    "run_adjudication",
    "Verdict",
    # Schemas
    "FileNode",
    "FileTree",
    "FileMetadata",
    "Invariant",
    "InvariantCategory",
    "InvariantSeverity",
    "InvariantSet",
    "JudgeVerdict",
    "JudgeRole",
    "VerdictStatus",
    "ConsensusResult",
    "Patch",
    "PatchSet",
    "PipelineStatus",
    "PipelineState",
    "RunConfig",
    "RunRequest",
    "RunResponse",
    "StatusResponse",
    "VerdictResponse",
    "WebSocketMessage",
    # Sandbox
    "SandboxRunner",
    "ExecutionResult",
    "ExecutionStatus",
]
