import { useEffect, useRef, useState } from 'react';
import type { Conversation } from './api';

type Frame = { type: string; request_id?: string; conversation_id?: string;
  data?: unknown; error?: string };
type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout> };

// 只在确认落库后清空输入；重连订阅完整状态，未确认命令由用户用原编号重试。
export function useGateway(id: string, onState: (data: Conversation) => void) {
  const socket = useRef<WebSocket | null>(null);
  const callback = useRef(onState);
  const selected = useRef(id);
  const requests = useRef(new Map<string, Pending>());
  const [connected, setConnected] = useState(false);
  callback.current = onState; selected.current = id;

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const rejectPending = () => {
      for (const pending of requests.current.values()) {
        clearTimeout(pending.timer); pending.reject(new Error('连接中断，可用原消息重试'));
      }
      requests.current.clear();
    };
    const connect = () => {
      const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/agent/gateway`);
      socket.current = ws;
      ws.onopen = () => {
        setConnected(true);
        if (selected.current) ws.send(JSON.stringify({ type: 'subscribe',
          request_id: crypto.randomUUID(), conversation_id: selected.current }));
      };
      ws.onmessage = event => {
        const frame = JSON.parse(String(event.data)) as Frame;
        if (frame.type === 'state' && frame.conversation_id === selected.current) {
          callback.current(frame.data as Conversation);
        }
        const pending = frame.request_id ? requests.current.get(frame.request_id) : undefined;
        if (pending && frame.request_id) {
          clearTimeout(pending.timer); requests.current.delete(frame.request_id);
          if (frame.type === 'error') pending.reject(new Error(frame.error || '命令失败'));
          else pending.resolve(frame.data);
        }
      };
      ws.onclose = () => {
        if (stopped) return;
        setConnected(false); rejectPending(); timer = setTimeout(connect, 1500);
      };
    };
    connect();
    return () => { stopped = true; clearTimeout(timer); socket.current?.close(); rejectPending(); };
  }, []);

  useEffect(() => {
    // 切换会话仅订阅新状态，不打断正在等待确认的消息。
    if (id && socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({
      type: 'subscribe', request_id: crypto.randomUUID(), conversation_id: id }));
  }, [id]);

  function command(type: string, conversationId: string, requestId: string, extra = {}): Promise<unknown> {
    if (socket.current?.readyState !== WebSocket.OPEN) return Promise.reject(new Error('网关正在重连，请稍后重试'));
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        requests.current.delete(requestId); reject(new Error('确认超时，可用原消息重试'));
      }, 10000);
      requests.current.set(requestId, { resolve, reject, timer: timeout });
      socket.current!.send(JSON.stringify({ type, conversation_id: conversationId,
        request_id: requestId, ...extra }));
    });
  }
  return { connected, command };
}
