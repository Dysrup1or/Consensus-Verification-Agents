/**
 * Backend Client
 * 
 * HTTP and WebSocket client for communicating with the CVA backend.
 * Supports both local and cloud modes.
 */

import WebSocket from 'ws';
import {
  RunRequest,
  RunResponse,
  StatusResponse,
  VerdictResponse,
  WebSocketMessage,
  Result,
} from '../types';
import {
  DEFAULTS,
  API_ENDPOINTS,
  RETRY,
  LOG_PREFIX,
} from '../constants';

type MessageHandler = (message: WebSocketMessage) => void;
type ErrorHandler = (error: Error) => void;
type ConnectionHandler = () => void;

export interface BackendClientConfig {
  /** Use cloud backend instead of local */
  useCloud: boolean;
  /** Cloud backend URL (required if useCloud is true) */
  cloudUrl?: string;
  /** API token for cloud authentication */
  apiToken?: string;
  /** Local backend port (used if useCloud is false) */
  port?: number;
}

export class BackendClient {
  private baseUrl: string;
  private wsUrl: string;
  private apiToken: string | null = null;
  private useCloud: boolean = false;
  private ws: WebSocket | null = null;
  private wsReconnectTimer: NodeJS.Timeout | null = null;
  private wsReconnectAttempts: number = 0;
  private messageHandlers: Set<MessageHandler> = new Set();
  private errorHandlers: Set<ErrorHandler> = new Set();
  private connectHandlers: Set<ConnectionHandler> = new Set();
  private disconnectHandlers: Set<ConnectionHandler> = new Set();
  private isConnecting: boolean = false;
  private shouldReconnect: boolean = true;

  constructor(portOrConfig: number | BackendClientConfig = DEFAULTS.BACKEND_PORT) {
    if (typeof portOrConfig === 'number') {
      // Legacy: local mode with port
      this.baseUrl = `http://127.0.0.1:${portOrConfig}`;
      this.wsUrl = `ws://127.0.0.1:${portOrConfig}${API_ENDPOINTS.WEBSOCKET}`;
      this.useCloud = false;
    } else {
      // New: config object supporting cloud mode
      this.useCloud = portOrConfig.useCloud;
      this.apiToken = portOrConfig.apiToken || null;
      
      if (this.useCloud && portOrConfig.cloudUrl) {
        // Cloud mode
        const cloudUrl = portOrConfig.cloudUrl.replace(/\/$/, ''); // Remove trailing slash
        this.baseUrl = cloudUrl;
        // Cloud WebSocket: convert https to wss, http to ws
        this.wsUrl = cloudUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:') + API_ENDPOINTS.WEBSOCKET;
      } else {
        // Local mode
        const port = portOrConfig.port || DEFAULTS.BACKEND_PORT;
        this.baseUrl = `http://127.0.0.1:${port}`;
        this.wsUrl = `ws://127.0.0.1:${port}${API_ENDPOINTS.WEBSOCKET}`;
      }
    }
  }

  /**
   * Check if using cloud backend
   */
  isCloudMode(): boolean {
    return this.useCloud;
  }

  /**
   * Configure for cloud mode
   */
  setCloudMode(cloudUrl: string, apiToken: string): void {
    const wasConnected = this.ws?.readyState === WebSocket.OPEN;
    
    this.useCloud = true;
    this.apiToken = apiToken;
    const cleanUrl = cloudUrl.replace(/\/$/, '');
    this.baseUrl = cleanUrl;
    this.wsUrl = cleanUrl.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:') + API_ENDPOINTS.WEBSOCKET;
    
    if (wasConnected) {
      this.disconnectWebSocket();
      this.connectWebSocket();
    }
  }

  /**
   * Configure for local mode
   */
  setLocalMode(port: number): void {
    const wasConnected = this.ws?.readyState === WebSocket.OPEN;
    
    this.useCloud = false;
    this.apiToken = null;
    this.baseUrl = `http://127.0.0.1:${port}`;
    this.wsUrl = `ws://127.0.0.1:${port}${API_ENDPOINTS.WEBSOCKET}`;
    
    if (wasConnected) {
      this.disconnectWebSocket();
      this.connectWebSocket();
    }
  }

  /**
   * Update the port (e.g., after configuration change) - local mode only
   */
  setPort(port: number): void {
    if (this.useCloud) {
      return; // Ignore port changes in cloud mode
    }
    this.setLocalMode(port);
  }

  // =========================================================================
  // HTTP Methods
  // =========================================================================

  /**
   * Check if the backend is healthy
   */
  async isHealthy(): Promise<boolean> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(
        () => controller.abort(),
        DEFAULTS.HEALTH_CHECK_TIMEOUT_MS
      );

      const headers: Record<string, string> = {};
      if (this.useCloud && this.apiToken) {
        headers['Authorization'] = `Bearer ${this.apiToken}`;
      }

      const response = await fetch(`${this.baseUrl}${API_ENDPOINTS.HEALTH}`, {
        method: 'GET',
        signal: controller.signal,
        headers,
      });

      clearTimeout(timeoutId);
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Trigger a verification run
   */
  async triggerRun(request: RunRequest): Promise<Result<RunResponse>> {
    return this.post<RunResponse>(API_ENDPOINTS.RUN, request);
  }

  /**
   * Get status of a verification run
   */
  async getStatus(runId: string): Promise<Result<StatusResponse>> {
    return this.get<StatusResponse>(`${API_ENDPOINTS.STATUS}/${runId}`);
  }

  /**
   * Get verdict for a completed run
   */
  async getVerdict(runId: string): Promise<Result<VerdictResponse>> {
    return this.get<VerdictResponse>(`${API_ENDPOINTS.VERDICT}/${runId}`);
  }

  /**
   * Generic GET request with retry logic
   */
  private async get<T>(endpoint: string): Promise<Result<T>> {
    return this.request<T>('GET', endpoint);
  }

  /**
   * Generic POST request with retry logic
   */
  private async post<T>(endpoint: string, body: unknown): Promise<Result<T>> {
    return this.request<T>('POST', endpoint, body);
  }

  /**
   * Generic HTTP request with retry and timeout
   */
  private async request<T>(
    method: 'GET' | 'POST',
    endpoint: string,
    body?: unknown
  ): Promise<Result<T>> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < RETRY.MAX_ATTEMPTS; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(
          () => controller.abort(),
          DEFAULTS.HTTP_TIMEOUT_MS
        );

        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };

        // Add authorization header for cloud mode
        if (this.useCloud && this.apiToken) {
          headers['Authorization'] = `Bearer ${this.apiToken}`;
        }

        const options: RequestInit = {
          method,
          signal: controller.signal,
          headers,
        };

        if (body && method === 'POST') {
          options.body = JSON.stringify(body);
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, options);
        clearTimeout(timeoutId);

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json() as T;
        return { success: true, value: data };
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        
        // Don't retry on abort (timeout) or non-retryable errors
        if (lastError.name === 'AbortError') {
          return { success: false, error: new Error('Request timeout') };
        }

        // Exponential backoff before retry
        if (attempt < RETRY.MAX_ATTEMPTS - 1) {
          const delay = Math.min(
            RETRY.INITIAL_DELAY_MS * Math.pow(RETRY.MULTIPLIER, attempt),
            RETRY.MAX_DELAY_MS
          );
          await this.delay(delay);
        }
      }
    }

    return {
      success: false,
      error: lastError ?? new Error('Unknown error'),
    };
  }

  // =========================================================================
  // WebSocket Methods
  // =========================================================================

  /**
   * Connect to WebSocket for real-time updates
   */
  connectWebSocket(): void {
    if (this.isConnecting || this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.isConnecting = true;
    this.shouldReconnect = true;

    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.on('open', () => {
        this.isConnecting = false;
        this.wsReconnectAttempts = 0;
        console.log(`${LOG_PREFIX.INFO} WebSocket connected`);
        
        for (const handler of this.connectHandlers) {
          try {
            handler();
          } catch (error) {
            console.error('Error in connect handler:', error);
          }
        }
      });

      this.ws.on('message', (data: WebSocket.Data) => {
        try {
          const message = JSON.parse(data.toString()) as WebSocketMessage;
          
          for (const handler of this.messageHandlers) {
            try {
              handler(message);
            } catch (error) {
              console.error('Error in message handler:', error);
            }
          }
        } catch (error) {
          console.error(`${LOG_PREFIX.ERROR} Failed to parse WebSocket message:`, error);
        }
      });

      this.ws.on('error', (error: Error) => {
        this.isConnecting = false;
        console.error(`${LOG_PREFIX.ERROR} WebSocket error:`, error.message);
        
        for (const handler of this.errorHandlers) {
          try {
            handler(error);
          } catch (err) {
            console.error('Error in error handler:', err);
          }
        }
      });

      this.ws.on('close', (code: number, reason: Buffer) => {
        this.isConnecting = false;
        console.log(`${LOG_PREFIX.INFO} WebSocket closed: ${code} ${reason.toString()}`);
        
        for (const handler of this.disconnectHandlers) {
          try {
            handler();
          } catch (error) {
            console.error('Error in disconnect handler:', error);
          }
        }

        // Auto-reconnect with exponential backoff
        if (this.shouldReconnect && this.wsReconnectAttempts < DEFAULTS.WEBSOCKET_MAX_RECONNECT_ATTEMPTS) {
          this.wsReconnectAttempts++;
          const delay = Math.min(
            DEFAULTS.WEBSOCKET_RECONNECT_DELAY_MS * Math.pow(2, this.wsReconnectAttempts - 1),
            RETRY.MAX_DELAY_MS
          );
          
          console.log(`${LOG_PREFIX.INFO} Reconnecting in ${delay}ms (attempt ${this.wsReconnectAttempts})`);
          
          this.wsReconnectTimer = setTimeout(() => {
            this.connectWebSocket();
          }, delay);
        }
      });
    } catch (error) {
      this.isConnecting = false;
      console.error(`${LOG_PREFIX.ERROR} Failed to create WebSocket:`, error);
    }
  }

  /**
   * Disconnect WebSocket
   */
  disconnectWebSocket(): void {
    this.shouldReconnect = false;
    
    if (this.wsReconnectTimer) {
      clearTimeout(this.wsReconnectTimer);
      this.wsReconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.isConnecting = false;
    this.wsReconnectAttempts = 0;
  }

  /**
   * Check if WebSocket is connected
   */
  isWebSocketConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Send message via WebSocket
   */
  sendWebSocketMessage(message: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message));
        return true;
      } catch (error) {
        console.error(`${LOG_PREFIX.ERROR} Failed to send WebSocket message:`, error);
        return false;
      }
    }
    return false;
  }

  // =========================================================================
  // Event Handlers
  // =========================================================================

  /**
   * Register handler for WebSocket messages
   */
  onMessage(handler: MessageHandler): void {
    this.messageHandlers.add(handler);
  }

  /**
   * Unregister message handler
   */
  offMessage(handler: MessageHandler): void {
    this.messageHandlers.delete(handler);
  }

  /**
   * Register handler for WebSocket errors
   */
  onError(handler: ErrorHandler): void {
    this.errorHandlers.add(handler);
  }

  /**
   * Unregister error handler
   */
  offError(handler: ErrorHandler): void {
    this.errorHandlers.delete(handler);
  }

  /**
   * Register handler for WebSocket connect
   */
  onConnect(handler: ConnectionHandler): void {
    this.connectHandlers.add(handler);
  }

  /**
   * Unregister connect handler
   */
  offConnect(handler: ConnectionHandler): void {
    this.connectHandlers.delete(handler);
  }

  /**
   * Register handler for WebSocket disconnect
   */
  onDisconnect(handler: ConnectionHandler): void {
    this.disconnectHandlers.add(handler);
  }

  /**
   * Unregister disconnect handler
   */
  offDisconnect(handler: ConnectionHandler): void {
    this.disconnectHandlers.delete(handler);
  }

  // =========================================================================
  // Utility Methods
  // =========================================================================

  /**
   * Get the docs URL for opening in browser
   */
  getDocsUrl(): string {
    return `${this.baseUrl}${API_ENDPOINTS.DOCS}`;
  }

  /**
   * Dispose all resources
   */
  dispose(): void {
    this.disconnectWebSocket();
    this.messageHandlers.clear();
    this.errorHandlers.clear();
    this.connectHandlers.clear();
    this.disconnectHandlers.clear();
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
