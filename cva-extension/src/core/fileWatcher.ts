/**
 * File Watcher
 * 
 * Watches for file changes in the workspace using VS Code's FileSystemWatcher API.
 * Filters out ignored patterns and emits change events for tracked files.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { FileChangeEvent } from '../types';
import { DEFAULT_IGNORE_PATTERNS, LOG_PREFIX } from '../constants';

type ChangeHandler = (event: FileChangeEvent) => void;

export class FileWatcher implements vscode.Disposable {
  private watchers: vscode.FileSystemWatcher[] = [];
  private changeHandlers: Set<ChangeHandler> = new Set();
  private ignorePatterns: string[];
  private outputChannel: vscode.OutputChannel | null = null;

  constructor(
    patterns: string[] = ['**/*.{py,js,ts,jsx,tsx,java,go,rs}'],
    ignorePatterns: string[] = [...DEFAULT_IGNORE_PATTERNS],
    outputChannel?: vscode.OutputChannel
  ) {
    this.ignorePatterns = ignorePatterns;
    this.outputChannel = outputChannel ?? null;
    
    // Create a watcher for each pattern
    for (const pattern of patterns) {
      this.createWatcher(pattern);
    }
  }

  /**
   * Create a file system watcher for a glob pattern
   */
  private createWatcher(pattern: string): void {
    const watcher = vscode.workspace.createFileSystemWatcher(
      pattern,
      false, // Don't ignore creates
      false, // Don't ignore changes
      false  // Don't ignore deletes
    );

    watcher.onDidCreate((uri) => this.handleChange('create', uri));
    watcher.onDidChange((uri) => this.handleChange('change', uri));
    watcher.onDidDelete((uri) => this.handleChange('delete', uri));

    this.watchers.push(watcher);
  }

  /**
   * Handle a file change event
   */
  private handleChange(type: 'create' | 'change' | 'delete', uri: vscode.Uri): void {
    const filePath = uri.fsPath;

    // Check if file should be ignored
    if (this.shouldIgnore(filePath)) {
      return;
    }

    const event: FileChangeEvent = {
      type,
      uri: uri.toString(),
      path: filePath,
      timestamp: new Date(),
    };

    this.log(`File ${type}: ${path.basename(filePath)}`);

    // Notify all handlers
    for (const handler of this.changeHandlers) {
      try {
        handler(event);
      } catch (error) {
        console.error(`${LOG_PREFIX.ERROR} Error in file change handler:`, error);
      }
    }
  }

  /**
   * Check if a file path should be ignored
   */
  private shouldIgnore(filePath: string): boolean {
    const normalizedPath = filePath.replace(/\\/g, '/');
    
    for (const pattern of this.ignorePatterns) {
      // Convert glob pattern to simple string matching
      // Handle ** (any directories) and * (any characters)
      const regexPattern = pattern
        .replace(/\*\*/g, '.*')
        .replace(/\*/g, '[^/]*')
        .replace(/\//g, '[/\\\\]');
      
      const regex = new RegExp(regexPattern, 'i');
      
      if (regex.test(normalizedPath)) {
        return true;
      }
    }

    return false;
  }

  /**
   * Add ignore pattern
   */
  addIgnorePattern(pattern: string): void {
    if (!this.ignorePatterns.includes(pattern)) {
      this.ignorePatterns.push(pattern);
    }
  }

  /**
   * Remove ignore pattern
   */
  removeIgnorePattern(pattern: string): void {
    const index = this.ignorePatterns.indexOf(pattern);
    if (index !== -1) {
      this.ignorePatterns.splice(index, 1);
    }
  }

  /**
   * Set ignore patterns (replaces all existing)
   */
  setIgnorePatterns(patterns: string[]): void {
    this.ignorePatterns = [...patterns];
  }

  /**
   * Register handler for file changes
   */
  onChange(handler: ChangeHandler): void {
    this.changeHandlers.add(handler);
  }

  /**
   * Unregister file change handler
   */
  offChange(handler: ChangeHandler): void {
    this.changeHandlers.delete(handler);
  }

  /**
   * Recreate watchers with new patterns
   */
  updatePatterns(patterns: string[]): void {
    // Dispose existing watchers
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
    this.watchers = [];

    // Create new watchers
    for (const pattern of patterns) {
      this.createWatcher(pattern);
    }
  }

  /**
   * Get all watched files in the workspace
   */
  async getWatchedFiles(): Promise<vscode.Uri[]> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) {
      return [];
    }

    const files: vscode.Uri[] = [];
    
    for (const folder of workspaceFolders) {
      // Find files matching our patterns that aren't ignored
      const foundFiles = await vscode.workspace.findFiles(
        new vscode.RelativePattern(folder, '**/*.{py,js,ts,jsx,tsx,java,go,rs}'),
        new vscode.RelativePattern(folder, '{**/node_modules/**,**/.git/**,**/__pycache__/**}')
      );
      
      // Additional filtering for our ignore patterns
      for (const file of foundFiles) {
        if (!this.shouldIgnore(file.fsPath)) {
          files.push(file);
        }
      }
    }

    return files;
  }

  /**
   * Log message to output channel if available
   */
  private log(message: string): void {
    if (this.outputChannel) {
      this.outputChannel.appendLine(`${LOG_PREFIX.DEBUG} ${message}`);
    }
  }

  /**
   * Dispose all resources
   */
  dispose(): void {
    for (const watcher of this.watchers) {
      watcher.dispose();
    }
    this.watchers = [];
    this.changeHandlers.clear();
  }
}
