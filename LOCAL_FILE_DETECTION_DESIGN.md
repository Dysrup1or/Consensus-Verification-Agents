# Local File Detection System Design
## Replacing GitHub-Dependent Ingestion for Offline Operation

**Document Version:** 1.0  
**Date:** 2025-01-15  
**Author:** Dysruption Enterprises / CVA Architecture Team

---

## Executive Summary

This document outlines a comprehensive design for a local file detection system that can replace the current GitHub-dependent file ingestion mechanism in the CVA (Consensus Verifier Agent) platform. The goal is to enable **full offline operation** while maintaining compatibility, security, and performance parity with the existing system.

**Key Finding:** The CVA backend already has robust local file detection capabilities via the `DirectoryWatcher` class using the **watchdog** library. The primary gap is in the **frontend UI**, which currently only exposes GitHub import functionality. This design focuses on exposing existing backend capabilities and adding browser-based local file ingestion.

---

## 1. Current Architecture Analysis

### 1.1 Existing GitHub-Dependent Flow

```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Browser (Next.js) │    │  GitHub API         │    │  FastAPI Backend    │
│   /app/api/github/* │───▶│  - OAuth            │    │  /upload endpoint   │
│   - fetchGitHubRepos│    │  - Zipball download │───▶│  - File storage     │
│   - importGitHubRepo│    │  - Branch listing   │    │  - DirectoryWatcher │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

**GitHub Integration Points:**
- [lib/api.ts](dysruption-ui/lib/api.ts) - `fetchGitHubRepos()`, `fetchGitHubBranches()`, `importGitHubRepo()`
- [app/api/github/import/route.ts](dysruption-ui/app/api/github/import/route.ts) - Zipball download & extraction
- [components/onboarding/SelectRepoStep.tsx](dysruption-ui/components/onboarding/SelectRepoStep.tsx) - Repository picker UI

### 1.2 Existing Local File Detection (Backend)

The backend **already supports local file detection** via:

**[modules/watcher_v2.py](dysruption_cva/modules/watcher_v2.py):**
```python
class DirectoryWatcher:
    """
    Features:
    - Smart 3-second debounce (reset on file save)
    - dirty_files set tracking for incremental scans
    - FileTree output with Pydantic schemas
    - Git repository support
    """
    
    def __init__(self, target_path, config_path="config.yaml", on_change_callback=None):
        self.target_path = os.path.abspath(target_path)
        # Uses watchdog.observers.Observer for file system events
        
    def build_file_tree(self, dirty_only=False, dirty_files=None) -> FileTree:
        # Walks directory, reads files, computes hashes
        # Returns structured Pydantic FileTree model
```

**Key Capabilities Already Present:**
- ✅ Cross-platform file watching (Windows/macOS/Linux via watchdog)
- ✅ Smart debouncing (3-second wait after last change)
- ✅ Dirty file tracking for incremental processing
- ✅ Language detection (Python, JS, TS, etc.)
- ✅ Ignore patterns (__pycache__, node_modules, .git, etc.)
- ✅ FileTree Pydantic models for structured output
- ✅ Git repository support

---

## 2. Library Evaluation

### 2.1 Backend File Watching Libraries

| Library | Platform | Mechanism | Performance | Maturity | Recommendation |
|---------|----------|-----------|-------------|----------|----------------|
| **watchdog** (current) | Win/macOS/Linux | Native events + polling fallback | ⭐⭐⭐⭐⭐ | Production-ready | **KEEP** |
| inotify | Linux only | Kernel events | ⭐⭐⭐⭐⭐ | Production-ready | Linux-only |
| pyinotify | Linux only | inotify wrapper | ⭐⭐⭐⭐ | Stable | Linux-only |
| python-fsevents | macOS only | FSEvents | ⭐⭐⭐⭐⭐ | Stable | macOS-only |

**Recommendation:** **Keep watchdog** - It's already integrated, mature (used by 11.8M+ packages), cross-platform, and well-maintained.

### 2.2 Frontend File Access APIs

| API | Browser Support | Offline | Directory Access | Security |
|-----|-----------------|---------|------------------|----------|
| **File System Access API** | Chrome 86+, Edge 86+, Firefox 111+, Safari 15.2+ | ✅ | ✅ `showDirectoryPicker()` | User consent required |
| `<input type="file">` | Universal | ✅ | webkitdirectory attr | Limited (per-file) |
| Drag & Drop API | Universal | ✅ | `DataTransferItem.getAsFileSystemHandle()` | User-initiated only |
| File API | Universal | ✅ | ❌ | Single files only |

**Recommendation:** Use **File System Access API** with `showDirectoryPicker()` for modern browsers, with `<input webkitdirectory>` as fallback for Safari/older browsers.

### 2.3 Node.js/Electron Alternatives (for Desktop Wrapper)

| Library | Platform | Use Case |
|---------|----------|----------|
| **chokidar** | Node.js | Minimal, efficient file watching (35M+ dependents) |
| fs.watch | Node.js native | Built-in, but raw events need normalization |
| nsfw | Node.js | Native recursive watching |

**Recommendation:** If building an Electron desktop app, use **chokidar** for frontend file watching.

---

## 3. Security Considerations

### 3.1 Browser Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     BROWSER SECURITY LAYERS                     │
├─────────────────────────────────────────────────────────────────┤
│ 1. USER CONSENT                                                 │
│    - File System Access API requires explicit user action       │
│    - showDirectoryPicker() can only be called from user gesture │
│    - No silent background access to filesystem                  │
├─────────────────────────────────────────────────────────────────┤
│ 2. PERMISSION PERSISTENCE                                       │
│    - Handles can be stored in IndexedDB for "recent projects"   │
│    - User must re-grant permission per session                  │
│    - queryPermission() / requestPermission() for re-access      │
├─────────────────────────────────────────────────────────────────┤
│ 3. SAME-ORIGIN POLICY                                           │
│    - Files read locally stay in browser memory                  │
│    - Backend receives files via fetch/upload, not direct access │
│    - No cross-origin file exfiltration possible                 │
├─────────────────────────────────────────────────────────────────┤
│ 4. SECURE CONTEXT REQUIRED                                      │
│    - File System Access API requires HTTPS or localhost         │
│    - Offline-first PWA compatible                               │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Backend Security Model

**Existing Protections in [modules/api.py](dysruption_cva/modules/api.py):**
```python
# Production mode restricts paths to UPLOAD_ROOT
if os.getenv("CVA_PROD", "").lower() == "true":
    resolved = os.path.realpath(local_path)
    if not resolved.startswith(os.path.realpath(UPLOAD_ROOT)):
        raise HTTPException(403, "Path outside allowed directory")
```

**Additional Recommendations:**
1. **Path Traversal Prevention:** Validate all paths server-side
2. **File Size Limits:** Enforce maximum file sizes (already 50MB limit)
3. **Content-Type Validation:** Only accept known code file types
4. **Rate Limiting:** Prevent DoS via rapid file uploads
5. **Symlink Resolution:** Use `os.path.realpath()` before access

### 3.3 Offline-Specific Security

| Threat | Mitigation |
|--------|------------|
| Malicious files on disk | File type validation, no execution |
| Path traversal | Canonical path resolution |
| Large file DoS | Size limits, streaming |
| Sensitive file exposure | User explicitly selects directories |

---

## 4. Proposed System Design

### 4.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           OFFLINE-CAPABLE CVA                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         BROWSER (Next.js)                               │ │
│  ├─────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                         │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │ │
│  │  │ LocalFolderPicker│  │ DragDropZone   │  │ RecentProjectsStore    │ │ │
│  │  │ (showDirectory   │  │ (DataTransfer  │  │ (IndexedDB handles)    │ │ │
│  │  │  Picker API)     │  │  Item API)     │  │                        │ │ │
│  │  └────────┬─────────┘  └───────┬────────┘  └───────────┬─────────────┘ │ │
│  │           │                    │                       │               │ │
│  │           ▼                    ▼                       ▼               │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │  │              LocalFileIngestionService                              │ │
│  │  │  - readDirectory(handle) → FileTree                                 │ │
│  │  │  - uploadToBackend(files) → POST /upload                            │ │
│  │  │  - watchForChanges(handle) → FileSystemObserver (experimental)      │ │
│  │  └────────────────────────────────┬────────────────────────────────────┘ │
│  │                                   │                                      │
│  └───────────────────────────────────┼──────────────────────────────────────┘ │
│                                      │                                        │
│  ┌───────────────────────────────────▼──────────────────────────────────────┐ │
│  │                       BACKEND (FastAPI)                                  │ │
│  ├──────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                          │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │ │
│  │  │ /upload         │  │ /run            │  │ DirectoryWatcher       │  │ │
│  │  │ POST files      │  │ POST local_path │  │ (watchdog-based)       │  │ │
│  │  │ → temp_uploads/ │  │ → FileTree      │  │ → SmartDebounceHandler │  │ │
│  │  └────────┬────────┘  └────────┬────────┘  └───────────┬─────────────┘  │ │
│  │           │                    │                       │                │ │
│  │           ▼                    ▼                       ▼                │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │ │
│  │  │                    CVA Verification Engine                       │   │ │
│  │  │  - Parser → Dependency Resolver → Router → Tribunal → Verdicts  │   │ │
│  │  └──────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component Design

#### 4.2.1 LocalFolderPicker Component

```tsx
// components/LocalFolderPicker.tsx
interface LocalFolderPickerProps {
  onFolderSelected: (files: FileTree) => void;
  onError: (error: Error) => void;
}

export function LocalFolderPicker({ onFolderSelected, onError }: LocalFolderPickerProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [isSupported] = useState(() => 'showDirectoryPicker' in window);

  const handlePickFolder = async () => {
    if (!isSupported) {
      // Fallback to <input webkitdirectory>
      return;
    }
    
    try {
      setIsLoading(true);
      const dirHandle = await window.showDirectoryPicker({
        mode: 'read',
        startIn: 'documents',
      });
      
      const files = await readDirectoryRecursive(dirHandle);
      await uploadFilesToBackend(files);
      onFolderSelected(files);
    } catch (err) {
      if (err.name !== 'AbortError') {
        onError(err);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Button onClick={handlePickFolder} disabled={isLoading}>
      {isLoading ? <Spinner /> : <FolderIcon />}
      Select Local Project Folder
    </Button>
  );
}
```

#### 4.2.2 LocalFileIngestionService

```typescript
// lib/local-file-service.ts
export class LocalFileIngestionService {
  private readonly IGNORED_PATTERNS = [
    /node_modules/,
    /__pycache__/,
    /\.git/,
    /\.venv/,
    /dist/,
    /build/,
  ];
  
  private readonly SUPPORTED_EXTENSIONS = [
    '.py', '.js', '.ts', '.jsx', '.tsx', '.pyi',
  ];
  
  async readDirectoryRecursive(
    dirHandle: FileSystemDirectoryHandle,
    path = ''
  ): Promise<LocalFile[]> {
    const files: LocalFile[] = [];
    
    for await (const [name, handle] of dirHandle.entries()) {
      const fullPath = path ? `${path}/${name}` : name;
      
      if (this.shouldIgnore(fullPath)) continue;
      
      if (handle.kind === 'directory') {
        files.push(...await this.readDirectoryRecursive(handle, fullPath));
      } else if (this.isSupportedFile(name)) {
        const file = await handle.getFile();
        const content = await file.text();
        files.push({
          path: fullPath,
          content,
          size: file.size,
          lastModified: file.lastModified,
        });
      }
    }
    
    return files;
  }
  
  async uploadToBackend(files: LocalFile[]): Promise<UploadResult> {
    const formData = new FormData();
    
    for (const file of files) {
      const blob = new Blob([file.content], { type: 'text/plain' });
      formData.append('files', blob, file.path);
    }
    
    const response = await fetch('/api/local/upload', {
      method: 'POST',
      body: formData,
    });
    
    return response.json();
  }
}
```

#### 4.2.3 Backend Local Upload Endpoint

```python
# modules/api.py - New endpoint
@app.post("/local/upload")
async def upload_local_files(
    files: List[UploadFile] = File(...),
    project_name: str = Form(default="local-project"),
):
    """
    Receive files uploaded from browser's local file picker.
    
    Security:
    - Files are stored in temp_uploads/{session_id}/
    - Path traversal prevented via basename extraction
    - Size limits enforced
    """
    session_id = str(uuid.uuid4())
    upload_dir = Path(UPLOAD_ROOT) / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_paths = []
    for file in files:
        # Prevent path traversal
        safe_name = Path(file.filename).name if "/" in file.filename else file.filename
        file_path = upload_dir / safe_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(413, f"File too large: {file.filename}")
            
        file_path.write_bytes(content)
        file_paths.append(str(file_path))
    
    return {
        "session_id": session_id,
        "upload_dir": str(upload_dir),
        "file_count": len(file_paths),
        "files": file_paths,
    }
```

### 4.3 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LOCAL FILE INGESTION FLOW                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. USER INITIATES                                                          │
│     ┌──────────────┐                                                        │
│     │ User clicks  │                                                        │
│     │ "Open Local  │                                                        │
│     │  Project"    │                                                        │
│     └──────┬───────┘                                                        │
│            ▼                                                                │
│  2. BROWSER PERMISSION                                                      │
│     ┌──────────────────────────────────────────────────────┐                │
│     │ showDirectoryPicker() → User selects folder          │                │
│     │ Returns: FileSystemDirectoryHandle                   │                │
│     └──────┬───────────────────────────────────────────────┘                │
│            ▼                                                                │
│  3. RECURSIVE READ                                                          │
│     ┌──────────────────────────────────────────────────────┐                │
│     │ for await (entry of dirHandle.entries())             │                │
│     │   - Filter by extension (.py, .js, .ts, etc.)        │                │
│     │   - Skip ignored dirs (node_modules, .git, etc.)     │                │
│     │   - Read file content via getFile() → text()         │                │
│     └──────┬───────────────────────────────────────────────┘                │
│            ▼                                                                │
│  4. UPLOAD TO BACKEND                                                       │
│     ┌──────────────────────────────────────────────────────┐                │
│     │ POST /api/local/upload                               │                │
│     │   - FormData with all files                          │                │
│     │   - Batched in 100-file chunks if large              │                │
│     │   - Progress callback for UI                         │                │
│     └──────┬───────────────────────────────────────────────┘                │
│            ▼                                                                │
│  5. BACKEND PROCESSING                                                      │
│     ┌──────────────────────────────────────────────────────┐                │
│     │ Files saved to temp_uploads/{session_id}/            │                │
│     │ DirectoryWatcher.build_file_tree() → FileTree        │                │
│     │ Ready for /run endpoint                              │                │
│     └──────┬───────────────────────────────────────────────┘                │
│            ▼                                                                │
│  6. CVA VERIFICATION                                                        │
│     ┌──────────────────────────────────────────────────────┐                │
│     │ POST /run { local_path: "temp_uploads/{session_id}"} │                │
│     │ → Parser → Resolver → Router → Tribunal → Verdicts   │                │
│     └──────────────────────────────────────────────────────┘                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Challenges

### 5.1 Browser Compatibility

| Challenge | Solution |
|-----------|----------|
| Safari doesn't support `showDirectoryPicker()` | Fallback to `<input webkitdirectory>` |
| Firefox partial support | Feature detection + polyfill |
| Older browsers | Graceful degradation to file input |

```typescript
function getFilePickerStrategy(): FilePickerStrategy {
  if ('showDirectoryPicker' in window) {
    return new FileSystemAccessStrategy();
  } else if ('webkitdirectory' in document.createElement('input')) {
    return new WebkitDirectoryStrategy();
  } else {
    return new FileInputStrategy();
  }
}
```

### 5.2 Large Codebases

| Challenge | Solution |
|-----------|----------|
| >1000 files | Streaming upload with progress |
| Memory exhaustion | Process files in chunks |
| Slow upload | Web Worker for background processing |
| User feedback | Progress bar with file counts |

### 5.3 File Change Detection (Continuous Watching)

**Browser Limitation:** The File System Access API's `FileSystemObserver` is experimental and not widely supported.

**Solutions:**
1. **Manual Refresh Button:** User clicks to re-sync
2. **Polling Interval:** Check for changes every 5 seconds (battery-conscious)
3. **Electron Desktop App:** Use chokidar for true real-time watching

---

## 6. Implementation Roadmap

### Phase 1: Core Local Upload (Week 1)
- [ ] Create `LocalFolderPicker` component
- [ ] Implement `LocalFileIngestionService`
- [ ] Add `/api/local/upload` Next.js route
- [ ] Add `/local/upload` FastAPI endpoint
- [ ] Browser feature detection + fallback

### Phase 2: UI Integration (Week 2)
- [ ] Add "Open Local Folder" to onboarding wizard
- [ ] Add to project dashboard sidebar
- [ ] Recent projects store (IndexedDB)
- [ ] Drag-and-drop zone on dashboard

### Phase 3: File Watching (Week 3)
- [ ] "Refresh Files" button for manual sync
- [ ] Optional polling mode for live changes
- [ ] Desktop app wrapper with chokidar (optional)

### Phase 4: Polish (Week 4)
- [ ] Progress indicators for large uploads
- [ ] Error handling and retry logic
- [ ] Accessibility (keyboard navigation, ARIA)
- [ ] Performance testing with 10K+ file repos

---

## 7. Recommendations

### 7.1 Immediate Actions

1. **Keep watchdog** - No need to replace the backend file watching library
2. **Implement File System Access API** - Best user experience for modern browsers
3. **Add fallback** - `<input webkitdirectory>` for Safari/older browsers
4. **Expose existing backend** - The `/run` endpoint already accepts local paths

### 7.2 Architecture Decisions

| Decision | Recommendation | Rationale |
|----------|----------------|-----------|
| File watching library | Keep watchdog | Already integrated, cross-platform, mature |
| Browser file picker | File System Access API | Modern, secure, directory-level access |
| Fallback picker | `<input webkitdirectory>` | Universal support |
| File change detection | Manual refresh + optional polling | Browser API limitations |
| Desktop app | Optional Electron wrapper | Enables true real-time watching |

### 7.3 Security Checklist

- [ ] All paths validated server-side
- [ ] File size limits enforced (50MB per file)
- [ ] Symlinks resolved before access
- [ ] HTTPS required in production
- [ ] User consent required for file access
- [ ] Session isolation for uploaded files

---

## 8. Conclusion

The CVA system is **already well-positioned for offline operation** with its existing `DirectoryWatcher` implementation using the battle-tested watchdog library. The primary work needed is:

1. **Frontend UI components** to expose local folder picking
2. **Browser compatibility layer** with File System Access API + fallbacks
3. **Minor backend endpoint** for receiving browser-uploaded files

This design achieves **full offline capability** without replacing any core infrastructure, maintaining the existing security model, and providing a familiar user experience for vibecoding developers.

---

## Appendix A: Key Files Reference

| File | Purpose |
|------|---------|
| [modules/watcher_v2.py](dysruption_cva/modules/watcher_v2.py) | DirectoryWatcher + SmartDebounceHandler |
| [modules/watcher.py](dysruption_cva/modules/watcher.py) | Original watcher implementation |
| [modules/api.py](dysruption_cva/modules/api.py) | FastAPI endpoints including /run |
| [modules/schemas.py](dysruption_cva/modules/schemas.py) | FileTree, FileNode Pydantic models |
| [lib/api.ts](dysruption-ui/lib/api.ts) | Frontend API client |
| [app/api/github/import/route.ts](dysruption-ui/app/api/github/import/route.ts) | GitHub import (to be paralleled) |

## Appendix B: External References

- [watchdog Documentation](https://python-watchdog.readthedocs.io/)
- [chokidar GitHub](https://github.com/paulmillr/chokidar)
- [File System Access API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API)
- [Chrome File System Access Guide](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access)
