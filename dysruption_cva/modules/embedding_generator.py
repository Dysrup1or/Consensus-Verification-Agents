"""
Dysruption CVA - Embedding Generator Module
Version: 1.0

Generates embeddings for code chunks using LiteLLM's unified API.
Supports multiple embedding providers with fallback chain.

Providers (in priority order):
1. OpenAI text-embedding-3-small (default, best quality/cost)
2. OpenAI text-embedding-ada-002 (fallback)
3. Cohere embed-v3 (free tier fallback)
4. Local sentence-transformers (offline fallback)

Usage:
    from modules.embedding_generator import EmbeddingGenerator, generate_embeddings
    
    generator = EmbeddingGenerator()
    embeddings = generator.embed_texts(["def hello(): pass", "class Foo: ..."])
    
    # Or batch embed with automatic rate limiting
    embeddings = generator.embed_batch(texts, batch_size=100)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from loguru import logger

# LiteLLM for unified embedding API
try:
    import litellm
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False
    logger.warning("LiteLLM not available for embeddings")

# Optional: local sentence-transformers for offline mode
try:
    from sentence_transformers import SentenceTransformer
    LOCAL_EMBEDDINGS_AVAILABLE = True
except ImportError:
    LOCAL_EMBEDDINGS_AVAILABLE = False


# =============================================================================
# CONSTANTS
# =============================================================================

# Default embedding model (OpenAI text-embedding-3-small)
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536

# Model configurations
EMBEDDING_MODELS = {
    "text-embedding-3-small": {
        "provider": "openai",
        "dimensions": 1536,
        "max_tokens": 8191,
        "cost_per_1m_tokens": 0.02,
    },
    "text-embedding-3-large": {
        "provider": "openai",
        "dimensions": 3072,
        "max_tokens": 8191,
        "cost_per_1m_tokens": 0.13,
    },
    "text-embedding-ada-002": {
        "provider": "openai",
        "dimensions": 1536,
        "max_tokens": 8191,
        "cost_per_1m_tokens": 0.10,
    },
    "embed-english-v3.0": {
        "provider": "cohere",
        "dimensions": 1024,
        "max_tokens": 512,
        "cost_per_1m_tokens": 0.10,
    },
    "all-MiniLM-L6-v2": {
        "provider": "local",
        "dimensions": 384,
        "max_tokens": 512,
        "cost_per_1m_tokens": 0.0,
    },
}

# Rate limiting
DEFAULT_BATCH_SIZE = 100
DEFAULT_REQUESTS_PER_MINUTE = 3000
RATE_LIMIT_DELAY = 0.1  # seconds between batches


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class EmbeddingResult:
    """Result of embedding a single text."""
    
    text: str
    embedding: np.ndarray
    model: str
    token_count: int
    
    @property
    def dimensions(self) -> int:
        return len(self.embedding)


@dataclass
class BatchEmbeddingResult:
    """Result of embedding a batch of texts."""
    
    embeddings: List[np.ndarray]
    model: str
    total_tokens: int
    elapsed_seconds: float
    failed_indices: List[int] = field(default_factory=list)
    
    @property
    def success_count(self) -> int:
        return len(self.embeddings) - len(self.failed_indices)
    
    @property
    def tokens_per_second(self) -> float:
        if self.elapsed_seconds > 0:
            return self.total_tokens / self.elapsed_seconds
        return 0.0


# =============================================================================
# EMBEDDING GENERATOR CLASS
# =============================================================================


class EmbeddingGenerator:
    """
    Generates embeddings using LiteLLM's unified API.
    
    Features:
    - Automatic provider fallback
    - Batch processing with rate limiting
    - Token counting and cost estimation
    - Local model fallback for offline use
    """
    
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        fallback_models: Optional[List[str]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize embedding generator.
        
        Args:
            model: Primary embedding model
            fallback_models: List of fallback models if primary fails
            batch_size: Texts per batch for API calls
            max_retries: Max retry attempts per batch
            retry_delay: Delay between retries (exponential backoff)
        """
        self.model = model
        self.fallback_models = fallback_models or [
            "text-embedding-ada-002",
            "all-MiniLM-L6-v2",
        ]
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Model info
        self.model_info = EMBEDDING_MODELS.get(model, {
            "provider": "openai",
            "dimensions": DEFAULT_DIMENSIONS,
            "max_tokens": 8191,
        })
        
        # Local model (lazy loaded)
        self._local_model: Optional[SentenceTransformer] = None
        
        # Statistics
        self.total_tokens_used = 0
        self.total_api_calls = 0
    
    @property
    def dimensions(self) -> int:
        """Get embedding dimensions for current model."""
        return self.model_info.get("dimensions", DEFAULT_DIMENSIONS)
    
    def _get_local_model(self) -> Optional[SentenceTransformer]:
        """Lazy load local sentence transformer model."""
        if self._local_model is None and LOCAL_EMBEDDINGS_AVAILABLE:
            try:
                self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded local embedding model: all-MiniLM-L6-v2")
            except Exception as e:
                logger.warning(f"Failed to load local model: {e}")
        return self._local_model
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (~4 chars per token)."""
        return len(text) // 4 + 1
    
    def _truncate_to_max_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within token limit."""
        estimated_tokens = self._estimate_tokens(text)
        if estimated_tokens <= max_tokens:
            return text
        
        # Truncate by character count (conservative)
        max_chars = max_tokens * 3  # ~3 chars per token to be safe
        return text[:max_chars]
    
    def embed_text(self, text: str) -> Optional[np.ndarray]:
        """
        Embed a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array, or None if failed
        """
        result = self.embed_texts([text])
        if result and len(result) > 0:
            return result[0]
        return None
    
    def embed_texts(
        self, 
        texts: List[str],
        model: Optional[str] = None,
    ) -> List[Optional[np.ndarray]]:
        """
        Embed multiple texts.
        
        Args:
            texts: List of texts to embed
            model: Override model (uses default if None)
            
        Returns:
            List of embedding vectors (None for failed texts)
        """
        if not texts:
            return []
        
        model = model or self.model
        model_info = EMBEDDING_MODELS.get(model, self.model_info)
        max_tokens = model_info.get("max_tokens", 8191)
        
        # Truncate texts to max tokens
        truncated_texts = [
            self._truncate_to_max_tokens(t, max_tokens) 
            for t in texts
        ]
        
        # Try primary model
        embeddings = self._call_embedding_api(truncated_texts, model)
        
        # If failed, try fallbacks
        if embeddings is None:
            for fallback in self.fallback_models:
                logger.info(f"Trying fallback model: {fallback}")
                embeddings = self._call_embedding_api(truncated_texts, fallback)
                if embeddings is not None:
                    break
        
        if embeddings is None:
            logger.error("All embedding models failed")
            return [None] * len(texts)
        
        return embeddings
    
    def _call_embedding_api(
        self, 
        texts: List[str], 
        model: str
    ) -> Optional[List[np.ndarray]]:
        """Call embedding API with retries."""
        model_info = EMBEDDING_MODELS.get(model, {})
        provider = model_info.get("provider", "openai")
        
        # Use local model if specified
        if provider == "local":
            return self._embed_local(texts)
        
        if not LITELLM_AVAILABLE:
            logger.warning("LiteLLM not available, trying local model")
            return self._embed_local(texts)
        
        for attempt in range(self.max_retries):
            try:
                # LiteLLM embedding call
                response = litellm.embedding(
                    model=model,
                    input=texts,
                )
                
                self.total_api_calls += 1
                
                # Extract embeddings from response
                embeddings = []
                for item in response.data:
                    embedding = np.array(item["embedding"], dtype=np.float32)
                    embeddings.append(embedding)
                
                # Track tokens
                if hasattr(response, "usage") and response.usage:
                    self.total_tokens_used += response.usage.get("total_tokens", 0)
                
                return embeddings
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check for rate limiting
                if "rate" in error_str or "limit" in error_str:
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limited, waiting {delay}s...")
                    time.sleep(delay)
                    continue
                
                # Check for API key issues
                if "api" in error_str and "key" in error_str:
                    logger.error(f"API key error for {model}: {e}")
                    return None
                
                # Other errors
                logger.warning(f"Embedding attempt {attempt+1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    def _embed_local(self, texts: List[str]) -> Optional[List[np.ndarray]]:
        """Embed texts using local sentence-transformers model."""
        local_model = self._get_local_model()
        if local_model is None:
            logger.error("Local embedding model not available")
            return None
        
        try:
            embeddings = local_model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return [emb.astype(np.float32) for emb in embeddings]
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            return None
    
    def embed_batch(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        show_progress: bool = True,
    ) -> BatchEmbeddingResult:
        """
        Embed texts in batches with rate limiting.
        
        Args:
            texts: List of texts to embed
            batch_size: Override batch size
            show_progress: Log progress
            
        Returns:
            BatchEmbeddingResult with all embeddings
        """
        batch_size = batch_size or self.batch_size
        total = len(texts)
        
        all_embeddings: List[np.ndarray] = []
        failed_indices: List[int] = []
        total_tokens = 0
        
        start_time = time.time()
        
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            batch_start = i
            
            if show_progress and i > 0:
                progress = (i / total) * 100
                logger.info(f"Embedding progress: {progress:.1f}% ({i}/{total})")
            
            # Embed batch
            batch_embeddings = self.embed_texts(batch)
            
            # Track results
            for j, emb in enumerate(batch_embeddings):
                if emb is not None:
                    all_embeddings.append(emb)
                    total_tokens += self._estimate_tokens(batch[j])
                else:
                    failed_indices.append(batch_start + j)
                    # Add zero vector as placeholder
                    all_embeddings.append(np.zeros(self.dimensions, dtype=np.float32))
            
            # Rate limiting
            if i + batch_size < total:
                time.sleep(RATE_LIMIT_DELAY)
        
        elapsed = time.time() - start_time
        
        if show_progress:
            logger.info(
                f"Embedding complete: {total - len(failed_indices)}/{total} texts, "
                f"{total_tokens} tokens, {elapsed:.1f}s"
            )
        
        return BatchEmbeddingResult(
            embeddings=all_embeddings,
            model=self.model,
            total_tokens=total_tokens,
            elapsed_seconds=elapsed,
            failed_indices=failed_indices,
        )
    
    def estimate_cost(self, texts: List[str]) -> Dict[str, float]:
        """Estimate embedding cost for texts."""
        total_tokens = sum(self._estimate_tokens(t) for t in texts)
        cost_per_1m = self.model_info.get("cost_per_1m_tokens", 0.02)
        estimated_cost = (total_tokens / 1_000_000) * cost_per_1m
        
        return {
            "total_tokens": total_tokens,
            "cost_per_1m_tokens": cost_per_1m,
            "estimated_cost_usd": round(estimated_cost, 4),
            "model": self.model,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        cost_per_1m = self.model_info.get("cost_per_1m_tokens", 0.02)
        estimated_cost = (self.total_tokens_used / 1_000_000) * cost_per_1m
        
        return {
            "model": self.model,
            "dimensions": self.dimensions,
            "total_tokens_used": self.total_tokens_used,
            "total_api_calls": self.total_api_calls,
            "estimated_cost_usd": round(estimated_cost, 4),
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def generate_embeddings(
    texts: List[str],
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> List[np.ndarray]:
    """
    Generate embeddings for a list of texts.
    
    Args:
        texts: List of texts to embed
        model: Embedding model to use
        batch_size: Batch size for API calls
        
    Returns:
        List of embedding vectors
    """
    generator = EmbeddingGenerator(model=model, batch_size=batch_size)
    result = generator.embed_batch(texts, show_progress=True)
    return result.embeddings


def embed_single(text: str, model: str = DEFAULT_MODEL) -> Optional[np.ndarray]:
    """Embed a single text."""
    generator = EmbeddingGenerator(model=model)
    return generator.embed_text(text)


def get_embedding_dimensions(model: str = DEFAULT_MODEL) -> int:
    """Get embedding dimensions for a model."""
    return EMBEDDING_MODELS.get(model, {}).get("dimensions", DEFAULT_DIMENSIONS)
