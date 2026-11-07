/**
 * 医生/患者通信 WebSocket 服务（后端 /ws/chat/{conversation_id}）。
 *
 * 协议确认（backend/app/api/websockets.py + app/core/auth.py，commit 135a5d9）：
 * - 认证：get_current_user_ws 依次尝试 query 参数 token 与名为 access_token 的
 *   cookie。本系统登录流程不写 cookie（后端无任何 set_cookie 调用），access token
 *   仅存 localStorage，因此这里通过 ?token= 传递。token 缺失/失效时后端在 accept
 *   前直接 close(1008)（无错误帧）；非会话成员则 accept 后先收到
 *   {"type":"error","error_code":"NOT_CONVERSATION_PARTICIPANT"} 再 close(4403)。
 * - 入站：{"type":"message","content":...,"client_message_id":...}；成功逐帧回
 *   {"type":"message_ack","client_message_id":...,"message":<落库消息>}；失败回
 *   error 帧（INVALID_PAYLOAD / MESSAGE_PERSIST_FAILED / NOT_CONVERSATION_PARTICIPANT），
 *   注意 error 帧不携带 client_message_id。
 * - 广播：落库成功后向房间内所有人（含发送者本人）广播
 *   {"type":"message","message":<落库消息>}，载荷为真实 _id 字符串、UTC timestamp、
 *   sender_id、read/deleted，可能携带 client_message_id。
 * - 心跳：后端无应用层 ping/pong（未知 type 的入站帧被静默忽略，无法做往返探测），
 *   因此不发明私有心跳；保活依赖 uvicorn 协议层 ping，断连后靠本服务的重连 +
 *   页面 REST 轮询兜底。
 * - typing / read_receipt 服务端仅转发不落库（WS03 范围），已读状态仍以 REST 为准：
 *   本服务不发送、也不消费这两类帧，不假装已读回执实时生效。
 *
 * 设计：独立文件而非并入 chatService.ts——后者是无状态 REST/DTO 层，本文件是
 * 有状态连接生命周期管理器（重连退避、pending 队列、事件回调），职责分开后
 * WS 不可用时页面可以无碍地退回 chatApi 的 REST 方法。
 */

import { API_BASE_URL } from '../config/api';
import { STORAGE_KEYS } from '../config/constants';
import type { MessageDto } from './chatService';

// 广播/ack 载荷比 REST MessageDto 多一个可选幂等键
export interface WsChatMessage extends MessageDto {
  client_message_id?: string;
}

/** 页面侧乐观消息占位（WS 与 REST 两条路径共用同一形状） */
export interface PendingChatMessage {
  clientMessageId: string;
  content: string;
  status: 'pending' | 'failed';
}

export type ChatWsStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'degraded';

export interface ChatWsStatusInfo {
  /** degraded 原因：forbidden=非会话成员(4403)，auth=未登录/token 失效(1008)，network=其他 */
  reason?: 'forbidden' | 'auth' | 'network';
  closeCode?: number;
  errorCode?: string;
}

export interface ChatWsHandlers {
  onStatusChange?: (status: ChatWsStatus, info: ChatWsStatusInfo) => void;
  /** 房间广播的落库消息（含本人发送的消息，页面按 id/client_message_id 去重） */
  onBroadcastMessage?: (message: WsChatMessage) => void;
  /** 发送者本人的 ack 帧（与广播可能先后到达，页面用同一 upsert 去重） */
  onAck?: (message: WsChatMessage, clientMessageId: string | null) => void;
}

/** WS 不可用/发送失败时抛出，页面据此回退 REST */
export class ChatWsSendError extends Error {
  readonly errorCode: string;
  constructor(errorCode: string, message?: string) {
    super(message || errorCode);
    this.name = 'ChatWsSendError';
    this.errorCode = errorCode;
  }
}

// ---- 服务端帧类型守卫 ----

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** 宽松校验落库消息载荷：至少有字符串 id 与字符串 timestamp */
function parseServerMessage(value: unknown): WsChatMessage | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== 'string' || typeof value.timestamp !== 'string') return null;
  return value as unknown as WsChatMessage;
}

type ServerFrame =
  | { kind: 'broadcast'; message: WsChatMessage }
  | { kind: 'ack'; message: WsChatMessage; clientMessageId: string | null }
  | { kind: 'error'; errorCode: string; errorMessage?: string }
  | { kind: 'ignored' };

function parseServerFrame(raw: string): ServerFrame {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { kind: 'ignored' };
  }
  if (!isRecord(data) || typeof data.type !== 'string') return { kind: 'ignored' };

  if (data.type === 'message') {
    const message = parseServerMessage(data.message);
    return message ? { kind: 'broadcast', message } : { kind: 'ignored' };
  }
  if (data.type === 'message_ack') {
    const message = parseServerMessage(data.message);
    if (!message) return { kind: 'ignored' };
    const clientMessageId =
      typeof data.client_message_id === 'string' ? data.client_message_id : null;
    return { kind: 'ack', message, clientMessageId };
  }
  if (data.type === 'error') {
    if (typeof data.error_code !== 'string') return { kind: 'ignored' };
    return {
      kind: 'error',
      errorCode: data.error_code,
      errorMessage: typeof data.message === 'string' ? data.message : undefined,
    };
  }
  // user_joined / user_left / typing / read_receipt / notification_count 等：本轮不消费
  return { kind: 'ignored' };
}

// ---- client_message_id ----

export function generateClientMessageId(): string {
  // crypto.randomUUID 仅在安全上下文（https/localhost）可用，非安全上下文降级
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `cmid-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

// ---- WS 地址推导 ----

/**
 * 从与 REST 同源的 API_BASE_URL 推导 WS 基址（不硬编码 host）：
 * API_BASE_URL 形如 `https://host/api`（绝对）或 `/api`（根相对，最后一段必为 /api）。
 * 后端 WS 路由挂在应用根 /ws/chat/{id}，不在 /api 前缀下，因此去掉末尾 /api 得到基址。
 */
export function resolveChatWsBaseUrl(): string {
  const withoutApi = API_BASE_URL.replace(/\/api\/?$/, '');
  if (/^https?:\/\//i.test(withoutApi)) {
    return withoutApi.replace(/^http/i, 'ws');
  }
  // 根相对路径：挂到当前页面 origin（http→ws / https→wss 由 replace 之外的分支处理）
  return `${window.location.origin}${withoutApi}`;
}

// ---- 连接客户端 ----

const RECONNECT_BASE_DELAY_MS = 1_000;
const RECONNECT_MAX_DELAY_MS = 30_000;

interface PendingEntry {
  resolve: (message: WsChatMessage) => void;
  reject: (error: ChatWsSendError) => void;
  settled: boolean;
}

export class ChatWsClient {
  private readonly handlers: ChatWsHandlers;
  private ws: WebSocket | null = null;
  private conversationId: string | null = null;
  private manualClose = false;
  private attempt = 0;
  private reconnectTimer: number | null = null;
  private status: ChatWsStatus = 'idle';
  private statusInfo: ChatWsStatusInfo = {};
  private pending = new Map<string, PendingEntry>();

  constructor(handlers: ChatWsHandlers) {
    this.handlers = handlers;
  }

  getStatus(): ChatWsStatus {
    return this.status;
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * 接入指定会话。重复接入同一会话且连接仍在建立/已建立时为 no-op；
   * 切换会话时先断开旧连接。token 缺失不发起连接，直接降级（页面走 REST）。
   */
  connect(conversationId: string): void {
    if (
      this.conversationId === conversationId &&
      (this.status === 'connecting' || this.status === 'connected' || this.status === 'reconnecting')
    ) {
      return;
    }
    this.openConnection(conversationId);
  }

  private openConnection(conversationId: string): void {
    this.disconnect();
    this.manualClose = false;
    this.conversationId = conversationId;

    const token = localStorage.getItem(STORAGE_KEYS.TOKEN);
    if (!token) {
      this.setStatus('degraded', { reason: 'auth' });
      return;
    }

    const base = resolveChatWsBaseUrl();
    const url = `${base}/ws/chat/${encodeURIComponent(conversationId)}?token=${encodeURIComponent(token)}`;
    this.setStatus('connecting');

    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.attempt = 0;
      this.setStatus('connected');
    };
    ws.onmessage = (event: MessageEvent) => {
      this.handleFrame(event.data);
    };
    ws.onerror = () => {
      // 错误细节由 onclose 统一处理（浏览器总是先 error 后 close）
    };
    ws.onclose = (event: CloseEvent) => {
      this.ws = null;
      this.rejectAllPending(new ChatWsSendError('WS_CLOSED', '连接已断开，消息未送达'));
      if (this.manualClose) {
        this.setStatus('idle');
        return;
      }
      // 4403：非会话成员/会话不存在，重连无意义，降级且不再重试
      if (event.code === 4403) {
        this.setStatus('degraded', { reason: 'forbidden', closeCode: event.code });
        return;
      }
      // 1008：后端在 accept 前的鉴权拒绝（token 缺失/失效），不重试轰炸
      if (event.code === 1008) {
        this.setStatus('degraded', { reason: 'auth', closeCode: event.code });
        return;
      }
      this.scheduleReconnect();
    };
  }

  /** 主动断开（切换会话/卸载页面），不触发重连 */
  disconnect(): void {
    this.manualClose = true;
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const ws = this.ws;
    this.ws = null;
    this.rejectAllPending(new ChatWsSendError('WS_CLOSED', '连接已断开，消息未送达'));
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.onclose = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.close();
    }
    this.conversationId = null;
    this.setStatus('idle');
  }

  /**
   * 发送消息，resolve 于服务端 ack（或携带同一 client_message_id 的广播，
   * 两者先到先结算，幂等）。未连接/超时/错误帧时 reject，页面回退 REST 或标记失败。
   */
  send(content: string, clientMessageId: string): Promise<WsChatMessage> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN || !this.conversationId) {
      return Promise.reject(new ChatWsSendError('WS_NOT_CONNECTED', '实时连接未建立'));
    }
    return new Promise<WsChatMessage>((resolve, reject) => {
      this.pending.set(clientMessageId, { resolve, reject, settled: false });
      ws.send(
        JSON.stringify({
          type: 'message',
          content,
          client_message_id: clientMessageId,
        })
      );
    });
  }

  private handleFrame(data: unknown): void {
    if (typeof data !== 'string') return;
    const frame = parseServerFrame(data);
    switch (frame.kind) {
      case 'broadcast':
        // 本人消息的广播先于 ack 到达时，也直接结算 pending（幂等）
        if (frame.message.client_message_id) {
          this.settlePending(frame.message.client_message_id, frame.message);
        }
        this.handlers.onBroadcastMessage?.(frame.message);
        break;
      case 'ack':
        if (frame.clientMessageId) {
          this.settlePending(frame.clientMessageId, frame.message);
        }
        this.handlers.onAck?.(frame.message, frame.clientMessageId);
        break;
      case 'error':
        if (frame.errorCode === 'NOT_CONVERSATION_PARTICIPANT') {
          // 连接期间被移出会话：服务端随后 close(4403)，这里先行降级
          this.rejectAllPending(new ChatWsSendError(frame.errorCode, frame.errorMessage));
          this.setStatus('degraded', { reason: 'forbidden', errorCode: frame.errorCode });
        } else {
          // INVALID_PAYLOAD / MESSAGE_PERSIST_FAILED：error 帧不带 client_message_id，
          // 页面配合「同一时刻至多一条在途消息」的发送守卫即可无歧义映射
          this.rejectAllPending(
            new ChatWsSendError(frame.errorCode, frame.errorMessage || '消息发送失败')
          );
        }
        break;
      default:
        break;
    }
  }

  private settlePending(clientMessageId: string, message: WsChatMessage): void {
    const entry = this.pending.get(clientMessageId);
    if (!entry || entry.settled) return;
    entry.settled = true;
    this.pending.delete(clientMessageId);
    entry.resolve(message);
  }

  private rejectAllPending(error: ChatWsSendError): void {
    for (const [, entry] of this.pending) {
      if (!entry.settled) {
        entry.settled = true;
        entry.reject(error);
      }
    }
    this.pending.clear();
  }

  private scheduleReconnect(): void {
    this.setStatus('reconnecting');
    const delay = Math.min(RECONNECT_MAX_DELAY_MS, RECONNECT_BASE_DELAY_MS * 2 ** this.attempt);
    this.attempt += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.manualClose && this.conversationId) {
        // 重连路径绕过 connect() 的同会话去重（此时 status 为 reconnecting）
        this.openConnection(this.conversationId);
      }
    }, delay);
  }

  private setStatus(status: ChatWsStatus, info: ChatWsStatusInfo = {}): void {
    this.status = status;
    this.statusInfo = info;
    this.handlers.onStatusChange?.(status, info);
  }
}
