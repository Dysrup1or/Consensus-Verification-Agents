"""Polyglot import extraction helpers.

Primary strategy (optional): Tree-sitter via a prebuilt language pack.
Fallback: conservative regex for JS/TS and plain AST for Python is handled elsewhere.

We keep this module dependency-optional so Invariant works out-of-the-box.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class TreeSitterStatus:
    available: bool
    reason: str


def get_tree_sitter_status() -> TreeSitterStatus:
    """Best-effort probe for whether Tree-sitter is usable in this environment.

    This must not throw; it is used for explicit operational reporting and tests.
    """

    try:
        from tree_sitter_language_pack import get_language, get_parser  # type: ignore

        parser = get_parser("javascript")
        language = get_language("javascript")
        if parser and language:
            return TreeSitterStatus(available=True, reason="ok")
        return TreeSitterStatus(available=False, reason="parser_or_language_missing")
    except Exception as e:
        # Keep the reason stable-ish for assertions while still useful for debugging.
        name = type(e).__name__
        if name in {"ModuleNotFoundError", "ImportError"}:
            return TreeSitterStatus(available=False, reason="not_installed")
        return TreeSitterStatus(available=False, reason=f"error:{name}")


@dataclass(frozen=True)
class ImportExtraction:
    imports: List[str]
    used_tree_sitter: bool
    warnings: List[str]


@dataclass(frozen=True)
class JSImportDetails:
    imports: List[str]
    exports: List[str]
    signatures: List[str]
    used_tree_sitter: bool
    warnings: List[str]


_JS_IMPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:import\s+(?:type\s+)?[\s\S]*?from\s+['\"]([^'\"]+)['\"]\s*;?|import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)|require\(\s*['\"]([^'\"]+)['\"]\s*\))",
    re.MULTILINE,
)


def _infer_lang(rel_path: str) -> str:
    p = Path(rel_path)
    ext = p.suffix.lower()
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if ext == ".py":
        return "python"
    return "unknown"


def extract_imports(rel_path: str, source: str) -> ImportExtraction:
    lang = _infer_lang(rel_path)

    if lang in {"javascript", "typescript"}:
        details = extract_js_ts_details(rel_path, source)
        return ImportExtraction(imports=details.imports, used_tree_sitter=details.used_tree_sitter, warnings=details.warnings)

    return ImportExtraction(imports=[], used_tree_sitter=False, warnings=[f"unsupported_language:{lang}"])


def extract_js_ts_details(rel_path: str, source: str) -> JSImportDetails:
    """Extract imports/exports/signatures for JS/TS.

    If Tree-sitter is available, this uses Tree-sitter queries (not regex) to
    extract module specifiers, exports, and top-level signatures.
    """

    lang = _infer_lang(rel_path)
    if lang not in {"javascript", "typescript"}:
        return JSImportDetails(imports=[], exports=[], signatures=[], used_tree_sitter=False, warnings=[f"unsupported_language:{lang}"])

    # Tree-sitter path (preferred)
    try:
        from tree_sitter import Query  # type: ignore
        from tree_sitter_language_pack import get_language, get_parser  # type: ignore

        parser = get_parser(lang)
        language = get_language(lang)
        if not parser or not language:
            raise RuntimeError("tree_sitter_language_pack returned no parser/language")

        source_bytes = bytes(source or "", "utf-8")
        tree = parser.parse(source_bytes)

        imports = _ts_query_imports(language, tree, source_bytes)
        exports = _ts_query_exports(language, tree, source_bytes)
        signatures = _ts_query_signatures(language, tree, source_bytes)

        return JSImportDetails(
            imports=sorted(set(imports)),
            exports=sorted(set(exports)),
            signatures=_dedupe_keep_order(signatures, limit=80),
            used_tree_sitter=True,
            warnings=[],
        )
    except Exception:
        # Fallback: regex for imports only (keeps Invariant working even without optional deps).
        imports = _extract_js_like_imports(source)
        return JSImportDetails(imports=imports, exports=[], signatures=[], used_tree_sitter=False, warnings=["tree_sitter_unavailable"])


def extract_js_ts_header(rel_path: str, source: str, *, max_lines: int = 200) -> str:
    """Build a compact, consistent header for JS/TS for use in LLM context packing."""

    details = extract_js_ts_details(rel_path, source)
    lines: List[str] = []
    lines.append(f"// invariant:header used_tree_sitter={str(details.used_tree_sitter).lower()}")

    if details.imports:
        lines.append("// imports")
        for m in details.imports[:100]:
            lines.append(f"import: {m}")

    if details.exports:
        lines.append("// exports")
        for e in details.exports[:120]:
            lines.append(f"export: {e}")

    if details.signatures:
        lines.append("// signatures")
        for s in details.signatures[:120]:
            lines.append(s)

    # Attach a warning line if we fell back.
    if details.warnings:
        lines.append("// warnings")
        for w in details.warnings[:10]:
            lines.append(f"warn: {w}")

    return "\n".join(lines[:max_lines]).strip() + "\n"


def _node_text(source_bytes: bytes, node) -> str:
    try:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == "\"") or (s[0] == s[-1] == "'") or (s[0] == s[-1] == "`")):
        return s[1:-1]
    return s


def _dedupe_keep_order(items: Sequence[str], *, limit: int) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for it in items:
        if not it:
            continue
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def _ts_query_imports(language, tree, source_bytes: bytes) -> List[str]:
    # Covers: static imports, dynamic import("x"), require("x")
    queries = [
        "(import_statement source: (string) @mod)",
        "(call_expression function: (identifier) @fn arguments: (arguments (string) @mod) (#eq? @fn \"require\"))",
        "(call_expression function: (import) arguments: (arguments (string) @mod))",
    ]

    found: List[str] = []
    for q in queries:
        try:
            from tree_sitter import Query  # type: ignore

            query = Query(language, q)
            for node, cap in query.captures(tree.root_node):
                if cap == "mod":
                    lit = _strip_quotes(_node_text(source_bytes, node))
                    if lit:
                        found.append(lit)
        except Exception:
            continue

    return found


def _ts_query_exports(language, tree, source_bytes: bytes) -> List[str]:
    exports: List[str] = []

    # export { a as b }
    queries = [
        "(export_statement (export_clause (export_specifier name: (identifier) @name)))",
        "(export_statement (export_clause (export_specifier name: (type_identifier) @name)))",
        "(export_statement (export_clause (export_specifier alias: (identifier) @alias)))",
        "(export_statement (export_clause (export_specifier alias: (type_identifier) @alias)))",
        "(export_default_declaration (identifier) @default)",
        "(export_default_declaration (function_declaration name: (identifier) @default_fn))",
        "(export_default_declaration (class_declaration name: (identifier) @default_class))",
    ]

    for q in queries:
        try:
            from tree_sitter import Query  # type: ignore

            query = Query(language, q)
            for node, cap in query.captures(tree.root_node):
                txt = _node_text(source_bytes, node).strip()
                if not txt:
                    continue
                if cap.startswith("default"):
                    exports.append(f"default {txt}")
                elif cap == "alias":
                    exports.append(f"as {txt}")
                else:
                    exports.append(txt)
        except Exception:
            continue

    return exports


def _ts_query_signatures(language, tree, source_bytes: bytes) -> List[str]:
    sigs: List[str] = []

    # These queries are intentionally name-based; we avoid capturing bodies.
    queries = [
        "(function_declaration name: (identifier) @name parameters: (formal_parameters) @params)",
        "(class_declaration name: (identifier) @name)",
        "(interface_declaration name: (type_identifier) @name)",
        "(type_alias_declaration name: (type_identifier) @name)",
        "(enum_declaration name: (identifier) @name)",
    ]

    for q in queries:
        try:
            from tree_sitter import Query  # type: ignore

            query = Query(language, q)
            # We need pairing for function name+params; collect per match by reading captures grouped.
            # tree_sitter.Query doesn't expose match grouping consistently across versions, so we do a best-effort pairing.
            captures = list(query.captures(tree.root_node))
            if "formal_parameters" not in q:
                for node, cap in captures:
                    if cap == "name":
                        name = _node_text(source_bytes, node).strip()
                        if q.startswith("(class_declaration"):
                            sigs.append(f"class {name}")
                        elif q.startswith("(interface_declaration"):
                            sigs.append(f"interface {name}")
                        elif q.startswith("(type_alias_declaration"):
                            sigs.append(f"type {name}")
                        elif q.startswith("(enum_declaration"):
                            sigs.append(f"enum {name}")
                continue

            # function query: try to pair nearest params capture after each name capture
            name_nodes = [n for (n, cap) in captures if cap == "name"]
            param_nodes = [n for (n, cap) in captures if cap == "params"]
            for n in name_nodes:
                name = _node_text(source_bytes, n).strip()
                params_txt = "()"
                # pick the closest params that starts after name
                after = [p for p in param_nodes if p.start_byte >= n.end_byte]
                if after:
                    params_txt = _node_text(source_bytes, after[0]).strip() or "()"
                sigs.append(f"function {name}{params_txt}")
        except Exception:
            continue

    return sigs


def _extract_js_like_imports(source: str) -> List[str]:
    found: Set[str] = set()
    for m in _JS_IMPORT_RE.finditer(source or ""):
        for g in m.groups():
            if not g:
                continue
            # ignore node builtins and absolute urls; resolver decides what to do
            found.add(g.strip())
    return sorted(found)
