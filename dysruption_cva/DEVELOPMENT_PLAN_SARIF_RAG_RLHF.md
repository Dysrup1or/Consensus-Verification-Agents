# CVA Enhancement Development Plan
## Phase 1-3: SARIF Export, Semantic Embeddings, RLHF-Lite

**Document Version**: 1.2
**Created**: 2025-12-16
**Updated**: 2025-12-16
**Author**: CVA Development Team
**Status**: Phase 1-2 COMPLETE ✅ | Phase 3 Pending

---

## Progress Summary

| Phase | Enhancement | Status | Completion Date |
|-------|-------------|--------|-----------------|
| 1 | SARIF Export | ✅ **COMPLETE** | 2025-12-16 |
| 2 | Semantic Code Embeddings (RAG) | ✅ **COMPLETE** | 2025-12-16 |
| 3 | Iterative Judge Refinement (RLHF-Lite) | 🔜 Pending | - |

### Phase 1 Deliverables ✅
- [x] `modules/sarif_export.py` - Full SARIF 2.1.0 exporter (613 lines)
- [x] `tests/test_sarif_export.py` - 42 passing tests
- [x] Tribunal integration - `save_outputs()` generates verdict.sarif
- [x] Config support - `config.yaml` sarif_enabled option
- [x] Documentation - `docs/GITHUB_ACTIONS_SARIF.md`

### Phase 2 Deliverables ✅
- [x] `modules/embedding_store.py` - SQLite + numpy vector storage (623 lines)
- [x] `modules/code_chunker.py` - AST-based Python/JS chunking (600 lines)
- [x] `modules/embedding_generator.py` - LiteLLM embedding with fallback (493 lines)
- [x] `modules/semantic_search.py` - Cosine similarity search (400+ lines)
- [x] `modules/rag_integration.py` - Coverage planner integration (600+ lines)
- [x] `tests/test_rag_system.py` - 20 passing tests
- [x] CLI command - `cva index --dir .` for embedding generation
- [x] File manager integration - semantic boost in `plan_context()`

---

## Executive Summary

This document provides a comprehensive, sequential development plan for three major CVA enhancements:

| Phase | Enhancement | Impact | Estimated Effort |
|-------|-------------|--------|------------------|
| 1 | SARIF Export | Native GitHub Code Scanning integration | 1 day |
| 2 | Semantic Code Embeddings (RAG) | 10x file selection accuracy | 3 days |
| 3 | Iterative Judge Refinement (RLHF-Lite) | 5x false positive reduction | 1-2 weeks |

**Dependency Order**: Phase 1 → Phase 2 → Phase 3 (sequential, each builds on previous)

---

## Phase 1: SARIF Export

### 1.1 Overview

**SARIF** (Static Analysis Results Interchange Format) is an OASIS standard for static analysis output. GitHub Code Scanning natively consumes SARIF files to display findings inline in PRs and the Security tab.

**Goal**: Export CVA verdicts in SARIF 2.1.0 format for seamless GitHub integration.

### 1.2 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Current Output Flow                       │
├─────────────────────────────────────────────────────────────┤
│  TribunalVerdict → generate_verdict_json() → verdict.json   │
│                  → generate_report_md()   → REPORT.md       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Enhanced Output Flow                      │
├─────────────────────────────────────────────────────────────┤
│  TribunalVerdict → generate_verdict_json() → verdict.json   │
│                  → generate_report_md()   → REPORT.md       │
│                  → generate_sarif()       → verdict.sarif   │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 SARIF Schema Requirements (2.1.0)

```json
{
  "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "Dysruption CVA",
        "version": "1.2",
        "informationUri": "https://github.com/dysruption/cva",
        "rules": [/* Rule definitions */]
      }
    },
    "results": [/* Finding instances */]
  }]
}
```

### 1.4 Task Breakdown

#### Task 1.4.1: Create SARIF Schema Models ✅
**File**: `modules/sarif_export.py`
**Objective**: Define Pydantic models for SARIF 2.1.0 schema
**Verification**: 
- [x] All required SARIF fields modeled
- [x] Passes jsonschema validation against SARIF 2.1.0

#### Task 1.4.2: Implement SARIF Generator ✅
**File**: `modules/sarif_export.py`
**Objective**: Convert TribunalVerdict to SARIF format
**Verification**:
- [x] Generates valid SARIF JSON
- [x] Maps severity correctly (security→error, functionality→warning, style→note)
- [x] Includes file/line information where available

#### Task 1.4.3: Integrate with Tribunal save_outputs() ✅
**File**: `modules/tribunal.py`
**Objective**: Add SARIF export to existing output pipeline
**Verification**:
- [x] `verdict.sarif` generated alongside `verdict.json`
- [x] Config option to enable/disable SARIF export

#### Task 1.4.4: Add Unit Tests ✅
**File**: `tests/test_sarif_export.py`
**Objective**: Comprehensive test coverage (42 tests)
**Verification**:
- [x] Test SARIF schema compliance
- [x] Test severity mapping
- [x] Test file/line annotation

#### Task 1.4.5: GitHub Actions Integration Example ✅
**File**: `docs/GITHUB_ACTIONS_SARIF.md`
**Objective**: Document GitHub workflow integration
**Verification**:
- [x] Working example workflow YAML
- [x] Complete production workflow example
- [x] Troubleshooting guide

---

## Phase 1 Complete Summary 🎉

Phase 1 (SARIF Export) has been successfully implemented with:

1. **Core Module** (`modules/sarif_export.py`):
   - Full Pydantic models for SARIF 2.1.0 schema
   - `SarifExporter` class with tribunal dataclass compatibility
   - Mapping functions for criterion types, verdicts, and scores
   - Convenience functions: `generate_sarif()`, `save_sarif()`, `validate_sarif()`

2. **Integration** (`modules/tribunal.py`):
   - `save_outputs()` now generates `verdict.sarif` alongside `verdict.json`
   - Graceful fallback if SARIF module unavailable

3. **Configuration** (`config.yaml`):
   - `sarif_enabled: true/false`
   - `sarif_file: "verdict.sarif"`

4. **Tests** (`tests/test_sarif_export.py`):
   - 42 tests covering all components
   - 100% pass rate

5. **Documentation** (`docs/GITHUB_ACTIONS_SARIF.md`):
   - Quick start guide
   - Complete production workflow
   - Troubleshooting section

---

## Phase 2: Semantic Code Embeddings (RAG)

### 2.1 Overview

**Problem**: The current coverage planner uses structural signals (git frequency, import count) but doesn't semantically match spec requirements to code content. This caused `tribunal.py` to be excluded when testing tribunal-related requirements.

**Solution**: Pre-compute embeddings for all code files and use semantic search to find spec-relevant files.

### 2.2 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Embedding Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│  1. Index Phase (offline, once per project)                 │
│     project_root → scan files → chunk code → embed → store  │
│                                                              │
│  2. Query Phase (per verification run)                       │
│     spec.txt → extract criteria → embed queries →            │
│     → semantic search → rank files → coverage plan          │
└─────────────────────────────────────────────────────────────┘

Storage:
┌─────────────────┐     ┌─────────────────┐
│  embeddings.db  │     │  embeddings/    │
│  (SQLite)       │     │  *.npy files    │
│  - file_path    │     │  (numpy arrays) │
│  - chunk_id     │     │                 │
│  - content_hash │     │                 │
└─────────────────┘     └─────────────────┘
```

### 2.3 Embedding Model Selection

| Model | Dimensions | Cost | Quality | Choice |
|-------|------------|------|---------|--------|
| text-embedding-3-small | 1536 | $0.02/1M tokens | Good | ✅ Default |
| text-embedding-3-large | 3072 | $0.13/1M tokens | Better | Option |
| Cohere embed-v3 | 1024 | Free tier | Good | Fallback |
| Local: all-MiniLM-L6-v2 | 384 | Free | OK | Offline |

### 2.4 Task Breakdown

#### Task 2.4.1: Create Embedding Store Schema
**File**: `modules/embedding_store.py`
**Objective**: SQLite schema for embedding metadata
**Verification**:
- [x] Schema created with migrations
- [x] CRUD operations work correctly
- [x] Content hash prevents re-embedding unchanged files

#### Task 2.4.2: Implement Code Chunker
**File**: `modules/code_chunker.py`
**Objective**: Split code files into semantic chunks (functions, classes)
**Verification**:
- [x] Python AST-based chunking
- [x] TypeScript regex-based chunking
- [x] Chunk size respects token limits (512 tokens max)

#### Task 2.4.3: Implement Embedding Generator
**File**: `modules/embedding_generator.py`
**Objective**: Generate embeddings via LiteLLM
**Verification**:
- [x] Batch embedding support
- [x] Caching to avoid re-embedding
- [x] Fallback to local model if API fails

#### Task 2.4.4: Implement Semantic Search
**File**: `modules/semantic_search.py`
**Objective**: Query embeddings with cosine similarity
**Verification**:
- [x] Top-K retrieval working
- [x] Relevance threshold filtering
- [x] Aggregation from chunk to file level

#### Task 2.4.5: Integrate with Coverage Planner
**File**: `modules/file_manager.py` and `modules/rag_integration.py`
**Objective**: Use semantic search in file selection
**Verification**:
- [x] Spec keywords boost file selection
- [x] semantic_relevance reason added to risk scores
- [x] `enable_semantic_boost` parameter controls feature

#### Task 2.4.6: Add CLI Commands
**File**: `cva.py`
**Objective**: Add `cva index` command for embedding generation
**Verification**:
- [x] `cva index --dir .` creates embeddings
- [x] Progress callback and status output
- [x] Incremental update support (--force to rebuild)

#### Task 2.4.7: Add Unit Tests
**File**: `tests/test_rag_system.py`
**Objective**: Test embedding and search functionality
**Verification**:
- [x] Test chunking preserves context
- [x] Test similarity scoring accuracy
- [x] Test incremental indexing

---

### 2.5 Phase 2 Deliverables

1. **Embedding Store** (`modules/embedding_store.py`):
   - SQLite schema with `embeddings` table
   - Content hash for incremental updates
   - Stats and cleanup operations

2. **Code Chunker** (`modules/code_chunker.py`):
   - AST-based Python chunking (functions, classes, methods)
   - Regex-based TypeScript/JavaScript chunking
   - Section-based Markdown chunking
   - Token-aware splitting (512 max, 50 min, 10% overlap)

3. **Embedding Generator** (`modules/embedding_generator.py`):
   - LiteLLM integration for OpenAI/Cohere models
   - Batch processing with retry logic
   - Cost estimation before indexing
   - Fallback to local sentence-transformers

4. **Semantic Search** (`modules/semantic_search.py`):
   - Cosine similarity with numpy
   - Top-K retrieval with threshold filtering
   - Chunk-to-file aggregation

5. **RAG Integration** (`modules/rag_integration.py`):
   - `RAGIntegration` class bridging search to planner
   - `analyze_spec()` extracts queries from spec text
   - `score_files_for_spec()` returns semantic scores
   - `enhance_risk_scores()` boosts file selection

6. **File Manager Integration** (`modules/file_manager.py`):
   - `spec_text` parameter in `plan_context()`
   - `enable_semantic_boost` toggle
   - `semantic_relevance:{boost}` in risk reasons

7. **CLI Commands** (`cva.py`):
   - `cva index --dir . [--force] [--verbose]`
   - Progress callback with file counts
   - Cost estimation before proceeding

8. **Tests** (`tests/test_rag_system.py`):
   - 20 tests covering all RAG components
   - 100% pass rate

---

## Phase 3: Iterative Judge Refinement (RLHF-Lite)

### 3.1 Overview

**Problem**: The Security Judge vetoed 14/16 criteria with high confidence, indicating miscalibration.

**Solution**: Implement a lightweight feedback loop where human corrections to verdicts are stored and used to improve judge behavior over time.

### 3.2 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  RLHF-Lite Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│  1. Verdict Phase                                            │
│     criteria → judges → verdicts → stored with run_id       │
│                                                              │
│  2. Feedback Phase (human-in-the-loop)                       │
│     human reviews verdict → provides correction →            │
│     correction stored with (run_id, criterion_id)           │
│                                                              │
│  3. Learning Phase (periodic)                                │
│     analyze corrections → identify patterns →                │
│     adjust prompts OR confidence thresholds                 │
└─────────────────────────────────────────────────────────────┘

Data Model:
┌─────────────────────────────────────────────────────────────┐
│  feedback_store.db                                           │
├─────────────────────────────────────────────────────────────┤
│  human_feedback:                                             │
│    - id (UUID)                                               │
│    - run_id (FK)                                             │
│    - criterion_id (str)                                      │
│    - judge_role (enum)                                       │
│    - original_score (float)                                  │
│    - original_verdict (enum)                                 │
│    - corrected_score (float, nullable)                       │
│    - corrected_verdict (enum, nullable)                      │
│    - feedback_text (str)                                     │
│    - created_at (timestamp)                                  │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Learning Mechanisms

| Mechanism | Description | Implementation |
|-----------|-------------|----------------|
| **Threshold Adjustment** | If Security Judge vetoes are often overturned, raise veto threshold | Config update |
| **Few-Shot Injection** | Add corrected examples to judge prompts | Prompt template |
| **Confidence Calibration** | Adjust reported confidence based on accuracy | Post-processing |
| **Pattern Detection** | Identify common false positive patterns | Rule-based filtering |

### 3.4 Task Breakdown

#### Task 3.4.1: Create Feedback Store Schema
**File**: `modules/feedback_store.py`
**Objective**: SQLite schema for human feedback
**Verification**:
- [ ] Schema with migrations
- [ ] CRUD for feedback entries
- [ ] Query by judge role, criterion type

#### Task 3.4.2: Implement Feedback Collection API
**File**: `modules/api.py` (modify)
**Objective**: REST endpoints for submitting feedback
**Verification**:
- [ ] POST /api/feedback accepts corrections
- [ ] GET /api/feedback/stats returns analytics
- [ ] Authentication for feedback submission

#### Task 3.4.3: Implement Feedback UI Component
**File**: `dysruption-ui/components/FeedbackPanel.tsx`
**Objective**: UI for reviewing and correcting verdicts
**Verification**:
- [ ] Display verdict with correction controls
- [ ] Submit feedback to API
- [ ] Show feedback history

#### Task 3.4.4: Implement Threshold Adjuster
**File**: `modules/calibration.py`
**Objective**: Analyze feedback and adjust thresholds
**Verification**:
- [ ] Calculate false positive rate per judge
- [ ] Recommend threshold changes
- [ ] Apply changes to config.yaml

#### Task 3.4.5: Implement Few-Shot Generator
**File**: `modules/prompt_optimizer.py`
**Objective**: Generate few-shot examples from corrections
**Verification**:
- [ ] Extract patterns from feedback
- [ ] Generate new few-shot examples
- [ ] Update judge system prompts

#### Task 3.4.6: Implement Feedback Dashboard
**File**: `dysruption-ui/app/dashboard/feedback/page.tsx`
**Objective**: Analytics dashboard for feedback data
**Verification**:
- [ ] Judge accuracy over time charts
- [ ] False positive/negative breakdown
- [ ] Trend analysis

#### Task 3.4.7: Add Integration Tests
**File**: `tests/test_feedback_loop.py`
**Objective**: End-to-end feedback flow testing
**Verification**:
- [ ] Feedback submission works
- [ ] Threshold adjustment triggers
- [ ] Few-shot generation works

---

## Execution Schedule

### Week 1: Phase 1 (SARIF Export)

| Day | Task | Status |
|-----|------|--------|
| Day 1 AM | Task 1.4.1: SARIF Schema Models | ⬜ |
| Day 1 PM | Task 1.4.2: SARIF Generator | ⬜ |
| Day 1 PM | Task 1.4.3: Tribunal Integration | ⬜ |
| Day 1 EOD | Task 1.4.4: Unit Tests | ⬜ |
| Day 1 EOD | Task 1.4.5: Documentation | ⬜ |

### Week 1-2: Phase 2 (Semantic Embeddings)

| Day | Task | Status |
|-----|------|--------|
| Day 2 AM | Task 2.4.1: Embedding Store Schema | ⬜ |
| Day 2 PM | Task 2.4.2: Code Chunker | ⬜ |
| Day 3 AM | Task 2.4.3: Embedding Generator | ⬜ |
| Day 3 PM | Task 2.4.4: Semantic Search | ⬜ |
| Day 4 AM | Task 2.4.5: Coverage Integration | ⬜ |
| Day 4 PM | Task 2.4.6: CLI Commands | ⬜ |
| Day 4 EOD | Task 2.4.7: Unit Tests | ⬜ |

### Week 2-3: Phase 3 (RLHF-Lite)

| Day | Task | Status |
|-----|------|--------|
| Day 5-6 | Task 3.4.1: Feedback Store | ⬜ |
| Day 6-7 | Task 3.4.2: Feedback API | ⬜ |
| Day 7-8 | Task 3.4.3: Feedback UI | ⬜ |
| Day 8-9 | Task 3.4.4: Threshold Adjuster | ⬜ |
| Day 9-10 | Task 3.4.5: Few-Shot Generator | ⬜ |
| Day 10-11 | Task 3.4.6: Dashboard | ⬜ |
| Day 11-12 | Task 3.4.7: Integration Tests | ⬜ |

---

## Verification Criteria (Definition of Done)

### Phase 1 Complete When:
- [ ] `cva verify` generates `verdict.sarif` alongside existing outputs
- [ ] SARIF file validates against SARIF 2.1.0 schema
- [ ] GitHub Actions workflow uploads SARIF successfully
- [ ] Findings appear in GitHub Security tab
- [ ] All unit tests pass

### Phase 2 Complete When:
- [ ] `cva index` creates embeddings for entire codebase
- [ ] Embeddings persist across runs (SQLite + .npy files)
- [ ] `tribunal.py` is selected when spec mentions "consensus", "judge", "veto"
- [ ] File selection accuracy measurably improved (A/B test)
- [ ] All unit tests pass

### Phase 3 Complete When:
- [ ] Human feedback can be submitted via UI
- [ ] Feedback stored in persistent database
- [ ] Threshold adjuster recommends changes based on feedback
- [ ] Few-shot examples generated from corrections
- [ ] Judge false positive rate decreases over 10 feedback cycles
- [ ] All unit tests pass

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenAI embedding API rate limits | Delays indexing | Use batch API, local fallback |
| SARIF schema complexity | Integration issues | Use official schema validator |
| Feedback quality (human errors) | Bad training signal | Require consensus from multiple reviewers |
| Embedding storage size | Disk space | Compress embeddings, configurable retention |
| Prompt injection via feedback | Security | Sanitize all feedback text |

---

## Dependencies

### Python Packages (requirements.txt additions)
```
sarif-om>=1.0.4         # SARIF object model
numpy>=1.24.0           # Embedding storage
sentence-transformers   # Local embedding fallback
chromadb>=0.4.0         # Vector store (optional)
```

### Environment Variables
```
OPENAI_API_KEY          # Required for embeddings
CVA_EMBEDDING_MODEL     # Optional: override default model
CVA_FEEDBACK_DB         # Optional: feedback database path
```

---

## File Structure (New Files)

```
modules/
├── sarif_export.py          # Phase 1: SARIF generation
├── embedding_store.py       # Phase 2: Embedding persistence
├── code_chunker.py          # Phase 2: Code splitting
├── embedding_generator.py   # Phase 2: Embedding creation
├── semantic_search.py       # Phase 2: Vector search
├── feedback_store.py        # Phase 3: Feedback persistence
├── calibration.py           # Phase 3: Threshold adjustment
└── prompt_optimizer.py      # Phase 3: Few-shot generation

tests/
├── test_sarif_export.py     # Phase 1 tests
├── test_semantic_search.py  # Phase 2 tests
└── test_feedback_loop.py    # Phase 3 tests

docs/
├── github-sarif-integration.md  # Phase 1 docs
├── semantic-indexing.md         # Phase 2 docs
└── feedback-system.md           # Phase 3 docs
```

---

## Next Action

**Proceed to Phase 1, Task 1.4.1: Create SARIF Schema Models**

Ready to execute. Awaiting confirmation or proceed automatically.
