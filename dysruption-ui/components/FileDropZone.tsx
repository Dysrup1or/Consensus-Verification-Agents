"use client";

import { useState, useCallback, useRef } from 'react';
import { Upload, FolderOpen, AlertCircle, X, Loader2, FileCode, CheckCircle2 } from 'lucide-react';
import { clsx } from 'clsx';
import { uploadFilesBatched } from '@/lib/api';

interface FileDropZoneProps {
  onFilesSelected: (files: FileList | null, path?: string) => void;
  acceptedTypes?: string;
  disabled?: boolean;
}

export default function FileDropZone({ onFilesSelected, acceptedTypes, disabled }: FileDropZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [manualPath, setManualPath] = useState('');
  const [dropError, setDropError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  
  // NEW: Track successful upload state
  const [uploadedPath, setUploadedPath] = useState<string | null>(null);
  const [uploadedOriginalName, setUploadedOriginalName] = useState<string | null>(null);
  const [uploadedFileCount, setUploadedFileCount] = useState(0);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled && !isUploading) setIsDragOver(true);
  }, [disabled, isUploading]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  // Recursive file scanner
  const scanFiles = async (item: any, path: string = ''): Promise<{ file: File, path: string }[]> => {
    if (item.isFile) {
      return new Promise((resolve) => {
        item.file((file: File) => {
          resolve([{ file, path: path + file.name }]);
        });
      });
    } else if (item.isDirectory) {
      // Skip node_modules and .git
      if (item.name === 'node_modules' || item.name === '.git' || item.name === '.venv' || item.name === '__pycache__') {
        return [];
      }

      const dirReader = item.createReader();
      const entries: any[] = [];

      const readEntries = async () => {
        const result = await new Promise<any[]>((resolve) => {
          dirReader.readEntries((res: any[]) => resolve(res));
        });

        if (result.length > 0) {
          entries.push(...result);
          await readEntries(); // Continue reading (Chrome limit is 100)
        }
      };

      await readEntries();

      const results = await Promise.all(
        entries.map(entry => scanFiles(entry, path + item.name + '/'))
      );

      return results.flat();
    }
    return [];
  };

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    if (disabled || isUploading) return;

    const items = e.dataTransfer.items;
    if (!items || items.length === 0) return;

    setIsUploading(true);
    setUploadStatus("Scanning files...");
    setUploadProgress(0);
    setDropError(null);

    try {
      const allFiles: { file: File, path: string }[] = [];
      let rootFolderName = "Uploaded Content";

      // Use webkitGetAsEntry for directory support
      for (let i = 0; i < items.length; i++) {
        const item = (items[i] as any).webkitGetAsEntry();
        if (item) {
          // Capture the name of the first item (usually the folder name)
          if (i === 0) rootFolderName = item.name;
          
          const files = await scanFiles(item);
          allFiles.push(...files);
        }
      }

      if (allFiles.length === 0) {
        throw new Error("No valid files found. Please drop a folder containing code.");
      }

      // Filter unwanted files
      const validFiles = allFiles.filter(f => {
        const name = f.file.name.toLowerCase();
        // Reject binaries/media
        if (/\.(jpg|jpeg|png|gif|mp4|mp3|exe|dll|bin|zip|tar|gz)$/.test(name)) return false;
        // Reject system files
        if (name === '.ds_store' || name === 'thumbs.db') return false;
        // Reject env files (security)
        if (name.startsWith('.env')) return false;
        return true;
      });

      if (validFiles.length === 0) {
        throw new Error("All files were filtered out. Please drop source code files.");
      }

      setUploadStatus(`Uploading ${validFiles.length} files...`);

      // Upload
      const files = validFiles.map(f => f.file);
      const paths = validFiles.map(f => f.path);

      const result = await uploadFilesBatched(files, paths, (percent) => {
        setUploadProgress(percent);
      });

      console.log('✅ Upload complete:', result);
      setUploadStatus("Upload complete!");

      // Pass the temp path to the parent
      onFilesSelected(null, result.path);
      
      // NEW: Update UI to show successful upload
      setUploadedPath(result.path);
      setUploadedOriginalName(rootFolderName);
      setUploadedFileCount(result.count);
      // We do NOT set manualPath here anymore, to avoid confusing the user 
      // with the internal temp path in the "Project Path" input.
      // setManualPath(result.path); 

      // Reset upload progress after a moment, but keep success state
      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress(0);
        // Keep uploadStatus showing success
      }, 1000);

    } catch (err: any) {
      console.error('Upload error:', err);
      setDropError(err.message || "Failed to upload files");
      setIsUploading(false);
      setUploadStatus(null);
    }
  }, [disabled, isUploading, onFilesSelected]);

  const handlePathSubmit = () => {
    if (manualPath.trim()) {
      onFilesSelected(null, manualPath.trim());
      setDropError(null);
    }
  };

  const clearError = () => {
    setDropError(null);
  };

  return (
    <div className="space-y-4">
      {/* Primary: Manual Path Entry */}
      <div className="p-4 rounded-xl bg-surface border-2 border-primary/50">
        <h4 className="text-sm font-semibold text-primary mb-2 flex items-center gap-2">
          <FolderOpen size={16} /> Project Path
        </h4>
        <div className="flex gap-2">
          <input
            type="text"
            value={manualPath}
            onChange={(e) => setManualPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePathSubmit()}
            placeholder="C:\Users\you\Projects\my-app"
            disabled={disabled || isUploading}
            className={clsx(
              'flex-1 px-4 py-3 rounded-lg bg-background border border-border text-sm font-mono',
              'placeholder:text-textMuted focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary',
              'transition-all duration-200',
              (disabled || isUploading) && 'opacity-50 cursor-not-allowed'
            )}
          />
          <button
            onClick={handlePathSubmit}
            disabled={disabled || isUploading || !manualPath.trim()}
            className={clsx(
              'px-4 py-3 rounded-lg bg-primary text-white font-medium',
              'hover:bg-primaryHover transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            Use Path
          </button>
        </div>
      </div>

      {/* Divider */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-px bg-border" />
        <span className="text-xs text-textMuted uppercase tracking-wider">or drop folder</span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* Secondary: Drop Zone (Upload Mode) */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={clsx(
          'relative border-2 border-dashed rounded-xl p-6 transition-all duration-200',
          'flex flex-col items-center justify-center min-h-[160px]',
          dropError
            ? 'border-danger bg-danger/5'
            : isUploading
              ? 'border-primary bg-primary/5'
              : isDragOver
                ? 'border-primary bg-primary/10 scale-[1.02]'
                : 'border-border/50 hover:border-primary/30 hover:bg-surface/30',
          (disabled || isUploading) && !dropError && 'cursor-default'
        )}
      >
        {isUploading ? (
          <div className="text-center w-full max-w-xs animate-in fade-in zoom-in duration-300">
            <div className="relative w-12 h-12 mx-auto mb-4">
              <Loader2 className="w-12 h-12 text-primary animate-spin" />
            </div>
            <h5 className="text-sm font-bold text-textPrimary mb-1">
              {uploadStatus || "Processing..."}
            </h5>
            <div className="w-full h-2 bg-surface rounded-full overflow-hidden mt-3 border border-border">
              <div
                className="h-full bg-primary transition-all duration-300 ease-out"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="text-xs text-textMuted mt-2 font-mono">
              {uploadProgress}%
            </p>
          </div>
        ) : dropError ? (
          <div className="text-center animate-in fade-in zoom-in duration-200">
            <div className="w-12 h-12 rounded-full bg-danger/10 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-6 h-6 text-danger" />
            </div>
            <h5 className="text-sm font-bold text-danger mb-1">Upload Failed</h5>
            <p className="text-sm text-textPrimary mb-4 max-w-md mx-auto">
              {dropError}
            </p>
            <button
              onClick={(e) => { e.stopPropagation(); clearError(); }}
              className="px-4 py-2 rounded-lg bg-surface border border-border text-xs font-medium hover:bg-surfaceHover transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : uploadedPath ? (
          <div className="text-center animate-in fade-in zoom-in duration-200">
            <div className="w-12 h-12 rounded-full bg-success/20 flex items-center justify-center mx-auto mb-3">
              <CheckCircle2 className="w-6 h-6 text-success" />
            </div>
            <h5 className="text-sm font-bold text-success mb-1">Upload Complete!</h5>
            
            {/* Show Original Name Prominently */}
            <p className="text-lg font-semibold text-textPrimary mb-1">
              {uploadedOriginalName}
            </p>
            
            {/* Show Temp Path subtly */}
            <p className="text-xs text-textMuted mb-1 font-mono break-all max-w-md mx-auto opacity-70">
              Staged at: {uploadedPath}
            </p>
            
            <p className="text-xs text-textSecondary mb-3">
              {uploadedFileCount} file{uploadedFileCount !== 1 ? 's' : ''} ready for verification
            </p>
            <button
              onClick={(e) => { 
                e.stopPropagation(); 
                setUploadedPath('');
                setUploadedOriginalName(null);
                setUploadedFileCount(0);
                setManualPath('');
              }}
              className="px-4 py-2 rounded-lg bg-surface border border-border text-xs font-medium hover:bg-surfaceHover transition-colors"
            >
              Upload Different Folder
            </button>
          </div>
        ) : (
          <div className="text-center pointer-events-none">
            <div className="w-12 h-12 rounded-full bg-surface flex items-center justify-center mx-auto mb-3 group-hover:scale-110 transition-transform">
              <Upload className="w-6 h-6 text-primary/70" />
            </div>
            <h5 className="text-sm font-medium text-textPrimary mb-1">
              Drag & Drop Project Folder
            </h5>
            <p className="text-xs text-textSecondary mb-4 max-w-sm mx-auto">
              We'll upload and analyze your code securely.
              <br />
              <span className="text-textMuted">(Binaries & node_modules are automatically skipped)</span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}


