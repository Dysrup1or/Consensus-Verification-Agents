/**
 * Change Tracker
 * 
 * Tracks file changes and implements smart debouncing.
 * Detects bulk operations (AI agents creating many files) and adjusts debounce accordingly.
 */

import { FileChangeEvent, FileChangeBatch } from '../types';
import { BULK_CHANGE, LOG_PREFIX } from '../constants';

type TriggerHandler = (files: string[], batch: FileChangeBatch) => void;

export class ChangeTracker {
  private dirtyFiles: Set<string> = new Set();
  private deletedFiles: Set<string> = new Set();
  private debounceTimer: NodeJS.Timeout | null = null;
  private baseDebounceMs: number;
  private currentDebounceMs: number;
  private onTrigger: TriggerHandler;

  // Bulk change detection
  private changeBuffer: FileChangeEvent[] = [];
  private bufferStartTime: number = 0;
  private isBulkOperation: boolean = false;

  // Statistics
  private totalChanges: number = 0;
  private totalTriggers: number = 0;

  constructor(debounceMs: number, onTrigger: TriggerHandler) {
    this.baseDebounceMs = debounceMs;
    this.currentDebounceMs = debounceMs;
    this.onTrigger = onTrigger;
  }

  /**
   * Add a changed file to the dirty set
   */
  addFile(event: FileChangeEvent): void {
    const filePath = event.path;

    if (event.type === 'delete') {
      // Track deleted files separately
      this.deletedFiles.add(filePath);
      this.dirtyFiles.delete(filePath);
    } else {
      // Track created or modified files
      this.dirtyFiles.add(filePath);
      this.deletedFiles.delete(filePath);
    }

    this.totalChanges++;
    this.detectBulkOperation(event);
    this.scheduleVerification();
  }

  /**
   * Detect if we're in a bulk operation (AI agent, git checkout, etc.)
   */
  private detectBulkOperation(event: FileChangeEvent): void {
    const now = Date.now();

    // Start new buffer window if previous one expired
    if (now - this.bufferStartTime > BULK_CHANGE.WINDOW_MS) {
      this.changeBuffer = [event];
      this.bufferStartTime = now;
      this.isBulkOperation = false;
    } else {
      this.changeBuffer.push(event);
    }

    // Check if we've crossed the bulk threshold
    if (this.changeBuffer.length >= BULK_CHANGE.THRESHOLD && !this.isBulkOperation) {
      this.isBulkOperation = true;
      
      // Extend debounce time for bulk operations
      this.currentDebounceMs = Math.min(
        this.baseDebounceMs * BULK_CHANGE.DEBOUNCE_MULTIPLIER,
        BULK_CHANGE.MAX_DEBOUNCE_MS
      );
      
      console.log(
        `${LOG_PREFIX.INFO} Bulk operation detected (${this.changeBuffer.length} files), ` +
        `extending debounce to ${this.currentDebounceMs}ms`
      );
    }
  }

  /**
   * Schedule a verification trigger after debounce period
   */
  private scheduleVerification(): void {
    // Clear existing timer
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    // Schedule new trigger
    this.debounceTimer = setTimeout(() => {
      this.triggerVerification();
    }, this.currentDebounceMs);
  }

  /**
   * Trigger the verification callback
   */
  private triggerVerification(): void {
    const files = Array.from(this.dirtyFiles);
    
    if (files.length === 0) {
      // No files to verify (maybe all were deleted)
      this.reset();
      return;
    }

    // Create batch info
    const batch: FileChangeBatch = {
      changes: [...this.changeBuffer],
      isBulkOperation: this.isBulkOperation,
      duration: Date.now() - this.bufferStartTime,
    };

    // Clear tracking state before callback
    const filesToVerify = [...files];
    this.reset();
    
    this.totalTriggers++;

    // Call handler
    try {
      this.onTrigger(filesToVerify, batch);
    } catch (error) {
      console.error(`${LOG_PREFIX.ERROR} Error in trigger handler:`, error);
    }
  }

  /**
   * Reset tracker state
   */
  private reset(): void {
    this.dirtyFiles.clear();
    this.deletedFiles.clear();
    this.changeBuffer = [];
    this.isBulkOperation = false;
    this.currentDebounceMs = this.baseDebounceMs;
    
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
  }

  /**
   * Force trigger immediately (bypass debounce)
   */
  forceTriger(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }
    this.triggerVerification();
  }

  /**
   * Cancel pending verification
   */
  cancel(): void {
    this.reset();
  }

  /**
   * Get list of currently dirty files
   */
  getDirtyFiles(): string[] {
    return Array.from(this.dirtyFiles);
  }

  /**
   * Get list of deleted files
   */
  getDeletedFiles(): string[] {
    return Array.from(this.deletedFiles);
  }

  /**
   * Check if there are pending changes
   */
  hasPendingChanges(): boolean {
    return this.dirtyFiles.size > 0 || this.debounceTimer !== null;
  }

  /**
   * Get number of pending files
   */
  getPendingCount(): number {
    return this.dirtyFiles.size;
  }

  /**
   * Check if currently in bulk operation mode
   */
  isInBulkOperation(): boolean {
    return this.isBulkOperation;
  }

  /**
   * Update debounce time
   */
  setDebounceMs(ms: number): void {
    this.baseDebounceMs = ms;
    this.currentDebounceMs = ms;
  }

  /**
   * Get statistics
   */
  getStats(): { totalChanges: number; totalTriggers: number } {
    return {
      totalChanges: this.totalChanges,
      totalTriggers: this.totalTriggers,
    };
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.reset();
  }
}
