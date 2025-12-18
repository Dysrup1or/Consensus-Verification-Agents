"""
Dysruption CVA - Embedding Store Module
Version: 1.0

SQLite-backed storage for code embeddings with incremental update support.
Uses content hashing to avoid re-embedding unchanged files.

Architecture:
- embeddings table: stores file metadata and chunk info
- embedding vectors stored as numpy .npy files on disk
- content_hash enables incremental indexing

Usage:
    from modules.embedding_store import EmbeddingStore
    
    store = EmbeddingStore("db/embeddings.db", "embeddings/")
    store.init_db()
    
    # Store embedding
    store.upsert_embedding(
        project_id="my_project",
        file_path="modules/tribunal.py",
        chunk_id=0,
        content_hash="abc123",
        embedding_vector=np.array([0.1, 0.2, ...]),
        chunk_text="def evaluate_criterion...",
        chunk_type="function"
    )
    
    # Query for changed files
    unchanged = store.get_unchanged_files(project_id, file_hashes)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

import numpy as np
from loguru import logger


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class EmbeddingRow:
    """Single embedding record from the database."""
    
    id: int
    project_id: str
    file_path: str
    chunk_id: int
    content_hash: str
    chunk_type: str  # 'function', 'class', 'module', 'docstring', 'block'
    chunk_start_line: int
    chunk_end_line: int
    chunk_text_preview: str  # First 200 chars for debugging
    embedding_dim: int
    created_at: int
    updated_at: int


@dataclass
class FileEmbeddingInfo:
    """Summary of embeddings for a single file."""
    
    file_path: str
    content_hash: str
    chunk_count: int
    total_tokens_estimate: int
    last_updated: int


@dataclass
class SearchResult:
    """Single search result with similarity score."""
    
    file_path: str
    chunk_id: int
    chunk_type: str
    chunk_text_preview: str
    similarity_score: float
    chunk_start_line: int
    chunk_end_line: int


@dataclass
class FileSearchResult:
    """Aggregated search result at file level."""
    
    file_path: str
    max_similarity: float
    avg_similarity: float
    matching_chunks: int
    total_chunks: int
    top_chunk_previews: List[str] = field(default_factory=list)


# =============================================================================
# EMBEDDING STORE CLASS
# =============================================================================


class EmbeddingStore:
    """
    SQLite-backed embedding storage with numpy vector files.
    
    Design decisions:
    - SQLite for metadata (fast queries, ACID, no external deps)
    - Numpy files for vectors (fast load, standard format)
    - Content hash for incremental updates (skip unchanged files)
    - Project isolation (multiple projects in one DB)
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(
        self,
        db_path: Union[str, Path] = "db/embeddings.db",
        vectors_dir: Union[str, Path] = "embeddings/",
        embedding_dim: int = 1536,  # OpenAI text-embedding-3-small default
    ):
        """
        Initialize embedding store.
        
        Args:
            db_path: Path to SQLite database
            vectors_dir: Directory for numpy vector files
            embedding_dim: Dimension of embedding vectors
        """
        self.db_path = Path(db_path)
        self.vectors_dir = Path(vectors_dir)
        self.embedding_dim = embedding_dim
        
    def init_db(self) -> None:
        """Initialize database schema and vector directory."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)
            
            # Check current version
            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0
            
            if current_version < self.SCHEMA_VERSION:
                self._migrate_schema(conn, current_version)
            
            conn.commit()
    
    def _migrate_schema(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Apply schema migrations."""
        if from_version < 1:
            # Initial schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    chunk_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    chunk_type TEXT NOT NULL DEFAULT 'block',
                    chunk_start_line INTEGER NOT NULL DEFAULT 1,
                    chunk_end_line INTEGER NOT NULL DEFAULT 1,
                    chunk_text_preview TEXT NOT NULL DEFAULT '',
                    embedding_dim INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    
                    UNIQUE(project_id, file_path, chunk_id)
                )
            """)
            
            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_project 
                ON embeddings(project_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_file 
                ON embeddings(project_id, file_path)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_embeddings_hash 
                ON embeddings(project_id, content_hash)
            """)
            
            # File-level summary table for quick lookups
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_index (
                    project_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    total_tokens_estimate INTEGER NOT NULL DEFAULT 0,
                    last_indexed_at INTEGER NOT NULL,
                    
                    PRIMARY KEY(project_id, file_path)
                )
            """)
            
            # Update schema version
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", 
                        (self.SCHEMA_VERSION,))
            
            logger.info(f"Initialized embedding store schema v{self.SCHEMA_VERSION}")
    
    # =========================================================================
    # VECTOR FILE OPERATIONS
    # =========================================================================
    
    def _vector_path(self, project_id: str, file_path: str, chunk_id: int) -> Path:
        """Get path for a vector file."""
        # Create safe filename from file_path
        safe_name = file_path.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.vectors_dir / project_id / f"{safe_name}_chunk{chunk_id}.npy"
    
    def _save_vector(
        self, 
        project_id: str, 
        file_path: str, 
        chunk_id: int, 
        vector: np.ndarray
    ) -> None:
        """Save embedding vector to disk."""
        path = self._vector_path(project_id, file_path, chunk_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(str(path), vector.astype(np.float32))
    
    def _load_vector(
        self, 
        project_id: str, 
        file_path: str, 
        chunk_id: int
    ) -> Optional[np.ndarray]:
        """Load embedding vector from disk."""
        path = self._vector_path(project_id, file_path, chunk_id)
        if not path.exists():
            return None
        try:
            return np.load(str(path))
        except Exception as e:
            logger.warning(f"Failed to load vector {path}: {e}")
            return None
    
    def _delete_file_vectors(self, project_id: str, file_path: str) -> None:
        """Delete all vector files for a file."""
        safe_name = file_path.replace("/", "_").replace("\\", "_").replace(":", "_")
        project_dir = self.vectors_dir / project_id
        if not project_dir.exists():
            return
        
        for path in project_dir.glob(f"{safe_name}_chunk*.npy"):
            try:
                path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete vector {path}: {e}")
    
    # =========================================================================
    # CONTENT HASHING
    # =========================================================================
    
    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    # =========================================================================
    # CRUD OPERATIONS
    # =========================================================================
    
    def upsert_embedding(
        self,
        project_id: str,
        file_path: str,
        chunk_id: int,
        content_hash: str,
        embedding_vector: np.ndarray,
        chunk_text: str,
        chunk_type: str = "block",
        chunk_start_line: int = 1,
        chunk_end_line: int = 1,
    ) -> int:
        """
        Insert or update an embedding.
        
        Returns:
            Row ID of the upserted embedding
        """
        now = int(time.time())
        preview = chunk_text[:200] if chunk_text else ""
        
        # Save vector to disk
        self._save_vector(project_id, file_path, chunk_id, embedding_vector)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                INSERT INTO embeddings 
                (project_id, file_path, chunk_id, content_hash, chunk_type,
                 chunk_start_line, chunk_end_line, chunk_text_preview, 
                 embedding_dim, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, file_path, chunk_id) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    chunk_type = excluded.chunk_type,
                    chunk_start_line = excluded.chunk_start_line,
                    chunk_end_line = excluded.chunk_end_line,
                    chunk_text_preview = excluded.chunk_text_preview,
                    embedding_dim = excluded.embedding_dim,
                    updated_at = excluded.updated_at
            """, (
                project_id, file_path, chunk_id, content_hash, chunk_type,
                chunk_start_line, chunk_end_line, preview,
                len(embedding_vector), now, now
            ))
            conn.commit()
            return cursor.lastrowid or 0
    
    def update_file_index(
        self,
        project_id: str,
        file_path: str,
        content_hash: str,
        chunk_count: int,
        total_tokens_estimate: int,
    ) -> None:
        """Update the file-level index after indexing all chunks."""
        now = int(time.time())
        
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO file_index 
                (project_id, file_path, content_hash, chunk_count, 
                 total_tokens_estimate, last_indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, file_path) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    chunk_count = excluded.chunk_count,
                    total_tokens_estimate = excluded.total_tokens_estimate,
                    last_indexed_at = excluded.last_indexed_at
            """, (
                project_id, file_path, content_hash, 
                chunk_count, total_tokens_estimate, now
            ))
            conn.commit()
    
    def get_file_info(
        self, 
        project_id: str, 
        file_path: str
    ) -> Optional[FileEmbeddingInfo]:
        """Get embedding info for a specific file."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                SELECT file_path, content_hash, chunk_count, 
                       total_tokens_estimate, last_indexed_at
                FROM file_index
                WHERE project_id = ? AND file_path = ?
            """, (project_id, file_path))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return FileEmbeddingInfo(
                file_path=row[0],
                content_hash=row[1],
                chunk_count=row[2],
                total_tokens_estimate=row[3],
                last_updated=row[4],
            )
    
    def get_unchanged_files(
        self,
        project_id: str,
        file_hashes: Dict[str, str],
    ) -> Set[str]:
        """
        Return set of files that haven't changed (same content hash).
        
        Args:
            project_id: Project identifier
            file_hashes: Dict of {file_path: content_hash}
            
        Returns:
            Set of file paths that are already indexed with same hash
        """
        if not file_hashes:
            return set()
        
        unchanged = set()
        
        with sqlite3.connect(str(self.db_path)) as conn:
            for file_path, content_hash in file_hashes.items():
                cursor = conn.execute("""
                    SELECT content_hash FROM file_index
                    WHERE project_id = ? AND file_path = ?
                """, (project_id, file_path))
                
                row = cursor.fetchone()
                if row and row[0] == content_hash:
                    unchanged.add(file_path)
        
        return unchanged
    
    def get_all_embeddings(
        self, 
        project_id: str
    ) -> List[Tuple[EmbeddingRow, np.ndarray]]:
        """
        Load all embeddings for a project.
        
        Returns:
            List of (metadata, vector) tuples
        """
        results = []
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                SELECT id, project_id, file_path, chunk_id, content_hash,
                       chunk_type, chunk_start_line, chunk_end_line,
                       chunk_text_preview, embedding_dim, created_at, updated_at
                FROM embeddings
                WHERE project_id = ?
                ORDER BY file_path, chunk_id
            """, (project_id,))
            
            for row in cursor.fetchall():
                meta = EmbeddingRow(
                    id=row[0],
                    project_id=row[1],
                    file_path=row[2],
                    chunk_id=row[3],
                    content_hash=row[4],
                    chunk_type=row[5],
                    chunk_start_line=row[6],
                    chunk_end_line=row[7],
                    chunk_text_preview=row[8],
                    embedding_dim=row[9],
                    created_at=row[10],
                    updated_at=row[11],
                )
                
                vector = self._load_vector(project_id, meta.file_path, meta.chunk_id)
                if vector is not None:
                    results.append((meta, vector))
        
        return results
    
    def get_file_embeddings(
        self, 
        project_id: str, 
        file_path: str
    ) -> List[Tuple[EmbeddingRow, np.ndarray]]:
        """Load all embeddings for a specific file."""
        results = []
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                SELECT id, project_id, file_path, chunk_id, content_hash,
                       chunk_type, chunk_start_line, chunk_end_line,
                       chunk_text_preview, embedding_dim, created_at, updated_at
                FROM embeddings
                WHERE project_id = ? AND file_path = ?
                ORDER BY chunk_id
            """, (project_id, file_path))
            
            for row in cursor.fetchall():
                meta = EmbeddingRow(
                    id=row[0],
                    project_id=row[1],
                    file_path=row[2],
                    chunk_id=row[3],
                    content_hash=row[4],
                    chunk_type=row[5],
                    chunk_start_line=row[6],
                    chunk_end_line=row[7],
                    chunk_text_preview=row[8],
                    embedding_dim=row[9],
                    created_at=row[10],
                    updated_at=row[11],
                )
                
                vector = self._load_vector(project_id, file_path, meta.chunk_id)
                if vector is not None:
                    results.append((meta, vector))
        
        return results
    
    def delete_file(self, project_id: str, file_path: str) -> int:
        """
        Delete all embeddings for a file.
        
        Returns:
            Number of chunks deleted
        """
        # Delete vectors from disk
        self._delete_file_vectors(project_id, file_path)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                DELETE FROM embeddings
                WHERE project_id = ? AND file_path = ?
            """, (project_id, file_path))
            
            conn.execute("""
                DELETE FROM file_index
                WHERE project_id = ? AND file_path = ?
            """, (project_id, file_path))
            
            conn.commit()
            return cursor.rowcount
    
    def delete_project(self, project_id: str) -> int:
        """
        Delete all embeddings for a project.
        
        Returns:
            Number of embeddings deleted
        """
        # Delete vector directory
        project_vector_dir = self.vectors_dir / project_id
        if project_vector_dir.exists():
            import shutil
            shutil.rmtree(str(project_vector_dir), ignore_errors=True)
        
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                DELETE FROM embeddings WHERE project_id = ?
            """, (project_id,))
            
            conn.execute("""
                DELETE FROM file_index WHERE project_id = ?
            """, (project_id,))
            
            conn.commit()
            return cursor.rowcount
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self, project_id: str) -> Dict[str, Any]:
        """Get statistics for a project's embeddings."""
        with sqlite3.connect(str(self.db_path)) as conn:
            # File count
            cursor = conn.execute("""
                SELECT COUNT(DISTINCT file_path) FROM file_index
                WHERE project_id = ?
            """, (project_id,))
            file_count = cursor.fetchone()[0]
            
            # Chunk count
            cursor = conn.execute("""
                SELECT COUNT(*) FROM embeddings WHERE project_id = ?
            """, (project_id,))
            chunk_count = cursor.fetchone()[0]
            
            # Token estimate
            cursor = conn.execute("""
                SELECT SUM(total_tokens_estimate) FROM file_index
                WHERE project_id = ?
            """, (project_id,))
            total_tokens = cursor.fetchone()[0] or 0
            
            # Chunk type distribution
            cursor = conn.execute("""
                SELECT chunk_type, COUNT(*) FROM embeddings
                WHERE project_id = ?
                GROUP BY chunk_type
            """, (project_id,))
            chunk_types = dict(cursor.fetchall())
            
            # Vector directory size
            project_dir = self.vectors_dir / project_id
            vector_size_bytes = 0
            if project_dir.exists():
                for f in project_dir.glob("*.npy"):
                    vector_size_bytes += f.stat().st_size
            
            return {
                "project_id": project_id,
                "file_count": file_count,
                "chunk_count": chunk_count,
                "total_tokens_estimate": total_tokens,
                "chunk_types": chunk_types,
                "vector_size_mb": round(vector_size_bytes / (1024 * 1024), 2),
                "embedding_dim": self.embedding_dim,
            }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_embedding_store(
    db_path: Union[str, Path] = "db/embeddings.db",
    vectors_dir: Union[str, Path] = "embeddings/",
    embedding_dim: int = 1536,
) -> EmbeddingStore:
    """Create and initialize an embedding store."""
    store = EmbeddingStore(db_path, vectors_dir, embedding_dim)
    store.init_db()
    return store
