"""Polyglot dependency resolver (Phase 2).

This module is intentionally deterministic and repo-local:
- It never resolves to external dependencies (e.g. node_modules).
- It never returns paths outside the repo root.

Supported:
- Python: AST-based import parsing + dotted/relative import resolution.
- JS/TS: Tree-sitter (optional) or regex fallback via ts_imports, plus:
  - relative specifiers (./ ../)
  - repo-root absolute (/foo)
  - tsconfig/jsconfig compilerOptions.baseUrl + paths (single * wildcard)
  - conservative package.json workspaces (repo-local packages)
"""

from __future__ import annotations

import ast
import json
import re
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from loguru import logger

try:
    from .ts_imports import extract_imports
except Exception:  # pragma: no cover
    from modules.ts_imports import extract_imports  # type: ignore


_JS_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


@dataclass(frozen=True)
class ResolverConfig:
    max_file_bytes: int = 512 * 1024
    enable_tsconfig_paths: bool = True
    enable_workspaces: bool = True


@dataclass(frozen=True)
class ResolutionResult:
    resolved_files: List[str]
    skipped_imports: List[str]
    diagnostics: Dict[str, int]
    edges: List[Tuple[str, str]]  # (src_rel, dst_rel)


def _safe_relative_to(path: Path, root: Path) -> Optional[str]:
    try:
        rel = path.resolve().relative_to(root.resolve())
        return rel.as_posix()
    except Exception:
        return None


def _strip_jsonc(text: str) -> str:
    # Best-effort JSONC -> JSON (enough for common tsconfig/jsconfig files).
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(^|\s)//.*$", "", text, flags=re.MULTILINE)
    return text


@lru_cache(maxsize=16)
def _load_tsconfig_compiler_options(root: Path) -> Tuple[Optional[str], Dict[str, List[str]]]:
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

    # Deterministic priority: iterate `paths` in the JSON order as loaded.
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

    # baseUrl resolution for bare specifiers
    if base_url and spec and not spec.startswith("./") and not spec.startswith("../") and not spec.startswith("/"):
        abs_path = (base_dir / spec).resolve()
        rel = _safe_relative_to(abs_path, root)
        if rel:
            out.append(rel)

    # De-dupe while preserving order
    seen: Set[str] = set()
    uniq: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


@lru_cache(maxsize=32)
def _load_root_workspaces_patterns(root: Path) -> List[str]:
    pkg = (root / "package.json").resolve()
    try:
        if not pkg.exists() or not pkg.is_file():
            return []
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace") or "{}")
        ws = data.get("workspaces")
        if isinstance(ws, list):
            return [str(x) for x in ws if isinstance(x, str)]
        if isinstance(ws, dict):
            pkgs = ws.get("packages")
            if isinstance(pkgs, list):
                return [str(x) for x in pkgs if isinstance(x, str)]
        return []
    except Exception:
        return []


@lru_cache(maxsize=32)
def _workspace_name_to_dir(root: Path) -> Dict[str, str]:
    patterns = _load_root_workspaces_patterns(root)
    if not patterns:
        return {}

    mapping: Dict[str, str] = {}
    seen_dirs: Set[str] = set()

    for pat in patterns[:50]:
        try:
            for p in root.glob(pat):
                try:
                    if not p.is_dir():
                        continue
                    rel = _safe_relative_to(p, root)
                    if not rel or "node_modules" in rel.split("/"):
                        continue
                    if rel in seen_dirs:
                        continue
                    seen_dirs.add(rel)

                    pkg_json = (p / "package.json").resolve()
                    if not pkg_json.exists() or not pkg_json.is_file():
                        continue
                    data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace") or "{}")
                    name = data.get("name")
                    if isinstance(name, str) and name and name not in mapping:
                        mapping[name] = rel
                except Exception:
                    continue
        except Exception:
            continue

    return mapping


def _workspace_entry_candidates(root: Path, pkg_dir_rel: str) -> List[str]:
    pkg_dir = (root / pkg_dir_rel).resolve()

    # Conservative priority:
    # 1) package.json module/main/source
    # 2) src/index.*
    # 3) index.*
    try:
        data = json.loads((pkg_dir / "package.json").read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        data = {}

    out: List[str] = []
    for field in ("module", "main", "source"):
        v = data.get(field)
        if isinstance(v, str) and v:
            out.append((Path(pkg_dir_rel) / v).as_posix())

    for ext in _JS_TS_EXTS:
        out.append((Path(pkg_dir_rel) / "src" / f"index{ext}").as_posix())
    for ext in _JS_TS_EXTS:
        out.append((Path(pkg_dir_rel) / f"index{ext}").as_posix())

    # De-dupe
    seen: Set[str] = set()
    uniq: List[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def _workspace_spec_candidates(root: Path, spec: str) -> List[str]:
    mapping = _workspace_name_to_dir(root)
    if not mapping:
        return []

    pkg_name = ""
    subpath = ""

    if spec.startswith("@"):
        parts = spec.split("/")
        if len(parts) >= 2:
            pkg_name = "/".join(parts[:2])
            subpath = "/".join(parts[2:])
    else:
        parts = spec.split("/")
        pkg_name = parts[0] if parts else ""
        subpath = "/".join(parts[1:]) if len(parts) > 1 else ""

    pkg_dir_rel = mapping.get(pkg_name)
    if not pkg_dir_rel:
        return []

    if not subpath:
        return _workspace_entry_candidates(root, pkg_dir_rel)

    # Subpath import within workspace package: try both <pkg>/<subpath> and <pkg>/src/<subpath>
    bases = [
        (Path(pkg_dir_rel) / subpath).as_posix(),
        (Path(pkg_dir_rel) / "src" / subpath).as_posix(),
    ]

    candidates: List[str] = []
    for base in bases:
        p = Path(base)
        if p.suffix.lower() in _JS_TS_EXTS:
            candidates.append(p.as_posix())
        else:
            for ext in _JS_TS_EXTS:
                candidates.append(p.with_suffix(ext).as_posix())
            for ext in _JS_TS_EXTS:
                candidates.append((p / f"index{ext}").as_posix())

    # De-dupe
    seen: Set[str] = set()
    uniq: List[str] = []
    for x in candidates:
        if x in seen:
            continue
        seen.add(x)
        uniq.append(x)
    return uniq


def _module_to_candidate_paths(module: str) -> List[str]:
    parts = module.split(".")
    base = "/".join(parts)
    return [f"{base}.py", f"{base}/__init__.py"]


def _parse_imports_python(source: str) -> Set[str]:
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
                prefix = "." * node.level
                imports.add(prefix + node.module)
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        imports.add(prefix + node.module + "." + alias.name)
            elif node.level:
                imports.add("." * node.level)

    return imports


def _resolve_python_module_to_rel(root: Path, module: str, base_rel: str) -> Optional[str]:
    module = (module or "").strip()
    if not module:
        return None

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


def _resolve_js_ts_specifier_to_rel(root: Path, spec: str, base_rel: str, *, config: ResolverConfig) -> Tuple[Optional[str], str]:
    spec = (spec or "").strip()
    if not spec:
        return None, "skipped_invalid_spec"

    base_rel_l = base_rel.lower()
    if not base_rel_l.endswith(_JS_TS_EXTS):
        return None, "skipped_invalid_spec"

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
        # Aliases/workspaces only for bare specifiers.
        if config.enable_tsconfig_paths:
            candidate_bases.extend(_tsconfig_alias_candidates(root, spec))
        if config.enable_workspaces:
            candidate_bases.extend(_workspace_spec_candidates(root, spec))

        if not candidate_bases:
            return None, "skipped_external"

    for base in candidate_bases:
        cand_path = Path(base)
        candidates: List[str] = []

        if cand_path.suffix.lower() in _JS_TS_EXTS:
            candidates.append(cand_path.as_posix())
        else:
            for ext in _JS_TS_EXTS:
                candidates.append(cand_path.with_suffix(ext).as_posix())
            for ext in _JS_TS_EXTS:
                candidates.append((cand_path / f"index{ext}").as_posix())

        for cand in candidates:
            path = (root / cand).resolve()
            rel = _safe_relative_to(path, root)
            if rel and path.exists() and path.is_file():
                return rel, "ok"

    return None, "skipped_missing"


def _read_text_file(root: Path, rel: str, *, max_bytes: int) -> Optional[str]:
    path = (root / rel).resolve()
    rel_safe = _safe_relative_to(path, root)
    if not rel_safe:
        return None

    try:
        if not path.exists() or not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _parse_imports_polyglot(rel_path: str, source: str) -> Set[str]:
    if rel_path.lower().endswith(".py"):
        return _parse_imports_python(source)

    out: Set[str] = set()
    res = extract_imports(rel_path, source)
    for imp in res.imports:
        if imp:
            out.add(imp)
    return out


def resolve_dependencies(
    project_root: Path,
    entry_files: Sequence[str],
    *,
    depth: int,
    max_files: int,
    config: ResolverConfig,
) -> ResolutionResult:
    root = project_root.resolve()

    diagnostics: Dict[str, int] = {
        "files_seen": 0,
        "files_read": 0,
        "imports_seen": 0,
        "imports_resolved": 0,
        "skipped_external": 0,
        "skipped_missing": 0,
        "skipped_too_large": 0,
        "skipped_invalid_spec": 0,
    }

    resolved: Set[str] = set()
    skipped: Set[str] = set()
    edges: List[Tuple[str, str]] = []

    read_cache: Dict[str, Optional[str]] = {}
    imports_cache: Dict[str, Set[str]] = {}

    seed = [(f or "").replace("\\", "/") for f in entry_files if f]
    frontier: deque[Tuple[str, int]] = deque([(f, 0) for f in seed])
    seen: Set[str] = set(seed)

    while frontier:
        rel, d = frontier.popleft()
        if rel.startswith("../") or rel.startswith("..\\"):
            continue
        if d >= depth:
            continue

        diagnostics["files_seen"] += 1

        if rel in read_cache:
            src = read_cache[rel]
        else:
            src = _read_text_file(root, rel, max_bytes=config.max_file_bytes)
            read_cache[rel] = src

        if src is None:
            # Differentiate too-large vs missing (best-effort).
            p = (root / rel).resolve()
            try:
                if p.exists() and p.is_file() and p.stat().st_size > config.max_file_bytes:
                    diagnostics["skipped_too_large"] += 1
                else:
                    diagnostics["skipped_missing"] += 1
            except Exception:
                diagnostics["skipped_missing"] += 1
            continue

        diagnostics["files_read"] += 1

        if rel in imports_cache:
            imports = imports_cache[rel]
        else:
            imports = _parse_imports_polyglot(rel, src)
            imports_cache[rel] = imports

        for imp in sorted(imports):
            diagnostics["imports_seen"] += 1

            resolved_rel: Optional[str] = None
            reason = ""

            if rel.lower().endswith(".py"):
                resolved_rel = _resolve_python_module_to_rel(root, imp, rel)
                reason = "ok" if resolved_rel else "skipped_missing"
            elif rel.lower().endswith(_JS_TS_EXTS):
                resolved_rel, reason = _resolve_js_ts_specifier_to_rel(root, imp, rel, config=config)
            else:
                reason = "skipped_invalid_spec"

            if not resolved_rel:
                skipped.add(imp)
                if reason in diagnostics:
                    diagnostics[reason] += 1
                elif reason.startswith("skipped_"):
                    diagnostics[reason] = diagnostics.get(reason, 0) + 1
                else:
                    diagnostics["skipped_missing"] += 1
                continue

            diagnostics["imports_resolved"] += 1
            edges.append((rel, resolved_rel))

            if resolved_rel in seen:
                continue
            seen.add(resolved_rel)
            resolved.add(resolved_rel)
            frontier.append((resolved_rel, d + 1))

            if len(seen) >= max_files:
                logger.warning(f"resolve_dependencies hit max_files={max_files}")
                break

    return ResolutionResult(
        resolved_files=sorted(resolved),
        skipped_imports=sorted(skipped),
        diagnostics=diagnostics,
        edges=edges,
    )
