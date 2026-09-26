/**
 * Cliente WebSocket (contrato §7).
 * - Conexão única em wss(s)://<host>/api/ws?token=<JWT>.
 * - Frames: { channel, data }.
 * - Reconexão com backoff exponencial (1s, 2s, 4s, ..., 30s).
 * - Inscrição por canal e por run.
 * - Callback de reconexão para as telas refazerem o GET.
 */

import type { WSChannel, WSFrame } from "./types";

type EventHandler = (data: Record<string, unknown>) => void;
type ReconnectHandler = () => void;

interface Subscription {
  channel: WSChannel;
  handler: EventHandler;
  pipelineId?: string;
}

const MAX_BACKOFF = 30_000;

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string;
  private subscriptions: Subscription[] = [];
  private reconnectHandler: ReconnectHandler | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private connected = false;

  constructor(token: string) {
    this.token = token;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`;
  }

  /**
   * Conecta ao WebSocket.
   */
  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.shouldReconnect = true;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      const wasReconnecting = this.reconnectAttempts > 0;
      this.connected = true;
      this.reconnectAttempts = 0;
      if (wasReconnecting && this.reconnectHandler) {
        this.reconnectHandler();
      }
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const frame: WSFrame = JSON.parse(event.data as string);
        this.dispatch(frame);
      } catch {
        // Frame inválido: ignora.
      }
    };

    this.ws.onclose = () => {
      this.connected = false;
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose será chamado depois; nada a fazer aqui.
    };
  }

  /**
   * Desconecta e impede reconexão.
   */
  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  /**
   * Registra um handler para um canal.
   * Opcionalmente filtra por pipelineId.
   */
  on(channel: WSChannel, handler: EventHandler, pipelineId?: string): void {
    this.subscriptions.push({ channel, handler, pipelineId });
  }

  /**
   * Remove um handler específico.
   */
  off(channel: WSChannel, handler: EventHandler, pipelineId?: string): void {
    this.subscriptions = this.subscriptions.filter(
      (sub) =>
        !(sub.channel === channel && sub.handler === handler && sub.pipelineId === pipelineId)
    );
  }

  /**
   * Registra um callback chamado após reconexão.
   * As telas usam para refazer GET REST e sincronizar estado.
   */
  onReconnect(handler: ReconnectHandler): void {
    this.reconnectHandler = handler;
  }

  /**
   * Atualiza o token (usado após rotação de refresh).
   */
  setToken(token: string): void {
    this.token = token;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.url = `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`;
  }

  /**
   * Estado da conexão.
   */
  get isConnected(): boolean {
    return this.connected;
  }

  private dispatch(frame: WSFrame): void {
    for (const sub of this.subscriptions) {
      if (sub.channel !== frame.channel) continue;

      if (sub.pipelineId) {
        const dataPipelineId = frame.data.pipelineId as string | undefined;
        if (dataPipelineId !== sub.pipelineId) continue;
      }

      sub.handler(frame.data);
    }
  }

  private scheduleReconnect(): void {
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), MAX_BACKOFF);
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }
}

/**
 * Singleton do WebSocketClient.
 * Uma única conexão por página (contrato §7).
 */
let client: WebSocketClient | null = null;

export function getWebSocketClient(token: string): WebSocketClient {
  if (!client) {
    client = new WebSocketClient(token);
  } else {
    client.setToken(token);
  }
  return client;
}

export function disposeWebSocketClient(): void {
  if (client) {
    client.disconnect();
    client = null;
  }
}
