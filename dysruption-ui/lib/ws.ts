import { WatcherUpdatePayload, VerdictUpdatePayload, VerdictPayload } from './types';

type WSEventType = 'watcher:update' | 'verdict:update' | 'verdict:complete';

interface WSEvent {
  type: WSEventType;
  payload: WatcherUpdatePayload | VerdictUpdatePayload | VerdictPayload;
}

type Handler = (event: WSEvent) => void;

export class CVAWebSocket {
  private url = 'ws://localhost:8000/ws';
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private handlers: Handler[] = [];
  private statusHandlers: ((status: string) => void)[] = [];
  private shouldReconnect = true;

  constructor(url?: string) {
    if (url) this.url = url;
  }

  start() {
    this.shouldReconnect = true;
    this.connect();
  }

  onMessage(fn: Handler) { 
    this.handlers.push(fn); 
  }

  onStatusChange(fn: (status: string) => void) {
    this.statusHandlers.push(fn);
  }

  private notifyStatus(status: string) {
    this.statusHandlers.forEach(h => h(status));
  }

  private connect() {
    try {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => { 
        this.reconnectAttempts = 0; 
        console.log('ws open'); 
        this.notifyStatus('connected');
      };
      
      this.ws.onmessage = (e) => { 
        try {
          const msg = JSON.parse(e.data); 
          this.handlers.forEach(h => h(msg)); 
        } catch (err) {
          console.error('Failed to parse WS message', err);
        }
      };
      
      this.ws.onclose = () => {
        this.notifyStatus('disconnected');
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };
      
      this.ws.onerror = () => { 
        console.error('WS error');
        this.ws?.close(); 
      };
    } catch (e) {
      console.error('WS connection failed', e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    this.reconnectAttempts++;
    // Exponential backoff: min(30s, 1s * 2^attempts + jitter)
    const delay = Math.min(30000, Math.pow(2, this.reconnectAttempts) * 1000 + Math.random() * 500);
    this.notifyStatus(`reconnecting (attempt ${this.reconnectAttempts})`);
    console.log(`Reconnecting in ${delay}ms...`);
    setTimeout(() => this.connect(), delay);
  }

  manualReconnect() {
    this.reconnectAttempts = 0;
    this.ws?.close();
    this.connect();
  }

  stop() { 
    this.shouldReconnect = false;
    this.ws?.close(); 
    this.ws = null; 
  }
}
