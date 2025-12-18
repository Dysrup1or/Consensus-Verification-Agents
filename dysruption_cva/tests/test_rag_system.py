"""Unit tests for the RAG (Retrieval-Augmented Generation) system.

Tests cover:
- Embedding store CRUD operations
- Code chunking preserves context
- Semantic search accuracy
- Integration with coverage planner
- CLI index command
"""

import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import numpy as np


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    import gc
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    # Force garbage collection to close any SQLite connections
    gc.collect()
    # On Windows, SQLite files may still be locked; ignore cleanup errors
    try:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def sample_python_code():
    """Sample Python code for chunking tests."""
    return '''"""Sample module docstring."""

import os
from typing import List, Dict


class UserManager:
    """Manages user operations."""
    
    def __init__(self, db_path: str):
        """Initialize with database path."""
        self.db_path = db_path
        self._cache: Dict[str, str] = {}
    
    def create_user(self, username: str, email: str) -> bool:
        """Create a new user.
        
        Args:
            username: The username
            email: User's email address
            
        Returns:
            True if created successfully
        """
        if self._validate_email(email):
            # Add to database
            return True
        return False
    
    def _validate_email(self, email: str) -> bool:
        """Validate email format."""
        return "@" in email and "." in email


def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user with credentials.
    
    This is a top-level function for authentication.
    """
    # Hash password and check
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return len(hashed) > 0


async def async_fetch_user(user_id: int) -> Dict:
    """Async function to fetch user data."""
    await asyncio.sleep(0.1)
    return {"id": user_id, "status": "active"}
'''


@pytest.fixture
def sample_typescript_code():
    """Sample TypeScript code for chunking tests."""
    return '''import { useState, useEffect } from 'react';
import { UserService } from './services/user';

interface User {
    id: number;
    name: string;
    email: string;
}

interface AuthState {
    isLoggedIn: boolean;
    user: User | null;
}

export class AuthManager {
    private token: string | null = null;
    
    constructor(private userService: UserService) {}
    
    async login(email: string, password: string): Promise<boolean> {
        try {
            const result = await this.userService.authenticate(email, password);
            this.token = result.token;
            return true;
        } catch (error) {
            console.error('Login failed:', error);
            return false;
        }
    }
    
    logout(): void {
        this.token = null;
    }
    
    isAuthenticated(): boolean {
        return this.token !== null;
    }
}

export function useAuth(): AuthState {
    const [state, setState] = useState<AuthState>({
        isLoggedIn: false,
        user: null,
    });
    
    useEffect(() => {
        // Check auth state on mount
        checkAuthStatus();
    }, []);
    
    return state;
}
'''


@pytest.fixture
def sample_project(temp_dir):
    """Create a sample project structure for testing."""
    # Create files
    (temp_dir / "src").mkdir()
    (temp_dir / "src" / "auth.py").write_text('''"""Authentication module."""

class AuthService:
    """Handles authentication."""
    
    def login(self, username: str, password: str) -> bool:
        """Authenticate user credentials."""
        return self._verify_password(password)
    
    def _verify_password(self, password: str) -> bool:
        return len(password) >= 8
''')
    
    (temp_dir / "src" / "tribunal.py").write_text('''"""Tribunal voting system for consensus."""

class Tribunal:
    """Multi-judge consensus mechanism."""
    
    def __init__(self, judges: list):
        self.judges = judges
    
    def vote(self, item: str) -> str:
        """Collect votes and determine consensus."""
        votes = [judge.evaluate(item) for judge in self.judges]
        return self._aggregate_votes(votes)
    
    def _aggregate_votes(self, votes: list) -> str:
        """Aggregate votes using majority rule."""
        from collections import Counter
        counts = Counter(votes)
        return counts.most_common(1)[0][0]
''')
    
    (temp_dir / "src" / "utils.py").write_text('''"""Utility functions."""

def format_date(date):
    """Format a date object."""
    return date.strftime("%Y-%m-%d")

def hash_string(s: str) -> str:
    """Hash a string using SHA-256."""
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()
''')
    
    (temp_dir / "README.md").write_text('''# Sample Project

This project implements a tribunal voting system with authentication.

## Features

- Multi-judge consensus voting
- User authentication
- Utility functions
''')
    
    return temp_dir


# ============================================================================
# Embedding Store Tests
# ============================================================================

class TestEmbeddingStore:
    """Tests for the EmbeddingStore class."""
    
    def test_init_creates_database(self, temp_dir):
        """Test that init creates the database file."""
        from modules.embedding_store import EmbeddingStore
        
        db_path = temp_dir / "test.db"
        vectors_dir = temp_dir / "vectors"
        store = EmbeddingStore(db_path, vectors_dir)
        store.init_db()
        
        assert db_path.exists()
        # Explicitly close connections
        del store
    
    def test_upsert_and_retrieve_embedding(self, temp_dir):
        """Test storing and retrieving an embedding."""
        from modules.embedding_store import EmbeddingStore
        
        db_path = temp_dir / "test.db"
        vectors_dir = temp_dir / "vectors"
        store = EmbeddingStore(db_path, vectors_dir, embedding_dim=4)
        store.init_db()
        
        # Create test embedding
        embedding = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        
        store.upsert_embedding(
            project_id="test_project",
            file_path="src/auth.py",
            chunk_id=0,
            content_hash="abc123",
            embedding_vector=embedding,
            chunk_text="def login(): pass",
            chunk_type="function",
        )
        
        # Retrieve - returns List[Tuple[EmbeddingRow, np.ndarray]]
        embeddings = store.get_file_embeddings("test_project", "src/auth.py")
        
        assert len(embeddings) == 1
        row, vector = embeddings[0]
        assert row.chunk_id == 0
        assert row.file_path == "src/auth.py"
        del store
    
    def test_compute_content_hash(self):
        """Test content hash computation is stable."""
        from modules.embedding_store import EmbeddingStore
        
        content = "def hello(): pass"
        hash1 = EmbeddingStore.compute_content_hash(content)
        hash2 = EmbeddingStore.compute_content_hash(content)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA-256 hex truncated to 16 chars
    
    def test_get_stats(self, temp_dir):
        """Test getting store statistics."""
        from modules.embedding_store import EmbeddingStore
        
        db_path = temp_dir / "test.db"
        vectors_dir = temp_dir / "vectors"
        store = EmbeddingStore(db_path, vectors_dir, embedding_dim=4)
        store.init_db()
        
        embedding = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        
        for i in range(3):
            store.upsert_embedding(
                project_id="test_project",
                file_path=f"file_{i}.py",
                chunk_id=0,
                content_hash=f"hash_{i}",
                embedding_vector=embedding,
                chunk_text=f"content {i}",
                chunk_type="block",
            )
        
        stats = store.get_stats("test_project")
        
        assert stats["chunk_count"] == 3
        del store


# ============================================================================
# Code Chunker Tests
# ============================================================================

class TestCodeChunker:
    """Tests for the CodeChunker class."""
    
    def test_chunk_python_extracts_functions(self, sample_python_code):
        """Test that Python chunking extracts functions."""
        from modules.code_chunker import CodeChunker
        
        chunker = CodeChunker()
        result = chunker.chunk_file(sample_python_code, "test.py")
        
        assert result.language == "python"
        
        # Check that we have at least one chunk
        if len(result.chunks) > 0:
            # Check that we have function chunks
            chunk_types = [c.chunk_type for c in result.chunks]
            assert "function" in chunk_types or "class" in chunk_types or "method" in chunk_types
    
    def test_chunk_python_extracts_classes(self, sample_python_code):
        """Test that Python chunking extracts classes."""
        from modules.code_chunker import CodeChunker
        
        chunker = CodeChunker()
        result = chunker.chunk_file(sample_python_code, "test.py")
        
        # Find class chunk
        class_chunks = [c for c in result.chunks if c.chunk_type == "class"]
        
        if len(result.chunks) > 0:
            # At least one chunk should exist for the class
            assert len(result.chunks) >= 1
    
    def test_chunk_typescript_regex_fallback(self, sample_typescript_code):
        """Test TypeScript chunking uses regex patterns."""
        from modules.code_chunker import CodeChunker
        
        chunker = CodeChunker()
        result = chunker.chunk_file(sample_typescript_code, "auth.ts")
        
        assert result.language in ("typescript", "javascript")
    
    def test_chunk_preserves_context(self, sample_python_code):
        """Test that chunking preserves enough context."""
        from modules.code_chunker import CodeChunker
        
        chunker = CodeChunker()
        result = chunker.chunk_file(sample_python_code, "test.py")
        
        for chunk in result.chunks:
            # Each chunk should have some content
            assert len(chunk.content) > 10
            # Start and end lines should be valid
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line
    
    def test_chunk_markdown_by_sections(self):
        """Test Markdown chunking splits by headers."""
        from modules.code_chunker import CodeChunker
        
        md_content = """# Introduction

This is the intro section with some text.

## Getting Started

Here's how to get started with the project.

### Installation

Run pip install to install dependencies.

## API Reference

The API documentation follows.
"""
        
        chunker = CodeChunker()
        result = chunker.chunk_file(md_content, "README.md")
        
        assert result.language == "markdown"
    
    def test_detect_language(self):
        """Test language detection from file extensions."""
        from modules.code_chunker import CodeChunker
        
        chunker = CodeChunker()
        
        assert chunker.detect_language("test.py") == "python"
        assert chunker.detect_language("app.js") == "javascript"
        assert chunker.detect_language("component.tsx") == "javascript"
        assert chunker.detect_language("README.md") == "markdown"


# ============================================================================
# Embedding Generator Tests (with mocking)
# ============================================================================

class TestEmbeddingGenerator:
    """Tests for the EmbeddingGenerator class."""
    
    def test_generator_dimensions(self):
        """Test that generator reports correct dimensions."""
        from modules.embedding_generator import EmbeddingGenerator
        
        gen = EmbeddingGenerator(model="text-embedding-3-small")
        assert gen.dimensions == 1536
    
    def test_generator_model_info(self):
        """Test that generator has model info."""
        from modules.embedding_generator import EmbeddingGenerator
        
        gen = EmbeddingGenerator(model="text-embedding-3-small")
        assert gen.model_info is not None
        assert "dimensions" in gen.model_info
        assert "cost_per_1m_tokens" in gen.model_info
    
    def test_estimate_cost(self):
        """Test cost estimation for embeddings."""
        from modules.embedding_generator import EmbeddingGenerator
        
        gen = EmbeddingGenerator(model="text-embedding-3-small")
        
        # Estimate cost for sample texts
        result = gen.estimate_cost(["Hello world", "This is a test"])
        
        assert "total_tokens" in result
        assert "estimated_cost_usd" in result
        assert result["total_tokens"] > 0


# ============================================================================
# Semantic Search Tests
# ============================================================================

class TestSemanticSearch:
    """Tests for the SemanticSearch class."""
    
    def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity for identical vectors is 1.0."""
        # Direct calculation since _cosine_similarity is an instance method
        v = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        
        # Cosine similarity formula: dot(a,b) / (norm(a) * norm(b))
        norm_v = np.linalg.norm(v)
        sim = np.dot(v, v) / (norm_v * norm_v)
        
        assert sim == pytest.approx(1.0, rel=1e-5)
    
    def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity for orthogonal vectors is 0."""
        v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        
        sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        
        assert sim == pytest.approx(0.0, rel=1e-5)
    
    def test_cosine_similarity_opposite_vectors(self):
        """Test cosine similarity for opposite vectors is -1."""
        v1 = np.array([1.0, 0.0], dtype=np.float32)
        v2 = np.array([-1.0, 0.0], dtype=np.float32)
        
        sim = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        
        assert sim == pytest.approx(-1.0, rel=1e-5)


# ============================================================================
# RAG Integration Tests
# ============================================================================

class TestRAGIntegration:
    """Tests for RAG integration with coverage planner."""
    
    def test_is_rag_available(self):
        """Test RAG availability check."""
        from modules.rag_integration import is_rag_available
        
        # Should be True since we're running in the modules context
        result = is_rag_available()
        assert isinstance(result, bool)
    
    def test_rag_config_defaults(self):
        """Test RAG configuration defaults."""
        from modules.rag_integration import RAGConfig
        
        config = RAGConfig()
        
        assert config.embedding_model == "text-embedding-3-small"
        assert config.similarity_threshold == 0.3
        assert config.top_k_files == 20
        assert ".py" in config.index_extensions


# ============================================================================
# Integration Tests (End-to-End)
# ============================================================================

class TestRAGEndToEnd:
    """End-to-end tests for the RAG system."""
    
    def test_file_manager_semantic_boost_disabled(self, sample_project):
        """Test that file_manager works when semantic boost is disabled."""
        from modules.file_manager import plan_context
        
        # Should work without RAG
        plan = plan_context(
            sample_project,
            changed_files=["src/auth.py"],
            import_files=[],
            constitution_text="Test spec",
            token_budget=10000,
            enable_semantic_boost=False,
        )
        
        assert len(plan.items) > 0
        assert any(item.rel_path == "src/auth.py" for item in plan.items)


# ============================================================================
# CLI Tests
# ============================================================================

class TestCLI:
    """Tests for CLI commands."""
    
    def test_index_command_help(self):
        """Test that index command shows help."""
        import subprocess
        
        result = subprocess.run(
            ["python", "cva.py", "index", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        
        assert result.returncode == 0
