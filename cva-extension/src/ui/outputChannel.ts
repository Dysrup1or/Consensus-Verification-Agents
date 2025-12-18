/**
 * Output Channel Provider
 * 
 * Manages the CVA output channel for logging.
 */

import * as vscode from 'vscode';
import { OUTPUT_CHANNEL_NAME, LOG_PREFIX } from '../constants';

export class OutputChannelProvider implements vscode.Disposable {
  private outputChannel: vscode.OutputChannel;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel(OUTPUT_CHANNEL_NAME);
  }

  /**
   * Get the underlying output channel
   */
  getChannel(): vscode.OutputChannel {
    return this.outputChannel;
  }

  /**
   * Log an info message
   */
  info(message: string): void {
    this.log(LOG_PREFIX.INFO, message);
  }

  /**
   * Log a warning message
   */
  warn(message: string): void {
    this.log(LOG_PREFIX.WARN, message);
  }

  /**
   * Log an error message
   */
  error(message: string): void {
    this.log(LOG_PREFIX.ERROR, message);
  }

  /**
   * Log a debug message
   */
  debug(message: string): void {
    this.log(LOG_PREFIX.DEBUG, message);
  }

  /**
   * Log a message with prefix
   */
  private log(prefix: string, message: string): void {
    const timestamp = new Date().toISOString().substring(11, 23);
    this.outputChannel.appendLine(`[${timestamp}] ${prefix} ${message}`);
  }

  /**
   * Append raw text without prefix
   */
  append(text: string): void {
    this.outputChannel.append(text);
  }

  /**
   * Append line without prefix
   */
  appendLine(line: string): void {
    this.outputChannel.appendLine(line);
  }

  /**
   * Show the output channel
   */
  show(preserveFocus: boolean = true): void {
    this.outputChannel.show(preserveFocus);
  }

  /**
   * Hide the output channel
   */
  hide(): void {
    this.outputChannel.hide();
  }

  /**
   * Clear the output channel
   */
  clear(): void {
    this.outputChannel.clear();
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.outputChannel.dispose();
  }
}
