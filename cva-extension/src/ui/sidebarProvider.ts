/**
 * Sidebar Provider
 * 
 * TreeDataProvider for the CVA Verdicts sidebar view.
 * Shows verdict summary, violations, and recommendations.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { VerdictResponse, Violation, VerdictTreeItemData } from '../types';

export class SidebarProvider implements vscode.TreeDataProvider<VerdictTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData = new vscode.EventEmitter<VerdictTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private verdictResponse: VerdictResponse | null = null;
  private errorMessage: string | null = null;
  private isLoading: boolean = false;

  constructor() {}

  /**
   * Update the view with new verdict data
   */
  update(verdict: VerdictResponse): void {
    this.verdictResponse = verdict;
    this.errorMessage = null;
    this.isLoading = false;
    this._onDidChangeTreeData.fire();
  }

  /**
   * Show loading state
   */
  setLoading(loading: boolean): void {
    this.isLoading = loading;
    this._onDidChangeTreeData.fire();
  }

  /**
   * Show error state
   */
  setError(message: string): void {
    this.errorMessage = message;
    this.isLoading = false;
    this._onDidChangeTreeData.fire();
  }

  /**
   * Clear the view
   */
  clear(): void {
    this.verdictResponse = null;
    this.errorMessage = null;
    this.isLoading = false;
    this._onDidChangeTreeData.fire();
  }

  /**
   * Refresh the view
   */
  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  // TreeDataProvider implementation

  getTreeItem(element: VerdictTreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: VerdictTreeItem): VerdictTreeItem[] {
    // Loading state
    if (this.isLoading) {
      return [new VerdictTreeItem({
        type: 'info',
        label: '$(sync~spin) Verifying...',
        description: 'Please wait',
        collapsible: false,
      })];
    }

    // Error state
    if (this.errorMessage) {
      return [new VerdictTreeItem({
        type: 'error',
        label: '$(error) Error',
        description: this.errorMessage,
        tooltip: this.errorMessage,
        icon: 'error',
        collapsible: false,
      })];
    }

    // No verdict yet
    if (!this.verdictResponse) {
      return [new VerdictTreeItem({
        type: 'info',
        label: 'No verification run yet',
        description: 'Save a file or run CVA: Verify',
        tooltip: 'Use Ctrl+Shift+V to verify the workspace',
        icon: 'info',
        collapsible: false,
      })];
    }

    // Root level - show summary
    if (!element) {
      return this.getRootItems();
    }

    // Children of expandable items
    return this.getChildItems(element);
  }

  /**
   * Get root level items (verdict summary)
   */
  private getRootItems(): VerdictTreeItem[] {
    const verdict = this.verdictResponse!;
    const items: VerdictTreeItem[] = [];

    // Verdict summary
    const verdictIcon = verdict.verdict === 'PASS' ? 'check' : 
                        verdict.verdict === 'FAIL' ? 'warning' : 'question';

    items.push(new VerdictTreeItem({
      type: 'verdict-summary',
      label: `Verdict: ${verdict.verdict}`,
      description: `${(verdict.confidence * 100).toFixed(0)}% confidence`,
      tooltip: `Tribunal verdict: ${verdict.verdict}\nConfidence: ${(verdict.confidence * 100).toFixed(1)}%`,
      icon: verdictIcon,
      collapsible: false,
    }));

    // Judge count if available
    if (verdict.judge_count) {
      items.push(new VerdictTreeItem({
        type: 'info',
        label: `${verdict.judge_count} judges participated`,
        icon: 'organization',
        collapsible: false,
      }));
    }

    // Violations section
    if (verdict.violations.length > 0) {
      items.push(new VerdictTreeItem({
        type: 'violations-header',
        label: `Violations (${verdict.violations.length})`,
        icon: 'error',
        collapsible: true,
      }));
    }

    // Recommendations section
    if (verdict.recommendations.length > 0) {
      items.push(new VerdictTreeItem({
        type: 'recommendations-header',
        label: `Recommendations (${verdict.recommendations.length})`,
        icon: 'lightbulb',
        collapsible: true,
      }));
    }

    return items;
  }

  /**
   * Get child items for expandable parents
   */
  private getChildItems(parent: VerdictTreeItem): VerdictTreeItem[] {
    const verdict = this.verdictResponse!;

    switch (parent.data.type) {
      case 'violations-header':
        return verdict.violations.map(v => this.createViolationItem(v));

      case 'recommendations-header':
        return verdict.recommendations.map((r, i) => new VerdictTreeItem({
          type: 'recommendation',
          label: `${i + 1}. ${this.truncate(r, 60)}`,
          tooltip: r,
          recommendation: r,
          icon: 'lightbulb-autofix',
          collapsible: false,
        }));

      default:
        return [];
    }
  }

  /**
   * Create a tree item for a violation
   */
  private createViolationItem(violation: Violation): VerdictTreeItem {
    const fileName = path.basename(violation.file);
    const severityIcon = violation.severity === 'error' ? 'error' :
                         violation.severity === 'warning' ? 'warning' : 'info';

    return new VerdictTreeItem({
      type: 'violation',
      label: `${fileName}:${violation.line}`,
      description: violation.invariant,
      tooltip: `${violation.invariant}\n\n${violation.message}${violation.suggestion ? '\n\nSuggestion: ' + violation.suggestion : ''}`,
      violation,
      icon: severityIcon,
      collapsible: false,
    });
  }

  /**
   * Truncate text with ellipsis
   */
  private truncate(text: string, maxLength: number): string {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
  }

  /**
   * Get current verdict
   */
  getVerdict(): VerdictResponse | null {
    return this.verdictResponse;
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this._onDidChangeTreeData.dispose();
  }
}

/**
 * Tree item representing a verdict element
 */
class VerdictTreeItem extends vscode.TreeItem {
  public readonly data: VerdictTreeItemData;

  constructor(data: VerdictTreeItemData) {
    super(
      data.label,
      data.collapsible 
        ? vscode.TreeItemCollapsibleState.Expanded 
        : vscode.TreeItemCollapsibleState.None
    );

    this.data = data;
    this.description = data.description;
    this.tooltip = data.tooltip;

    // Set icon
    if (data.icon) {
      this.iconPath = new vscode.ThemeIcon(data.icon);
    }

    // Set command for violations - open file at line
    if (data.type === 'violation' && data.violation) {
      this.command = {
        command: 'vscode.open',
        title: 'Open File',
        arguments: [
          vscode.Uri.file(data.violation.file),
          {
            selection: new vscode.Range(
              Math.max(0, data.violation.line - 1),
              0,
              Math.max(0, data.violation.line - 1),
              0
            )
          }
        ]
      };
    }

    // Context value for menus
    this.contextValue = data.type;
  }
}
