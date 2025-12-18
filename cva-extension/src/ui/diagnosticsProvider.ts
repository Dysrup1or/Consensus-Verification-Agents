/**
 * Diagnostics Provider
 * 
 * Converts CVA violations to VS Code diagnostics (squiggly lines in editor).
 */

import * as vscode from 'vscode';
import { Violation, ViolationSeverity, VerdictResponse } from '../types';
import { DIAGNOSTIC_SOURCE, DIAGNOSTIC_COLLECTION_NAME } from '../constants';

export class DiagnosticsProvider implements vscode.Disposable {
  private collection: vscode.DiagnosticCollection;

  constructor() {
    this.collection = vscode.languages.createDiagnosticCollection(DIAGNOSTIC_COLLECTION_NAME);
  }

  /**
   * Update diagnostics from a verdict response
   */
  updateFromVerdict(verdict: VerdictResponse): void {
    this.update(verdict.violations);
  }

  /**
   * Update diagnostics from violations array
   */
  update(violations: Violation[]): void {
    // Clear existing diagnostics
    this.collection.clear();

    if (violations.length === 0) {
      return;
    }

    // Group violations by file
    const byFile = new Map<string, Violation[]>();
    
    for (const violation of violations) {
      const existing = byFile.get(violation.file) || [];
      existing.push(violation);
      byFile.set(violation.file, existing);
    }

    // Create diagnostics for each file
    for (const [file, fileViolations] of byFile) {
      try {
        const uri = vscode.Uri.file(file);
        const diagnostics = fileViolations.map(v => this.toDiagnostic(v));
        this.collection.set(uri, diagnostics);
      } catch (error) {
        console.error(`Failed to create diagnostics for ${file}:`, error);
      }
    }
  }

  /**
   * Convert a violation to a VS Code diagnostic
   */
  private toDiagnostic(violation: Violation): vscode.Diagnostic {
    // Create range - try to get accurate column, default to line-wide
    const line = Math.max(0, violation.line - 1); // Convert to 0-based
    const column = violation.column || 0;
    
    // Create a range that spans a reasonable portion of the line
    const range = new vscode.Range(
      line,
      column,
      line,
      column + 100 // Will be clamped to line length by VS Code
    );

    // Map severity
    const severity = this.mapSeverity(violation.severity);

    // Create diagnostic
    const diagnostic = new vscode.Diagnostic(
      range,
      this.formatMessage(violation),
      severity
    );

    // Add metadata
    diagnostic.source = DIAGNOSTIC_SOURCE;
    diagnostic.code = violation.invariant;

    // Add related information if we have a code snippet
    if (violation.code_snippet) {
      diagnostic.relatedInformation = [
        new vscode.DiagnosticRelatedInformation(
          new vscode.Location(vscode.Uri.file(violation.file), range),
          `Code: ${violation.code_snippet}`
        )
      ];
    }

    // Add tags for suggestions
    if (violation.suggestion) {
      // Store suggestion for potential quick fix
      (diagnostic as DiagnosticWithSuggestion).suggestion = violation.suggestion;
    }

    return diagnostic;
  }

  /**
   * Map CVA severity to VS Code severity
   */
  private mapSeverity(severity: ViolationSeverity): vscode.DiagnosticSeverity {
    switch (severity) {
      case 'error':
        return vscode.DiagnosticSeverity.Error;
      case 'warning':
        return vscode.DiagnosticSeverity.Warning;
      case 'info':
        return vscode.DiagnosticSeverity.Information;
      case 'hint':
        return vscode.DiagnosticSeverity.Hint;
      default:
        return vscode.DiagnosticSeverity.Warning;
    }
  }

  /**
   * Format violation message for display
   */
  private formatMessage(violation: Violation): string {
    let message = `[${violation.invariant}] ${violation.message}`;
    
    if (violation.suggestion) {
      message += `\n\nSuggestion: ${violation.suggestion}`;
    }
    
    return message;
  }

  /**
   * Get all current diagnostics
   */
  getAllDiagnostics(): Map<string, vscode.Diagnostic[]> {
    const result = new Map<string, vscode.Diagnostic[]>();
    
    this.collection.forEach((uri, diagnostics) => {
      result.set(uri.fsPath, [...diagnostics]);
    });
    
    return result;
  }

  /**
   * Get diagnostic count
   */
  getCount(): number {
    let count = 0;
    this.collection.forEach((_, diagnostics) => {
      count += diagnostics.length;
    });
    return count;
  }

  /**
   * Clear all diagnostics
   */
  clear(): void {
    this.collection.clear();
  }

  /**
   * Clear diagnostics for a specific file
   */
  clearFile(filePath: string): void {
    const uri = vscode.Uri.file(filePath);
    this.collection.delete(uri);
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.collection.dispose();
  }
}

/**
 * Extended diagnostic with suggestion field
 */
interface DiagnosticWithSuggestion extends vscode.Diagnostic {
  suggestion?: string;
}
