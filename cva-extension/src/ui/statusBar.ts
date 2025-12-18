/**
 * Status Bar Provider
 * 
 * Manages the CVA status bar item showing current verification status.
 */

import * as vscode from 'vscode';
import { StatusBarState } from '../types';
import { STATUS_ICONS, COMMANDS, EXTENSION_NAME } from '../constants';

export class StatusBarProvider implements vscode.Disposable {
  private statusBarItem: vscode.StatusBarItem;
  private currentState: StatusBarState = 'idle';
  private pendingCount: number = 0;

  constructor() {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.statusBarItem.name = EXTENSION_NAME;
    this.statusBarItem.command = COMMANDS.SHOW_OUTPUT;
    this.update('idle');
    this.statusBarItem.show();
  }

  /**
   * Update status bar state
   */
  update(state: StatusBarState, pendingCount?: number): void {
    this.currentState = state;
    
    if (pendingCount !== undefined) {
      this.pendingCount = pendingCount;
    }

    const icon = STATUS_ICONS[state.toUpperCase() as keyof typeof STATUS_ICONS] || STATUS_ICONS.IDLE;
    
    // Build text with optional pending count
    let text = `${icon} CVA`;
    if (state === 'watching' && this.pendingCount > 0) {
      text = `${icon} CVA (${this.pendingCount})`;
    }

    this.statusBarItem.text = text;
    this.statusBarItem.tooltip = this.getTooltip(state);
    
    // Set background color for important states
    switch (state) {
      case 'failed':
      case 'error':
        this.statusBarItem.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.warningBackground'
        );
        break;
      case 'passed':
        this.statusBarItem.backgroundColor = undefined;
        break;
      default:
        this.statusBarItem.backgroundColor = undefined;
    }

    // Update command based on state
    if (state === 'disabled') {
      this.statusBarItem.command = COMMANDS.START;
    } else if (state === 'error') {
      this.statusBarItem.command = COMMANDS.RESTART;
    } else {
      this.statusBarItem.command = COMMANDS.SHOW_OUTPUT;
    }
  }

  /**
   * Get tooltip text for state
   */
  private getTooltip(state: StatusBarState): string {
    const tooltips: Record<StatusBarState, string> = {
      idle: 'CVA: Ready - Click to show output',
      starting: 'CVA: Starting backend...',
      watching: this.pendingCount > 0 
        ? `CVA: Watching (${this.pendingCount} file(s) pending)` 
        : 'CVA: Watching for changes',
      verifying: 'CVA: Verifying code...',
      passed: 'CVA: All checks passed ✓',
      failed: 'CVA: Violations found - Click to show output',
      error: 'CVA: Error - Click to restart',
      disabled: 'CVA: Disabled - Click to start',
    };
    return tooltips[state];
  }

  /**
   * Get current state
   */
  getState(): StatusBarState {
    return this.currentState;
  }

  /**
   * Update pending file count
   */
  setPendingCount(count: number): void {
    this.pendingCount = count;
    // Refresh display if in watching state
    if (this.currentState === 'watching') {
      this.update('watching');
    }
  }

  /**
   * Show a temporary message in the status bar
   */
  showMessage(message: string, durationMs: number = 3000): void {
    const originalText = this.statusBarItem.text;
    const originalTooltip = this.statusBarItem.tooltip;
    
    this.statusBarItem.text = `$(info) ${message}`;
    this.statusBarItem.tooltip = message;

    setTimeout(() => {
      this.statusBarItem.text = originalText;
      this.statusBarItem.tooltip = originalTooltip;
    }, durationMs);
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.statusBarItem.dispose();
  }
}
