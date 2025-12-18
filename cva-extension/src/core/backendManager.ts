/**
 * Backend Manager
 * 
 * Manages the CVA Python backend as a subprocess.
 * Handles starting, stopping, health checks, and auto-restart on crash.
 */

import { spawn, ChildProcess } from 'child_process';
import * as vscode from 'vscode';
import * as fs from 'fs';
import { BackendStatus } from '../types';
import {
  DEFAULTS,
  LOG_PREFIX,
  API_ENDPOINTS,
} from '../constants';

type BackendEventType = 'started' | 'stopped' | 'ready' | 'error' | 'restart' | 'output';
type BackendEventCallback = (...args: unknown[]) => void;

export class BackendManager {
  private process: ChildProcess | null = null;
  private outputChannel: vscode.OutputChannel;
  private isReady: boolean = false;
  private restartCount: number = 0;
  private maxRestarts: number;
  private port: number;
  private healthCheckTimer: NodeJS.Timeout | null = null;
  private startedAt: Date | null = null;
  private lastError: string | null = null;
  private eventListeners: Map<BackendEventType, Set<BackendEventCallback>> = new Map();
  private isShuttingDown: boolean = false;

  constructor(
    outputChannel: vscode.OutputChannel,
    maxRestarts: number = DEFAULTS.MAX_RESTART_ATTEMPTS
  ) {
    this.outputChannel = outputChannel;
    this.maxRestarts = maxRestarts;
    this.port = DEFAULTS.BACKEND_PORT;
  }

  /**
   * Start the CVA backend server
   */
  async start(
    cvaPath: string,
    pythonPath: string = DEFAULTS.PYTHON_PATH,
    port: number = DEFAULTS.BACKEND_PORT
  ): Promise<boolean> {
    this.port = port;
    this.isShuttingDown = false;

    // Validate CVA path exists
    if (!fs.existsSync(cvaPath)) {
      const error = `CVA backend path does not exist: ${cvaPath}`;
      this.log('error', error);
      this.lastError = error;
      this.emit('error', new Error(error));
      return false;
    }

    // Check if already running
    if (this.process && !this.process.killed) {
      this.log('warn', 'Backend is already running');
      return true;
    }

    this.log('info', `Starting CVA backend...`);
    this.log('info', `  Python: ${pythonPath}`);
    this.log('info', `  Path: ${cvaPath}`);
    this.log('info', `  Port: ${port}`);

    try {
      // Spawn the uvicorn process
      this.process = spawn(
        pythonPath,
        [
          '-m', 'uvicorn',
          'modules.api:app',
          '--host', '127.0.0.1',
          '--port', port.toString(),
          '--log-level', 'info',
        ],
        {
          cwd: cvaPath,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
          },
          shell: process.platform === 'win32', // Use shell on Windows
          windowsHide: true,
        }
      );

      this.setupProcessHandlers();
      this.emit('started');

      // Wait for backend to be ready
      const ready = await this.waitForReady(DEFAULTS.BACKEND_STARTUP_TIMEOUT_MS);
      
      if (ready) {
        this.isReady = true;
        this.startedAt = new Date();
        this.restartCount = 0;
        this.lastError = null;
        this.log('info', `Backend is ready on port ${port}`);
        this.emit('ready');
        this.startHealthCheckTimer();
        return true;
      } else {
        this.log('error', 'Backend failed to become ready within timeout');
        this.stop();
        return false;
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      this.log('error', `Failed to start backend: ${errorMessage}`);
      this.lastError = errorMessage;
      this.emit('error', error);
      return false;
    }
  }

  /**
   * Stop the backend server
   */
  stop(): void {
    this.isShuttingDown = true;
    this.stopHealthCheckTimer();

    if (this.process) {
      this.log('info', 'Stopping backend...');
      
      // Try graceful shutdown first
      if (process.platform === 'win32') {
        // On Windows, use taskkill to terminate the process tree
        spawn('taskkill', ['/pid', this.process.pid!.toString(), '/f', '/t'], {
          windowsHide: true,
        });
      } else {
        // On Unix, send SIGTERM
        this.process.kill('SIGTERM');
        
        // Force kill after 5 seconds if still running
        setTimeout(() => {
          if (this.process && !this.process.killed) {
            this.process.kill('SIGKILL');
          }
        }, 5000);
      }

      this.process = null;
    }

    this.isReady = false;
    this.emit('stopped');
    this.log('info', 'Backend stopped');
  }

  /**
   * Restart the backend
   */
  async restart(cvaPath: string, pythonPath: string, port: number): Promise<boolean> {
    this.log('info', 'Restarting backend...');
    this.stop();
    
    // Wait a bit for port to be released
    await this.delay(1000);
    
    return this.start(cvaPath, pythonPath, port);
  }

  /**
   * Check if backend is currently running
   */
  isRunning(): boolean {
    return this.process !== null && !this.process.killed && this.isReady;
  }

  /**
   * Get current backend status
   */
  getStatus(): BackendStatus {
    return {
      running: this.isRunning(),
      pid: this.process?.pid,
      port: this.port,
      restartCount: this.restartCount,
      lastError: this.lastError ?? undefined,
      startedAt: this.startedAt ?? undefined,
    };
  }

  /**
   * Check backend health via HTTP
   */
  async checkHealth(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => controller.abort(),
        DEFAULTS.HEALTH_CHECK_TIMEOUT_MS
      );

      const response = await fetch(
        `http://127.0.0.1:${this.port}${API_ENDPOINTS.HEALTH}`,
        {
          method: 'GET',
          signal: controller.signal,
        }
      );

      clearTimeout(timeoutId);
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Add event listener
   */
  on(event: BackendEventType, callback: BackendEventCallback): void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, new Set());
    }
    this.eventListeners.get(event)!.add(callback);
  }

  /**
   * Remove event listener
   */
  off(event: BackendEventType, callback: BackendEventCallback): void {
    this.eventListeners.get(event)?.delete(callback);
  }

  /**
   * Dispose resources
   */
  dispose(): void {
    this.stop();
    this.eventListeners.clear();
  }

  // =========================================================================
  // Private Methods
  // =========================================================================

  private setupProcessHandlers(): void {
    if (!this.process) return;

    this.process.stdout?.on('data', (data: Buffer) => {
      const output = data.toString().trim();
      if (output) {
        this.outputChannel.appendLine(output);
        this.emit('output', output);
      }
    });

    this.process.stderr?.on('data', (data: Buffer) => {
      const output = data.toString().trim();
      if (output) {
        this.outputChannel.appendLine(`[stderr] ${output}`);
        this.emit('output', output);
      }
    });

    this.process.on('error', (error) => {
      this.log('error', `Process error: ${error.message}`);
      this.lastError = error.message;
      this.emit('error', error);
    });

    this.process.on('exit', (code, signal) => {
      this.isReady = false;
      
      if (this.isShuttingDown) {
        this.log('info', `Backend exited (shutdown)`);
        return;
      }

      if (code !== 0) {
        this.log('warn', `Backend exited with code ${code}, signal: ${signal}`);
        this.handleUnexpectedExit();
      }
    });
  }

  private async handleUnexpectedExit(): Promise<void> {
    if (this.isShuttingDown) return;

    if (this.restartCount < this.maxRestarts) {
      this.restartCount++;
      this.log('info', `Attempting restart ${this.restartCount}/${this.maxRestarts}...`);
      this.emit('restart', this.restartCount);
      
      // Exponential backoff
      const delay = Math.min(1000 * Math.pow(2, this.restartCount - 1), 10000);
      await this.delay(delay);
      
      // Note: We can't restart without the paths, so emit error
      // The extension.ts will need to handle the restart
      this.emit('error', new Error('Backend crashed, restart needed'));
    } else {
      this.log('error', `Max restart attempts (${this.maxRestarts}) exceeded`);
      this.emit('error', new Error('Max restart attempts exceeded'));
    }
  }

  private async waitForReady(timeoutMs: number): Promise<boolean> {
    const startTime = Date.now();
    const pollInterval = 500;

    while (Date.now() - startTime < timeoutMs) {
      if (await this.checkHealth()) {
        return true;
      }
      await this.delay(pollInterval);
    }

    return false;
  }

  private startHealthCheckTimer(): void {
    this.stopHealthCheckTimer();
    
    this.healthCheckTimer = setInterval(async () => {
      if (!await this.checkHealth()) {
        this.log('warn', 'Health check failed');
        this.isReady = false;
        // Don't emit error here, just log - the process exit handler will deal with it
      }
    }, DEFAULTS.HEALTH_CHECK_INTERVAL_MS);
  }

  private stopHealthCheckTimer(): void {
    if (this.healthCheckTimer) {
      clearInterval(this.healthCheckTimer);
      this.healthCheckTimer = null;
    }
  }

  private emit(event: BackendEventType, ...args: unknown[]): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      for (const callback of listeners) {
        try {
          callback(...args);
        } catch (error) {
          console.error(`Error in ${event} listener:`, error);
        }
      }
    }
  }

  private log(level: 'info' | 'warn' | 'error', message: string): void {
    const prefix = level === 'error' ? LOG_PREFIX.ERROR : 
                   level === 'warn' ? LOG_PREFIX.WARN : 
                   LOG_PREFIX.INFO;
    this.outputChannel.appendLine(`${prefix} ${message}`);
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
