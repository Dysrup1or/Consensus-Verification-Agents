"""File and repository utilities for the Tribunal API.

Implements:
- diff/full file selection
- AST-based import resolution (depth-limited)
- LLM context assembly with token-budget truncation

This module is intentionally deterministic (no LLM calls).
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from loguru import logger

try:
    from .ts_imports import extract_imports
    from .ts_imports import extract_js_ts_header
except Exception:  # pragma: no cover
    # Tests import via `from modules.file_manager ...` (top-level), so relative import may fail.
    from modules.ts_imports import extract_imports  # type: ignore
    from modules.ts_imports import extract_js_ts_header  # type: ignore

try:
    from .risk import collect_git_signals
except Exception:  # pragma: no cover
    from modules.risk import collect_git_signals  # type: ignore

try:
    from .dependency_resolver import ResolverConfig
    from .dependency_resolver import resolve_dependencies
except Exception:  # pragma: no cover
    from modules.dependency_resolver import ResolverConfig  # type: ignore
    from modules.dependency_resolver import resolve_dependencies  # type: ignore

# Optional RAG integration for semantic file scoring
_RAG_AVAILABLE = False
try:
    from .rag_integration import sync_enhance_risk_scores, RAGConfig
    _RAG_AVAILABLE = True
except ImportError:
    try:
        from modules.rag_integration import sync_enhance_risk_scores, RAGConfig  # type: ignore
        _RAG_AVAILABLE = True
    except ImportError:
        pass


_MAX_FILE_BYTES_DEFAULT = 512 * 1024  # 512KB safety cap for context building


@dataclass(frozen=True)
class DiffResult:
    mode: str  # "diff" | "full"
    changed_files: List[str]  # relative paths
    detection: str  # "git" | "mtime" | "full"


@dataclass(frozen=True)
class ImportResolutionResult:
    resolved_files: List[str]  # relative paths
    skipped_imports: List[str]  # import strings we could not resolve


@dataclass(frozen=True)
class ContextBuildResult:
    context: str
    token_count: int
    partial: bool
    truncated_files: List[str]
    included_changed_files: List[str]
    included_import_files: List[str]
    included_constitution: bool
    # New: snippets actually included for LLM context (full/header/slice).
    # Keys are pseudo-paths (real file rel paths, plus optional "__constitution__" and "__manifest__").
    file_snippets: Dict[str, str]
    # New: per-file coverage kind for auditability.
    coverage_kinds: Dict[str, str]
    # Phase 0: explicit coverage rollups (do not infer from maps downstream).
    total_candidate_files: int
    changed_files_total: int
    changed_files_fully_covered_count: int
    changed_files_header_covered_count: int
    changed_files_unknown_count: int
    fully_covered_percent_of_changed: float
    # Phase 0: explicit skip/truncation reasons for unevaluated or partially-evaluated files.
    skip_reasons: Dict[str, str]


@dataclass(frozen=True)
class CoveragePlanItem:
    rel_path: str
    kind: str  # changed|import
    risk_score: int
    risk_reasons: List[str]
    planned_tier: str  # header|full|slice
    planned_reason: str


@dataclass(frozen=True)
class CoveragePlan:
    items: List[CoveragePlanItem]
    manifest_items: List[FileManifestItem]
    forced_changed: List[str]


@dataclass(frozen=True)
class FileManifestItem:
    rel_path: str
    bytes: int
    est_tokens: int
    kind: str  # changed|import
    ext: str
    risk_score: int
    risk_reasons: List[str]


def _safe_relative_to(path: Path, root: Path) -> Optional[str]:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except Exception:
        return None


def get_project_root(upload_root: Path, project_id: str) -> Path:
    # Project IDs are treated as directory names; prevent path traversal.
    if not project_id or re.search(r"[\\/]|\.\.|^\s+$", project_id):
        raise ValueError("Invalid project_id")
    root = upload_root.resolve()
    candidate = (root / project_id).resolve()

    # Defend against symlink-based escapes (e.g., UPLOAD_ROOT/<id> -> /etc).
    try:
        candidate.relative_to(root)
    except Exception:
        raise ValueError("Invalid project_id")

    return candidate


def is_git_repo(project_root: Path) -> bool:
    return (project_root / ".git").exists() and (project_root / ".git").is_dir()


def detect_changed_files(
    project_root: Path,
    mode: str,
    *,
    mtime_window_seconds: int,
    exclude_dirs: Sequence[str] = (".git", "__pycache__", "node_modules", ".venv"),
) -> DiffResult:
    if mode not in {"diff", "full"}:
        raise ValueError("mode must be 'diff' or 'full'")

    if mode == "full":
        files = list(iter_project_files(project_root, exclude_dirs=exclude_dirs))
        return DiffResult(mode=mode, changed_files=files, detection="full")

    if is_git_repo(project_root):
        try:
            from git import Repo  # GitPython

            repo = Repo(str(project_root))
            changed: Set[str] = set()

            # Modified in working tree
            for diff in repo.index.diff(None):
                if diff.a_path:
                    changed.add(diff.a_path)

            # Untracked
            for p in repo.untracked_files:
                changed.add(p)

            # Staged vs HEAD (if HEAD exists)
            try:
                for diff in repo.index.diff("HEAD"):
                    if diff.a_path:
                        changed.add(diff.a_path)
            except Exception:
                pass

            changed_files = sorted({p.replace("\\", "/") for p in changed})
            return DiffResult(mode=mode, changed_files=changed_files, detection="git")
        except Exception as e:
            logger.warning(f"Git diff detection failed; falling back to mtime: {e}")

    changed_files = detect_mtime_changed_files(
        project_root,
        window_seconds=mtime_window_seconds,
        exclude_dirs=exclude_dirs,
    )
    return DiffResult(mode=mode, changed_files=changed_files, detection="mtime")


def iter_project_files(project_root: Path, *, exclude_dirs: Sequence[str]) -> Iterable[str]:
    root = project_root.resolve()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        rel = _safe_relative_to(path, root)
        if not rel:
            continue
        parts = rel.split("/")
        if any(part in exclude_dirs for part in parts):
            continue
        yield rel


def detect_mtime_changed_files(
    project_root: Path,
    *,
    window_seconds: int,
    exclude_dirs: Sequence[str],
) -> List[str]:
    root = project_root.resolve()
    now = time.time()
    changed: List[str] = []
    for rel in iter_project_files(root, exclude_dirs=exclude_dirs):
        abs_path = (root / rel).resolve()
        try:
            if now - abs_path.stat().st_mtime <= window_seconds:
                changed.append(rel)
        except Exception:
            continue
    return sorted(changed)


def _module_to_candidate_paths(module: str) -> List[str]:
    # mypkg.sub -> [mypkg/sub.py, mypkg/sub/__init__.py]
    parts = module.split(".")
    base = "/".join(parts)
    return [f"{base}.py", f"{base}/__init__.py"]


_JS_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _strip_jsonc(text: str) -> str:
    # Best-effort JSONC -> JSON; enough for common tsconfig/jsconfig files.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.MULTILINE)
    return text


@lru_cache(maxsize=16)
def _load_tsconfig_compiler_options(root: Path) -> Tuple[Optional[str], Dict[str, List[str]]]:
    """Return (baseUrl, paths) from tsconfig/jsconfig at repo root (best-effort)."""

    for name in ("tsconfig.json", "jsconfig.json"):
        path = (root / name).resolve()
        try:
            if not path.exists() or not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(_strip_jsonc(raw) or "{}")
            compiler_options = data.get("compilerOptions") or {}
            base_url = compiler_options.get("baseUrl")
            paths = compiler_options.get("paths") or {}

            if not isinstance(paths, dict):
                paths = {}

            norm_paths: Dict[str, List[str]] = {}
            for k, v in paths.items():
                if not isinstance(v, list):
                    continue
                norm_paths[str(k)] = [str(x) for x in v if isinstance(x, str)]

            return (str(base_url) if isinstance(base_url, str) else None, norm_paths)
        except Exception:
            continue

    return (None, {})


def _tsconfig_alias_candidates(root: Path, spec: str) -> List[str]:
    base_url, paths = _load_tsconfig_compiler_options(root)
    out: List[str] = []

    base_dir = root
    if base_url:
        base_dir = (root / base_url).resolve()

    def _add_target(target_pat: str, star: str) -> None:
        candidate = target_pat.replace("*", star) if "*" in target_pat else target_pat
        abs_path = (base_dir / candidate).resolve()
        rel = _safe_relative_to(abs_path, root)
        if rel:
            out.append(rel)

    # `paths` mappings
    for pat, targets in paths.items():
        if not pat:
            continue
        if "*" in pat:
            if pat.count("*") != 1:
                continue
            prefix, suffix = pat.split("*", 1)
            if not spec.startswith(prefix):
                continue
            if suffix and not spec.endswith(suffix):
                continue
            star = spec[len(prefix) : (len(spec) - len(suffix)) if suffix else None]
            for t in targets:
                _add_target(t, star)
        else:
            if spec != pat:
                continue
            for t in targets:
                _add_target(t, "")

    # `baseUrl` resolution (for bare specifiers)
    if base_url and spec and not spec.startswith("./") and not spec.startswith("../") and not spec.startswith("/"):
        abs_path = (base_dir / spec).resolve()
        rel = _safe_relative_to(abs_path, root)
        if rel:
            out.append(rel)

    # De-dupe while preserving order.
    seen: Set[str] = set()
    uniq: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def _resolve_module_to_rel(root: Path, module: str, base_rel: str) -> Optional[str]:
    """Resolve a parsed import specifier/module string to a repo-relative file path.

    - Python: supports absolute module paths and relative dotted imports.
    - JS/TS: supports relative specifiers (./../) and repo-root absolute (/foo).
    """

    module = (module or "").strip()
    if not module:
        return None

    base_rel_l = base_rel.lower()

    # JS/TS module specifiers
    if base_rel_l.endswith(_JS_TS_EXTS):
        spec = module

        candidate_bases: List[str] = []

        if spec.startswith("./") or spec.startswith("../") or spec.startswith("/"):
            base_dir = Path(base_rel).parent
            if spec.startswith("/"):
                candidate = spec.lstrip("/")
                base_dir = Path("")
            else:
                candidate = (base_dir / spec).as_posix()
            candidate_bases.append(Path(candidate).as_posix())
        else:
            # Phase 2: tsconfig/jsconfig baseUrl + paths mapping for repo-local aliases.
            candidate_bases.extend(_tsconfig_alias_candidates(root, spec))

        for base in candidate_bases:
            cand_path = Path(base)
            candidates: List[str] = []

            if cand_path.suffix.lower() in _JS_TS_EXTS:
                candidates.append(cand_path.as_posix())
            else:
                for ext in _JS_TS_EXTS:
                    candidates.append((cand_path.with_suffix(ext)).as_posix())
                for ext in _JS_TS_EXTS:
                    candidates.append((cand_path / f"index{ext}").as_posix())

            for cand in candidates:
                path = (root / cand).resolve()
                rel = _safe_relative_to(path, root)
                if rel and path.exists() and path.is_file():
                    return rel

        return None

    # Python module strings
    dot_prefix = len(module) - len(module.lstrip("."))
    mod_name = module.lstrip(".")

    if dot_prefix:
        base_dir = Path(base_rel).parent
        for _ in range(dot_prefix - 1):
            base_dir = base_dir.parent
        if mod_name:
            candidate_base = (base_dir / mod_name.replace(".", "/")).as_posix()
            candidates = [f"{candidate_base}.py", f"{candidate_base}/__init__.py"]
        else:
            candidates = [base_dir.as_posix() + "/__init__.py"]
    else:
        candidates = _module_to_candidate_paths(mod_name)

    for cand in candidates:
        path = (root / cand).resolve()
        rel = _safe_relative_to(path, root)
        if rel and path.exists() and path.is_file():
            return rel

    return None


def _parse_imports_from_source(source: str) -> Set[str]:
    imports: Set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Handle relative imports by ignoring leading dots here; resolver will adjust.
                prefix = "." * node.level
                imports.add(prefix + node.module)
                # Also include explicit imported names as potential submodules.
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        imports.add(prefix + node.module + "." + alias.name)
            elif node.level:
                imports.add("." * node.level)
    return imports


def _python_ast_header(source: str, *, max_lines: int = 200) -> str:
    lines: List[str] = []
    lines.append("# invariant:header python_ast=true")
    try:
        tree = ast.parse(source or "")
    except Exception:
        return ("\n".join(lines) + "\n").strip() + "\n"

    imports: Set[str] = set()
    top_level: List[str] = []

    for node in getattr(tree, "body", []) or []:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(("." * getattr(node, "level", 0)) + node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level.append(f"def {node.name}(...)")
        elif isinstance(node, ast.ClassDef):
            top_level.append(f"class {node.name}")

    if imports:
        lines.append("# imports")
        for m in sorted(imports)[:120]:
            lines.append(f"import: {m}")

    if top_level:
        lines.append("# top_level")
        for s in top_level[:160]:
            lines.append(s)

    return "\n".join(lines[:max_lines]).strip() + "\n"


def _parse_imports_polyglot(rel_path: str, source: str) -> Set[str]:
    """Best-effort polyglot import extraction.

    For Python we keep AST parsing (more accurate for relative imports).
    For JS/TS we use Tree-sitter if available, else regex fallback.
    """

    if rel_path.lower().endswith(".py"):
        return _parse_imports_from_source(source)

    res = extract_imports(rel_path, source)
    out: Set[str] = set()
    for imp in res.imports:
        out.add(imp)
    return out


def resolve_imports(
    project_root: Path,
    changed_files: Sequence[str],
    *,
    depth: int = 2,
    max_files: int = 200,
) -> ImportResolutionResult:
    res = resolve_dependencies(
        project_root,
        changed_files,
        depth=depth,
        max_files=max_files,
        config=ResolverConfig(max_file_bytes=_MAX_FILE_BYTES_DEFAULT),
    )
    return ImportResolutionResult(resolved_files=res.resolved_files, skipped_imports=res.skipped_imports)


def estimate_tokens(text: str) -> int:
    # Deterministic heuristic (rough): ~4 chars/token average.
    return max(1, (len(text) + 3) // 4)


def _read_text_file(root: Path, rel: str, *, max_bytes: int) -> str:
    path = (root / rel).resolve()
    try:
        data = path.read_bytes()
    except Exception:
        return ""

    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _infer_file_role(rel: str) -> str:
    rel_l = (rel or "").lower()
    name = Path(rel_l).name

    if any(x in rel_l for x in ["/.github/", "dockerfile", "docker-compose", "kubernetes", "terraform", "helm", "pulumi"]):
        return "infra"
    if any(x in name for x in ["package.json", "pnpm-lock", "yarn.lock", "package-lock", "requirements", "pyproject", "tsconfig", "next.config"]):
        return "config"
    if any(x in rel_l for x in ["auth", "oauth", "jwt", "session", "middleware", "csrf", "sso"]):
        return "auth"
    if any(x in rel_l for x in ["migrations", "schema", "prisma", "supabase", "database", "db/"]):
        return "db"
    if any(x in rel_l for x in ["test", "__tests__", "spec", "cypress", "playwright"]):
        return "tests"
    if any(x in rel_l for x in ["docs", "readme", "changelog"]):
        return "docs"
    if any(x in rel_l for x in ["app/", "pages/", "components/", "ui/"]):
        return "ui"
    if any(x in rel_l for x in ["api/", "server", "routes", "controllers"]):
        return "server"
    return "code"


def _python_symbol_slices(source: str, *, max_slices: int = 4, max_total_lines: int = 220) -> List[str]:
    """Extract function/class-level slices for Python using AST line ranges."""

    if not source:
        return []

    try:
        tree = ast.parse(source)
    except Exception:
        return []

    lines = (source or "").splitlines()

    chunks: List[Tuple[int, int, str]] = []
    for node in getattr(tree, "body", []) or []:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = int(getattr(node, "lineno", 1) or 1)
            end = int(getattr(node, "end_lineno", start) or start)
            name = getattr(node, "name", "") or ""
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            chunks.append((start, end, f"{kind} {name}".strip()))

    # Prefer earlier top-level symbols.
    chunks.sort(key=lambda t: (t[0], t[1]))

    out: List[str] = []
    used_lines = 0
    for start, end, label in chunks[: max_slices * 2]:
        if len(out) >= max_slices:
            break
        start_i = max(1, start)
        end_i = max(start_i, end)
        # Cap per-slice size to keep slices cheap.
        end_i = min(end_i, start_i + 120)
        chunk_lines = lines[start_i - 1 : end_i]
        if not chunk_lines:
            continue
        if used_lines + len(chunk_lines) > max_total_lines:
            break
        used_lines += len(chunk_lines)
        out.append(f"# slice: {label} (lines {start_i}-{end_i})\n" + "\n".join(chunk_lines))

    return out


def build_llm_context(
    project_root: Path,
    *,
    changed_files: Sequence[str],
    import_files: Sequence[str],
    forced_files: Sequence[str] = (),
    constitution_text: str,
    token_budget: int,
    max_file_bytes: int = _MAX_FILE_BYTES_DEFAULT,
    spec_text: Optional[str] = None,
    enable_semantic_boost: bool = True,
) -> ContextBuildResult:
    plan = plan_context(
        project_root,
        changed_files=changed_files,
        import_files=import_files,
        forced_files=forced_files,
        constitution_text=constitution_text,
        token_budget=token_budget,
        max_file_bytes=max_file_bytes,
        spec_text=spec_text,
        enable_semantic_boost=enable_semantic_boost,
    )
    return render_context_plan(
        project_root,
        plan=plan,
        constitution_text=constitution_text,
        token_budget=token_budget,
        max_file_bytes=max_file_bytes,
    )


def plan_context(
    project_root: Path,
    *,
    changed_files: Sequence[str],
    import_files: Sequence[str],
    forced_files: Sequence[str] = (),
    constitution_text: str,
    token_budget: int,
    max_file_bytes: int = _MAX_FILE_BYTES_DEFAULT,
    spec_text: Optional[str] = None,
    enable_semantic_boost: bool = True,
) -> CoveragePlan:
    """Phase 1: deterministic coverage planner with optional semantic boosting.

    Produces a structured plan (manifest + coverage tiers) without reading large
    file contents where avoidable.
    
    Args:
        project_root: Root directory of the project
        changed_files: List of changed file paths
        import_files: List of import file paths
        forced_files: Files to force full coverage
        constitution_text: Constitution/spec text (used for header)
        token_budget: Maximum token budget for context
        max_file_bytes: Maximum file size to process
        spec_text: Optional specification text for semantic file scoring
        enable_semantic_boost: If True, use RAG for semantic file boosting
    """

    root = project_root.resolve()

    forced_set: Set[str] = {p.replace("\\", "/") for p in (forced_files or []) if p}

    # Build candidate set.
    changed_unique = sorted({p.replace("\\", "/") for p in (changed_files or []) if p})
    import_unique_input = sorted({p.replace("\\", "/") for p in (import_files or []) if p})

    # Phase 2: planner owns dependency expansion (repo-local only) via the dedicated resolver.
    dep_res = resolve_dependencies(
        root,
        changed_unique,
        depth=2,
        max_files=200,
        config=ResolverConfig(max_file_bytes=max_file_bytes),
    )

    import_unique = sorted(set(import_unique_input + dep_res.resolved_files))
    candidates = sorted(set(changed_unique + import_unique))

    # RAG-based semantic boosts (Phase 2 enhancement)
    semantic_boosts: Dict[str, int] = {}
    if enable_semantic_boost and _RAG_AVAILABLE and spec_text:
        try:
            semantic_boosts = sync_enhance_risk_scores(
                root,
                spec_text,
                candidates,
            )
            if semantic_boosts:
                logger.info(f"RAG semantic boost applied to {len(semantic_boosts)} files")
        except Exception as e:
            logger.debug(f"RAG semantic boost unavailable: {e}")

    # Git signals (best-effort)
    git_new: Set[str] = set()
    git_churn: Dict[str, int] = {}
    git_recent: Dict[str, int] = {}
    if is_git_repo(root):
        try:
            sig = collect_git_signals(root, candidates)
            git_new = sig.new_files
            git_churn = sig.churn_lines
            git_recent = sig.recent_touches
        except Exception:
            pass

    # Phase 2: dependency centrality from resolver edges (reverse-deps within candidate set).
    centrality_in: Dict[str, int] = {p: 0 for p in candidates}
    cand_set = set(candidates)
    for _src, dst in dep_res.edges:
        if dst in cand_set:
            centrality_in[dst] = centrality_in.get(dst, 0) + 1

    def score_risk(rel: str, *, kind: str, is_forced: bool) -> Tuple[int, List[str]]:
        reasons: List[str] = []
        score = 0

        if is_forced:
            score += 100
            reasons.append("forced")

        rel_l = rel.lower()
        if any(
            x in rel_l
            for x in [
                "/.github/",
                "dockerfile",
                "docker-compose",
                "kubernetes",
                "helm",
                "terraform",
                "pulumi",
                "package.json",
                "pnpm-lock",
                "yarn.lock",
                "package-lock",
                "requirements",
                "pyproject",
                "tsconfig",
                "next.config",
                "vercel",
                "railway",
                "netlify",
                ".env",
                "secret",
                "key",
                "credential",
                "middleware",
                "auth",
                "oauth",
                "jwt",
                "session",
            ]
        ):
            score += 60
            reasons.append("infra_or_auth")

        if kind == "changed":
            score += 20
            reasons.append("changed")

        if rel in git_new:
            score += 50
            reasons.append("git_new")

        churn = int(git_churn.get(rel, 0) or 0)
        if churn > 0:
            score += min(50, (churn + 1) // 2)
            reasons.append(f"git_churn:{churn}")

        touches = int(git_recent.get(rel, 0) or 0)
        if touches > 0:
            score += min(20, touches)
            reasons.append(f"git_recent:{touches}")

        inc = int(centrality_in.get(rel, 0) or 0)
        if inc > 0:
            score += min(40, inc * 10)
            reasons.append(f"centrality_in:{inc}")

        try:
            sz = (root / rel).resolve().stat().st_size
        except Exception:
            sz = 0
        if sz > 200_000:
            score += 10
            reasons.append("large_file")

        # Phase 2: RAG semantic boost (if available)
        semantic_boost = semantic_boosts.get(rel, 0)
        if semantic_boost > 0:
            score += semantic_boost
            reasons.append(f"semantic_relevance:{semantic_boost}")

        return score, reasons

    def choose_planned_tier(rel: str, *, risk_score: int, kind: str) -> Tuple[str, str]:
        # Phase 1 principle: every changed file gets at least header.
        try:
            sz = (root / rel).resolve().stat().st_size
        except Exception:
            sz = 0

        if rel in forced_set and kind == "changed":
            # Forced: guarantee deep coverage (full when reasonable, else slice).
            if sz <= 180_000:
                return "full", "forced_full"
            return "slice", "forced_slice"

        if kind == "changed":
            if risk_score >= 90 and sz <= 180_000:
                return "full", "high_risk_small_full"
            if risk_score >= 90 and sz > 180_000:
                return "slice", "high_risk_large_slice"
            return "header", "baseline_header"

        # Import files: only deep-cover top-risk.
        if risk_score >= 110 and sz <= 160_000:
            return "full", "import_high_risk_full"
        if risk_score >= 110 and sz > 160_000:
            return "slice", "import_high_risk_slice"
        return "header", "import_header"

    manifest_items: List[FileManifestItem] = []

    def _manifest_for(rel: str, kind: str, forced: bool) -> Optional[FileManifestItem]:
        try:
            st = (root / rel).resolve().stat()
            b = int(st.st_size)
        except Exception:
            b = 0
        est = max(1, (b + 3) // 4)
        score, reasons = score_risk(rel, kind=kind, is_forced=forced)
        return FileManifestItem(
            rel_path=rel,
            bytes=b,
            est_tokens=est,
            kind=kind,
            ext=Path(rel).suffix.lower(),
            risk_score=score,
            risk_reasons=reasons,
        )

    for rel in changed_unique:
        mi = _manifest_for(rel, "changed", rel in forced_set)
        if mi:
            manifest_items.append(mi)
    for rel in import_unique:
        mi = _manifest_for(rel, "import", rel in forced_set)
        if mi:
            manifest_items.append(mi)

    # Plan ordering: changed first (broad coverage), then imports.
    manifest_sorted = sorted(manifest_items, key=lambda x: (-x.risk_score, x.kind, x.rel_path))

    items: List[CoveragePlanItem] = []
    for mi in manifest_sorted:
        tier, reason = choose_planned_tier(mi.rel_path, risk_score=mi.risk_score, kind=mi.kind)
        items.append(
            CoveragePlanItem(
                rel_path=mi.rel_path,
                kind=mi.kind,
                risk_score=mi.risk_score,
                risk_reasons=mi.risk_reasons,
                planned_tier=tier,
                planned_reason=reason,
            )
        )

    forced_changed = [p for p in changed_unique if p in forced_set]
    return CoveragePlan(items=items, manifest_items=manifest_sorted, forced_changed=forced_changed)


def render_context_plan(
    project_root: Path,
    *,
    plan: CoveragePlan,
    constitution_text: str,
    token_budget: int,
    max_file_bytes: int = _MAX_FILE_BYTES_DEFAULT,
) -> ContextBuildResult:
    """Phase 1: canonical prompt renderer from a CoveragePlan."""

    root = project_root.resolve()

    truncated: List[str] = []
    parts: List[str] = []
    file_snippets: Dict[str, str] = {}
    coverage_kinds: Dict[str, str] = {}
    skip_reasons: Dict[str, str] = {}

    def add_fitted_section(title: str, rel: str, content: str, remaining_tokens: int) -> Tuple[bool, int, str]:
        if remaining_tokens <= 0:
            return False, 0, ""

        def truncate_to_budget(text: str, remaining: int) -> str:
            remaining_chars = max(0, remaining * 4)
            if remaining_chars <= 0:
                return ""
            if len(text) <= remaining_chars:
                return text
            return text[: max(0, remaining_chars - 40)].rstrip() + "\n...<truncated>"

        snippet = truncate_to_budget(content, remaining_tokens)
        if not snippet:
            return False, 0, ""

        rendered = f"\n\n## {title}: {rel}\n{snippet}"
        while estimate_tokens(rendered) > remaining_tokens and len(snippet) > 200:
            base = snippet.replace("\n...<truncated>", "")
            base = base[: max(0, len(base) - 200)]
            snippet = base.rstrip() + "\n...<truncated>"
            rendered = f"\n\n## {title}: {rel}\n{snippet}"

        if estimate_tokens(rendered) > remaining_tokens:
            return False, 0, ""

        parts.append(rendered)
        used = estimate_tokens(rendered)
        return True, used, snippet

    running_tokens = 0

    # 0) Constitution
    included_constitution = False
    if constitution_text:
        remaining = token_budget - running_tokens
        added, used, snippet = add_fitted_section("Constitution", "constitution", constitution_text, remaining)
        if added:
            included_constitution = True
            running_tokens += used
            file_snippets["__constitution__"] = snippet
            coverage_kinds["__constitution__"] = "slice" if "...<truncated>" in snippet else "full"
            if coverage_kinds["__constitution__"] == "slice":
                truncated.append("__constitution__")
        else:
            truncated.append("__constitution__")
            skip_reasons["__constitution__"] = "could_not_fit"

    # 1) Manifest
    manifest_lines = [
        "PATH\tKIND\tBYTES\tEST_TOK\tRISK\tTIER\tREASONS",
    ]
    for item in plan.items[:600]:
        # Put planned tier inline.
        manifest_lines.append(
            f"{item.rel_path}\t{item.kind}\t{(root / item.rel_path).resolve().stat().st_size if (root / item.rel_path).exists() else 0}\t?\t{item.risk_score}\t{item.planned_tier}\t{','.join(item.risk_reasons)}"
        )
    manifest_text = "\n".join(manifest_lines)
    remaining = token_budget - running_tokens
    added, used, snippet = add_fitted_section("Manifest", "manifest", manifest_text, remaining)
    if added:
        running_tokens += used
        file_snippets["__manifest__"] = snippet
        coverage_kinds["__manifest__"] = "slice" if "...<truncated>" in snippet else "full"
        if coverage_kinds["__manifest__"] == "slice":
            truncated.append("__manifest__")
    else:
        truncated.append("__manifest__")
        skip_reasons["__manifest__"] = "could_not_fit"

    # 2) Coverage Plan table (explicit "why" for every file)
    cov_lines = ["PATH\tKIND\tROLE\tRISK\tPLANNED_TIER\tPLANNED_REASON"]
    for item in plan.items[:800]:
        cov_lines.append(
            f"{item.rel_path}\t{item.kind}\t{_infer_file_role(item.rel_path)}\t{item.risk_score}\t{item.planned_tier}\t{item.planned_reason}"
        )
    cov_text = "\n".join(cov_lines)
    remaining = token_budget - running_tokens
    added, used, snippet = add_fitted_section("Coverage Plan", "coverage_plan", cov_text, remaining)
    if added:
        running_tokens += used
        file_snippets["__coverage_plan__"] = snippet
        coverage_kinds["__coverage_plan__"] = "slice" if "...<truncated>" in snippet else "full"
        if coverage_kinds["__coverage_plan__"] == "slice":
            truncated.append("__coverage_plan__")
    else:
        truncated.append("__coverage_plan__")
        skip_reasons["__coverage_plan__"] = "could_not_fit"

    # Helper: compact header per file (language-aware + role)
    def _read_header_compact(rel: str, *, max_tokens: int) -> str:
        role = _infer_file_role(rel)
        rel_l = rel.lower()

        if rel_l.endswith(_JS_TS_EXTS):
            src = _read_text_file(root, rel, max_bytes=min(max_file_bytes, 256 * 1024))
            if src:
                header = f"// role: {role}\n" + extract_js_ts_header(rel, src, max_lines=120)
            else:
                header = f"// role: {role}\n"
        elif rel_l.endswith(".py"):
            src = _read_text_file(root, rel, max_bytes=min(max_file_bytes, 256 * 1024))
            header = f"# role: {role}\n" + (_python_ast_header(src, max_lines=120) if src else "")
        else:
            src = _read_text_file(root, rel, max_bytes=min(max_file_bytes, 64 * 1024))
            first_lines = "\n".join((src or "").splitlines()[:60])
            header = f"# role: {role}\n" + first_lines

        # Hard trim for budget.
        remaining_chars = max(0, max_tokens * 4)
        if remaining_chars <= 0:
            return ""
        if len(header) <= remaining_chars:
            return header
        return header[: max(0, remaining_chars - 40)].rstrip() + "\n...<truncated>"

    included_changed: List[str] = []
    included_imports: List[str] = []

    # 3) Baseline headers for ALL changed files (primary Phase 1 requirement)
    changed_items = [i for i in plan.items if i.kind == "changed"]
    import_items = [i for i in plan.items if i.kind != "changed"]

    # Ensure we reserve some budget per changed file.
    remaining = max(0, token_budget - running_tokens)
    per_header_total_tokens = max(24, min(80, remaining // max(1, len(changed_items))))

    for item in changed_items:
        rel = item.rel_path
        remaining = token_budget - running_tokens
        if remaining <= 0:
            truncated.append(rel)
            skip_reasons.setdefault(rel, "budget_exhausted")
            continue

        # Account for the section wrapper overhead so we don't overrun the per-file reserve.
        wrapper_overhead = estimate_tokens(f"\n\n## Header: {rel}\n")
        per_file_total = min(per_header_total_tokens, remaining)
        content_budget = max(8, per_file_total - wrapper_overhead)

        content = _read_header_compact(rel, max_tokens=content_budget)
        if not content:
            skip_reasons.setdefault(rel, "read_error")
            continue

        added, used, snippet = add_fitted_section("Header", rel, content, remaining)
        if not added:
            truncated.append(rel)
            skip_reasons.setdefault(rel, "could_not_fit")
            continue

        running_tokens += used
        included_changed.append(rel)
        file_snippets[rel] = snippet
        coverage_kinds[rel] = "slice" if "...<truncated>" in snippet else "header"
        if coverage_kinds[rel] == "slice":
            truncated.append(rel)
            skip_reasons.setdefault(rel, "truncated")

    # 4) Deep coverage upgrades (full/slice) for highest-risk subset
    def _deep_candidates(items: List[CoveragePlanItem]) -> List[CoveragePlanItem]:
        # Prioritize planned full/slice, then risk.
        return sorted(items, key=lambda i: (0 if i.planned_tier in {"full", "slice"} else 1, -i.risk_score, i.rel_path))

    deep_list = _deep_candidates(changed_items + import_items)

    # Only attempt a limited number of upgrades to avoid starving broad coverage.
    upgrades_budget = max(0, token_budget - running_tokens)
    max_upgrades = 10 if upgrades_budget > 1200 else 4
    upgraded = 0

    for item in deep_list:
        if upgraded >= max_upgrades:
            break
        if item.planned_tier not in {"full", "slice"}:
            continue
        rel = item.rel_path
        remaining = token_budget - running_tokens
        if remaining <= 0:
            break

        rel_l = rel.lower()
        abs_path = (root / rel).resolve()
        try:
            exists = abs_path.exists() and abs_path.is_file()
            size = abs_path.stat().st_size if exists else 0
        except Exception:
            exists = False
            size = 0
        if not exists:
            skip_reasons.setdefault(rel, "missing_file")
            continue

        if item.planned_tier == "full" and size <= max_file_bytes:
            content = _read_text_file(root, rel, max_bytes=max_file_bytes)
            title = "Full"
            planned_kind = "full"
        else:
            # Slices: Python AST symbols, else fallback to header.
            src = _read_text_file(root, rel, max_bytes=min(max_file_bytes, 512 * 1024))
            slices: List[str] = []
            if rel_l.endswith(".py"):
                slices = _python_symbol_slices(src)
            if not slices:
                # Fallback: compact header if slice not available.
                slices = [_read_header_compact(rel, max_tokens=min(120, remaining))]
            content = "\n\n".join([s for s in slices if s])
            title = "Slice"
            planned_kind = "slice"

        if not content:
            skip_reasons.setdefault(rel, "read_error")
            continue

        added, used, snippet = add_fitted_section(title, rel, content, remaining)
        if not added:
            truncated.append(rel)
            skip_reasons.setdefault(rel, "could_not_fit")
            continue

        running_tokens += used
        upgraded += 1
        file_snippets[rel] = snippet
        coverage_kinds[rel] = "slice" if "...<truncated>" in snippet else planned_kind
        if coverage_kinds[rel] == "slice":
            truncated.append(rel)
            skip_reasons.setdefault(rel, "truncated")

        if item.kind == "import" and rel not in included_imports:
            included_imports.append(rel)

    # If we didn't explicitly include imports, mark them as not included.
    for item in import_items:
        if item.rel_path not in coverage_kinds:
            skip_reasons.setdefault(item.rel_path, "not_included")

    # Rollups
    changed_unique = sorted({i.rel_path for i in changed_items})
    import_unique = sorted({i.rel_path for i in import_items})
    candidate_unique = sorted(set(changed_unique + import_unique))
    total_candidate_files = len(candidate_unique)
    changed_files_total = len(changed_unique)

    changed_full = sum(1 for p in changed_unique if coverage_kinds.get(p) == "full")
    changed_header = sum(1 for p in changed_unique if coverage_kinds.get(p) == "header")
    changed_slice = sum(1 for p in changed_unique if coverage_kinds.get(p) == "slice")
    changed_unknown = max(0, changed_files_total - (changed_full + changed_header + changed_slice))
    fully_covered_percent = (100.0 * changed_full / changed_files_total) if changed_files_total > 0 else 100.0

    # Ensure any candidate not in coverage_kinds is explicitly recorded.
    for p in candidate_unique:
        if p not in coverage_kinds:
            skip_reasons.setdefault(p, "not_included")

    partial = (len(truncated) > 0) or (not included_constitution) or any(v == "slice" for v in coverage_kinds.values())
    context = "".join(parts).strip()

    return ContextBuildResult(
        context=context,
        token_count=running_tokens,
        partial=partial,
        truncated_files=truncated,
        included_changed_files=included_changed,
        included_import_files=included_imports,
        included_constitution=included_constitution,
        file_snippets=file_snippets,
        coverage_kinds=coverage_kinds,
        total_candidate_files=total_candidate_files,
        changed_files_total=changed_files_total,
        changed_files_fully_covered_count=changed_full,
        changed_files_header_covered_count=changed_header,
        changed_files_unknown_count=changed_unknown,
        fully_covered_percent_of_changed=round(fully_covered_percent, 2),
        skip_reasons=skip_reasons,
    )
