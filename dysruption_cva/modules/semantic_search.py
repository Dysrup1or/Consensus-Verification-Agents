"""
Dysruption CVA - Semantic Search Module
Version: 1.0

Implements semantic search over code embeddings using cosine similarity.
Provides both chunk-level and file-level search with aggregation.

Features:
- Cosine similarity search
- Top-K retrieval with threshold filtering
- File-level aggregation from chunk results
- Query expansion for better recall
- Caching for repeated queries

Usage:
    from modules.semantic_search import SemanticSearch
    
    search = SemanticSearch(embedding_store, embedding_generator)
    
    # Search for relevant files
    results = search.search_files(
        project_id="my_project",
        query="consensus voting mechanism",
        top_k=10
    )
    
    # Search at chunk level
    chunk_results = search.search_chunks(
        project_id="my_project", 
        query="def evaluate_criterion",
        top_k=20
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np
from loguru import logger

from .embedding_store import EmbeddingStore, EmbeddingRow, SearchResult, FileSearchResult
from .embedding_generator import EmbeddingGenerator


# =============================================================================
# CONSTANTS
# =============================================================================

# Default search parameters
DEFAULT_TOP_K = 10
DEFAULT_SIMILARITY_THRESHOLD = 0.3  # Minimum cosine similarity
DEFAULT_FILE_AGGREGATION = "max"  # 'max', 'avg', or 'sum'

# Query expansion
ENABLE_QUERY_EXPANSION = True
QUERY_EXPANSION_WEIGHT = 0.3


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SearchConfig:
    """Configuration for semantic search."""
    
    top_k: int = DEFAULT_TOP_K
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    aggregation_method: str = DEFAULT_FILE_AGGREGATION
    enable_query_expansion: bool = ENABLE_QUERY_EXPANSION
    query_expansion_weight: float = QUERY_EXPANSION_WEIGHT
    
    # File filtering
    include_extensions: Optional[Set[str]] = None
    exclude_extensions: Optional[Set[str]] = None
    exclude_paths: Optional[Set[str]] = None


@dataclass
class ChunkSearchResult:
    """Search result at chunk level."""
    
    file_path: str
    chunk_id: int
    chunk_type: str
    chunk_text_preview: str
    similarity_score: float
    start_line: int
    end_line: int


@dataclass 
class FileSearchResult:
    """Search result aggregated to file level."""
    
    file_path: str
    max_similarity: float
    avg_similarity: float
    matching_chunks: int
    total_chunks: int
    chunk_previews: List[str] = field(default_factory=list)
    
    @property
    def relevance_score(self) -> float:
        """Combined relevance score."""
        # Weight max similarity higher than coverage
        coverage = self.matching_chunks / max(self.total_chunks, 1)
        return 0.7 * self.max_similarity + 0.3 * coverage


@dataclass
class SearchResults:
    """Complete search results with metadata."""
    
    query: str
    file_results: List[FileSearchResult] = field(default_factory=list)
    chunk_results: List[ChunkSearchResult] = field(default_factory=list)
    total_chunks_searched: int = 0
    elapsed_seconds: float = 0.0
    model_used: str = ""


# =============================================================================
# SEMANTIC SEARCH CLASS
# =============================================================================


class SemanticSearch:
    """
    Semantic search over code embeddings.
    
    Uses cosine similarity to find relevant code chunks and files
    based on natural language queries or code snippets.
    """
    
    def __init__(
        self,
        embedding_store: EmbeddingStore,
        embedding_generator: EmbeddingGenerator,
        config: Optional[SearchConfig] = None,
    ):
        """
        Initialize semantic search.
        
        Args:
            embedding_store: Store containing code embeddings
            embedding_generator: Generator for query embeddings
            config: Search configuration
        """
        self.store = embedding_store
        self.generator = embedding_generator
        self.config = config or SearchConfig()
        
        # Cache for query embeddings
        self._query_cache: Dict[str, np.ndarray] = {}
        
        # Cache for loaded embeddings
        self._embeddings_cache: Dict[str, List[Tuple[EmbeddingRow, np.ndarray]]] = {}
    
    def _get_query_embedding(self, query: str) -> Optional[np.ndarray]:
        """Get embedding for query string (with caching)."""
        if query in self._query_cache:
            return self._query_cache[query]
        
        embedding = self.generator.embed_text(query)
        if embedding is not None:
            self._query_cache[query] = embedding
        
        return embedding
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def _load_project_embeddings(
        self, 
        project_id: str
    ) -> List[Tuple[EmbeddingRow, np.ndarray]]:
        """Load all embeddings for a project (with caching)."""
        if project_id in self._embeddings_cache:
            return self._embeddings_cache[project_id]
        
        embeddings = self.store.get_all_embeddings(project_id)
        self._embeddings_cache[project_id] = embeddings
        return embeddings
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._query_cache.clear()
        self._embeddings_cache.clear()
    
    def _should_include_file(self, file_path: str) -> bool:
        """Check if file should be included based on config filters."""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        # Check extension filters
        if self.config.include_extensions:
            if ext not in self.config.include_extensions:
                return False
        
        if self.config.exclude_extensions:
            if ext in self.config.exclude_extensions:
                return False
        
        # Check path exclusions
        if self.config.exclude_paths:
            for exclude in self.config.exclude_paths:
                if exclude in file_path:
                    return False
        
        return True
    
    def search_chunks(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> List[ChunkSearchResult]:
        """
        Search for relevant code chunks.
        
        Args:
            project_id: Project to search
            query: Search query (natural language or code)
            top_k: Maximum results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of ChunkSearchResult sorted by similarity
        """
        top_k = top_k or self.config.top_k
        threshold = similarity_threshold or self.config.similarity_threshold
        
        # Get query embedding
        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            logger.error("Failed to generate query embedding")
            return []
        
        # Load project embeddings
        embeddings = self._load_project_embeddings(project_id)
        if not embeddings:
            logger.warning(f"No embeddings found for project: {project_id}")
            return []
        
        # Calculate similarities
        results: List[Tuple[float, EmbeddingRow]] = []
        
        for meta, vector in embeddings:
            # Check file filters
            if not self._should_include_file(meta.file_path):
                continue
            
            similarity = self._cosine_similarity(query_embedding, vector)
            
            if similarity >= threshold:
                results.append((similarity, meta))
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Take top K
        results = results[:top_k]
        
        # Convert to ChunkSearchResult
        chunk_results = []
        for similarity, meta in results:
            chunk_results.append(ChunkSearchResult(
                file_path=meta.file_path,
                chunk_id=meta.chunk_id,
                chunk_type=meta.chunk_type,
                chunk_text_preview=meta.chunk_text_preview,
                similarity_score=similarity,
                start_line=meta.chunk_start_line,
                end_line=meta.chunk_end_line,
            ))
        
        return chunk_results
    
    def search_files(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        aggregation_method: Optional[str] = None,
    ) -> List[FileSearchResult]:
        """
        Search for relevant files (aggregated from chunk results).
        
        Args:
            project_id: Project to search
            query: Search query
            top_k: Maximum files to return
            similarity_threshold: Minimum similarity score
            aggregation_method: How to aggregate chunk scores ('max', 'avg', 'sum')
            
        Returns:
            List of FileSearchResult sorted by relevance
        """
        top_k = top_k or self.config.top_k
        threshold = similarity_threshold or self.config.similarity_threshold
        aggregation = aggregation_method or self.config.aggregation_method
        
        # Get query embedding
        query_embedding = self._get_query_embedding(query)
        if query_embedding is None:
            logger.error("Failed to generate query embedding")
            return []
        
        # Load project embeddings
        embeddings = self._load_project_embeddings(project_id)
        if not embeddings:
            logger.warning(f"No embeddings found for project: {project_id}")
            return []
        
        # Aggregate by file
        file_scores: Dict[str, List[Tuple[float, str]]] = {}  # file -> [(score, preview), ...]
        file_chunk_counts: Dict[str, int] = {}
        
        for meta, vector in embeddings:
            # Check file filters
            if not self._should_include_file(meta.file_path):
                continue
            
            similarity = self._cosine_similarity(query_embedding, vector)
            
            if meta.file_path not in file_scores:
                file_scores[meta.file_path] = []
                file_chunk_counts[meta.file_path] = 0
            
            file_chunk_counts[meta.file_path] += 1
            
            if similarity >= threshold:
                file_scores[meta.file_path].append((similarity, meta.chunk_text_preview))
        
        # Calculate aggregated scores
        file_results: List[FileSearchResult] = []
        
        for file_path, scores in file_scores.items():
            if not scores:
                continue
            
            similarities = [s[0] for s in scores]
            previews = [s[1] for s in scores[:3]]  # Top 3 previews
            
            max_sim = max(similarities)
            avg_sim = sum(similarities) / len(similarities)
            
            file_results.append(FileSearchResult(
                file_path=file_path,
                max_similarity=max_sim,
                avg_similarity=avg_sim,
                matching_chunks=len(scores),
                total_chunks=file_chunk_counts[file_path],
                chunk_previews=previews,
            ))
        
        # Sort by aggregation method
        if aggregation == "max":
            file_results.sort(key=lambda x: x.max_similarity, reverse=True)
        elif aggregation == "avg":
            file_results.sort(key=lambda x: x.avg_similarity, reverse=True)
        elif aggregation == "sum":
            file_results.sort(key=lambda x: x.max_similarity * x.matching_chunks, reverse=True)
        else:
            file_results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return file_results[:top_k]
    
    def search(
        self,
        project_id: str,
        query: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        include_chunks: bool = True,
    ) -> SearchResults:
        """
        Full search returning both file and chunk results.
        
        Args:
            project_id: Project to search
            query: Search query
            top_k: Maximum results
            similarity_threshold: Minimum similarity
            include_chunks: Whether to include chunk-level results
            
        Returns:
            SearchResults with files and optionally chunks
        """
        start_time = time.time()
        
        top_k = top_k or self.config.top_k
        
        # File-level search
        file_results = self.search_files(
            project_id=project_id,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        
        # Chunk-level search (optional)
        chunk_results = []
        if include_chunks:
            chunk_results = self.search_chunks(
                project_id=project_id,
                query=query,
                top_k=top_k * 2,  # More chunks than files
                similarity_threshold=similarity_threshold,
            )
        
        # Get total chunks searched
        embeddings = self._load_project_embeddings(project_id)
        
        elapsed = time.time() - start_time
        
        return SearchResults(
            query=query,
            file_results=file_results,
            chunk_results=chunk_results,
            total_chunks_searched=len(embeddings),
            elapsed_seconds=elapsed,
            model_used=self.generator.model,
        )
    
    def multi_query_search(
        self,
        project_id: str,
        queries: List[str],
        top_k: Optional[int] = None,
        merge_method: str = "union",  # 'union' or 'intersection'
    ) -> List[FileSearchResult]:
        """
        Search with multiple queries and merge results.
        
        Useful for matching multiple spec requirements to files.
        
        Args:
            project_id: Project to search
            queries: List of search queries
            top_k: Maximum files to return
            merge_method: How to merge results
            
        Returns:
            Merged list of FileSearchResult
        """
        top_k = top_k or self.config.top_k
        
        if not queries:
            return []
        
        # Search for each query
        all_results: Dict[str, List[FileSearchResult]] = {}
        
        for query in queries:
            results = self.search_files(
                project_id=project_id,
                query=query,
                top_k=top_k * 2,  # Get more to allow filtering
            )
            
            for result in results:
                if result.file_path not in all_results:
                    all_results[result.file_path] = []
                all_results[result.file_path].append(result)
        
        # Merge based on method
        merged: List[FileSearchResult] = []
        
        for file_path, results in all_results.items():
            if merge_method == "intersection":
                # File must match all queries
                if len(results) < len(queries):
                    continue
            
            # Aggregate scores across queries
            max_sim = max(r.max_similarity for r in results)
            avg_sim = sum(r.avg_similarity for r in results) / len(results)
            total_matching = sum(r.matching_chunks for r in results)
            total_chunks = results[0].total_chunks  # Same for all
            
            merged.append(FileSearchResult(
                file_path=file_path,
                max_similarity=max_sim,
                avg_similarity=avg_sim,
                matching_chunks=total_matching,
                total_chunks=total_chunks,
                chunk_previews=results[0].chunk_previews,
            ))
        
        # Sort by relevance
        merged.sort(key=lambda x: x.relevance_score, reverse=True)
        
        return merged[:top_k]


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_semantic_search(
    db_path: str = "db/embeddings.db",
    vectors_dir: str = "embeddings/",
    embedding_model: str = "text-embedding-3-small",
) -> SemanticSearch:
    """Create a semantic search instance with default configuration."""
    from .embedding_store import EmbeddingStore
    from .embedding_generator import EmbeddingGenerator
    
    store = EmbeddingStore(db_path, vectors_dir)
    store.init_db()
    
    generator = EmbeddingGenerator(model=embedding_model)
    
    return SemanticSearch(store, generator)


def search_files_for_spec(
    project_id: str,
    spec_content: str,
    top_k: int = 20,
    db_path: str = "db/embeddings.db",
) -> List[FileSearchResult]:
    """
    Search for files relevant to a spec document.
    
    Extracts key requirements from spec and searches for matching files.
    
    Args:
        project_id: Project to search
        spec_content: Content of spec.txt
        top_k: Maximum files to return
        db_path: Path to embedding database
        
    Returns:
        List of relevant files sorted by relevance
    """
    search = create_semantic_search(db_path=db_path)
    
    # Extract queries from spec (simple line-based for now)
    lines = spec_content.strip().split("\n")
    queries = [
        line.strip() 
        for line in lines 
        if line.strip() and not line.startswith("#") and len(line) > 20
    ][:10]  # Limit to 10 queries
    
    if not queries:
        # Fall back to full spec as single query
        return search.search_files(project_id, spec_content[:2000], top_k=top_k)
    
    return search.multi_query_search(
        project_id=project_id,
        queries=queries,
        top_k=top_k,
        merge_method="union",
    )
