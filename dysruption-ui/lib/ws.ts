import { WSMessage } from './types';

export type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected';

type MessageHandler = (event: WSMessage) => void;
type StatusHandler = (status: ConnectionStatus, detail?: string) => void;

const isDev = process.env.NODE_ENV === 'development';
const isProd = process.env.NODE_ENV === 'production';

/**
 * WebSocket client for CVA real-time updates.
 * Connects to ws://localhost:8001/ws/{run_id}
 */
export class CVAWebSocket {
  // CRITICAL: Default to 8001 - must match backend port!
  private baseUrl: string;
  private wsToken: string | null = null;
  
  private static getDefaultWsUrl(): string {
    // Try environment variable first
    if (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_WS_URL) {
      const envUrl = process.env.NEXT_PUBLIC_WS_URL;
      return envUrl.endsWith('/ws') ? envUrl : `${envUrl}/ws`;
    }
    // Derive from API URL if available
    if (typeof process !== 'undefined' && process.env?.NEXT_PUBLIC_API_URL) {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL;
      const wsUrl = apiUrl.replace(/^http/, 'ws');
      return `${wsUrl}/ws`;
    }
    // Default fallback - MUST be 8001!
    return 'ws://localhost:8001/ws';
  }
  private ws: WebSocket | null = null;
  private runId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private messageHandlers: MessageHandler[] = [];
  private statusHandlers: StatusHandler[] = [];
  private shouldReconnect = true;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || CVAWebSocket.getDefaultWsUrl();
  }

  /**
   * Start WebSocket connection for a specific run.
   */
  start(runId: string, opts?: { wsToken?: string }) {
    this.runId = runId;
    this.shouldReconnect = true;
    this.reconnectAttempts = 0;
    this.wsToken = opts?.wsToken ?? null;
    this.connect();
  }

  onMessage(fn: MessageHandler) {
    this.messageHandlers.push(fn);
  }

  onStatusChange(fn: StatusHandler) {
    this.statusHandlers.push(fn);
  }

  private notifyStatus(status: ConnectionStatus, detail?: string) {
    this.statusHandlers.forEach((h) => h(status, detail));
  }

  private connect() {
    if (!this.runId) return;

    const urlObj = new URL(`${this.baseUrl}/${this.runId}`);
    if (isProd) {
      if (!this.wsToken) {
        this.notifyStatus('disconnected', 'missing_ws_token');
        return;
      }
      urlObj.searchParams.set('ws_token', this.wsToken);
    }

    // Avoid logging secrets.
    console.log(`🌐 [WS] Connecting to: ${urlObj.origin}${urlObj.pathname}`);
    this.notifyStatus('connecting');

    try {
      this.ws = new WebSocket(urlObj.toString());

      this.ws.onopen = () => {
        console.log(`✅ [WS] Connected`);
        this.reconnectAttempts = 0;
        this.notifyStatus('connected');
        this.startPing();
      };

      this.ws.onmessage = (e) => {
        try {
          const msg: WSMessage = JSON.parse(e.data);
          console.log(`📨 [WS] Received:`, msg.type, msg);
          // Handle pong silently
          if (msg.type === 'pong' || msg.type === 'ping') return;
          this.messageHandlers.forEach((h) => h(msg));
        } catch (err) {
          console.error(`❌ [WS] Parse error:`, err);
        }
      };

      this.ws.onclose = (event) => {
        console.log(`🔌 [WS] Closed: code=${event.code}, reason=${event.reason}`);
        this.stopPing();
        this.notifyStatus('disconnected');
        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (event) => {
        console.error(`❌ [WS] Error:`, event);
        this.ws?.close();
      };
    } catch (e) {
      console.error(`❌ [WS] Connection exception:`, e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(30000, Math.pow(2, this.reconnectAttempts) * 1000 + Math.random() * 500);
    this.notifyStatus('reconnecting', `attempt ${this.reconnectAttempts}`);
    setTimeout(() => this.connect(), delay);
  }

  private startPing() {
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 25000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  manualReconnect() {
    this.reconnectAttempts = 0;
    this.ws?.close();
    if (this.runId) this.connect();
  }

  stop() {
    this.shouldReconnect = false;
    this.stopPing();
    this.ws?.close();
    this.ws = null;
    this.runId = null;
    this.wsToken = null;
  }

  getConnectionState(): ConnectionStatus {
    if (!this.ws) return 'disconnected';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'connecting';
      case WebSocket.OPEN:
        return 'connected';
      default:
        return 'disconnected';
    }
  }
}
