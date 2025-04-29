import { useEffect, useState, useRef, useCallback } from 'react';

interface UseWebSocketOptions {
  reconnectInterval?: number;
  reconnectAttempts?: number;
  onOpen?: (event: WebSocketEventMap['open']) => void;
  onClose?: (event: WebSocketEventMap['close']) => void;
  onError?: (event: WebSocketEventMap['error']) => void;
}

interface WebSocketMessage {
  data: string;
  type: string;
  timestamp: Date;
}

export default function useWebSocket(
  url: string, 
  options: UseWebSocketOptions = {}
) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const [reconnectCount, setReconnectCount] = useState(0);
  const [error, setError] = useState<Error | null>(null);
  
  const {
    reconnectInterval = 3000,
    reconnectAttempts = 5,
    onOpen,
    onClose,
    onError
  } = options;
  
  const webSocketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // 清理重连定时器
  const cleanupReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);
  
  // 建立WebSocket连接
  const connect = useCallback(() => {
    // 如果之前有连接，先关闭
    if (webSocketRef.current) {
      webSocketRef.current.close();
    }
    
    try {
      // 创建新的WebSocket连接
      const ws = new WebSocket(url);
      
      ws.onopen = (event) => {
        setIsConnected(true);
        setReconnectCount(0);
        setError(null);
        if (onOpen) onOpen(event);
      };
      
      ws.onmessage = (event) => {
        const message: WebSocketMessage = {
          data: event.data,
          type: 'message',
          timestamp: new Date()
        };
        setLastMessage(message);
      };
      
      ws.onclose = (event) => {
        setIsConnected(false);
        if (onClose) onClose(event);
        
        // 尝试重连
        if (reconnectCount < reconnectAttempts) {
          cleanupReconnectTimeout();
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectCount(prev => prev + 1);
            connect();
          }, reconnectInterval);
        }
      };
      
      ws.onerror = (event) => {
        const wsError = new Error(`WebSocket error: ${event}`);
        setError(wsError);
        if (onError) onError(event);
      };
      
      webSocketRef.current = ws;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to create WebSocket connection');
      setError(error);
      
      // 尝试重连
      if (reconnectCount < reconnectAttempts) {
        cleanupReconnectTimeout();
        reconnectTimeoutRef.current = setTimeout(() => {
          setReconnectCount(prev => prev + 1);
          connect();
        }, reconnectInterval);
      }
    }
  }, [url, reconnectCount, reconnectAttempts, reconnectInterval, onOpen, onClose, onError, cleanupReconnectTimeout]);
  
  // 发送消息
  const sendMessage = useCallback((data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
    if (webSocketRef.current && isConnected) {
      webSocketRef.current.send(data);
      return true;
    }
    return false;
  }, [isConnected]);
  
  // 关闭连接
  const disconnect = useCallback(() => {
    if (webSocketRef.current) {
      webSocketRef.current.close();
      webSocketRef.current = null;
      setIsConnected(false);
    }
    cleanupReconnectTimeout();
  }, [cleanupReconnectTimeout]);
  
  // 初始化连接
  useEffect(() => {
    connect();
    
    // 清理函数
    return () => {
      if (webSocketRef.current) {
        webSocketRef.current.close();
      }
      cleanupReconnectTimeout();
    };
  }, [connect, cleanupReconnectTimeout]);
  
  return {
    isConnected,
    lastMessage,
    sendMessage,
    disconnect,
    reconnectCount,
    error
  };
} 