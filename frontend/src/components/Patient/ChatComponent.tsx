// @ts-nocheck
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Box, Paper, TextField, Button, Typography, Avatar, IconButton,
  Divider, List, ListItem, ListItemAvatar, ListItemText, CircularProgress,
  Card, CardContent, InputAdornment, Badge, Menu, MenuItem, Tooltip, Snackbar, Alert,
  Chip, Popover, Grid
} from '@mui/material';
import { FixedSizeList, ListChildComponentProps } from 'react-window';
import AutoSizer from 'react-virtualized-auto-sizer';
import SendIcon from '@mui/icons-material/Send';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import ImageIcon from '@mui/icons-material/Image';
import EmojiEmotionsIcon from '@mui/icons-material/EmojiEmotions';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import SyncIcon from '@mui/icons-material/Sync';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import FormatBoldIcon from '@mui/icons-material/FormatBold';
import FormatItalicIcon from '@mui/icons-material/FormatItalic';
import MarkChatReadIcon from '@mui/icons-material/MarkChatRead';
import PhoneIcon from '@mui/icons-material/Phone';
import VideoCallIcon from '@mui/icons-material/VideoCall';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { useTheme } from '@mui/material/styles';

// API服务接口
import { chatApi } from '../../services/chatService';
// 导入WebSocket钩子
import useWebSocket from '../../hooks/useWebSocket';

// 添加IndexedDB支持
import { openDB, DBSchema, IDBPDatabase } from 'idb';
// 添加网络状态监测
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

// 消息类型定义
interface Message {
  id: string;
  content: string;
  sender: 'patient' | 'doctor' | 'system';
  timestamp: Date;
  status: 'sent' | 'delivered' | 'read' | 'error' | 'pending';
  conversationId?: string;
  isDeleted?: boolean;
  pendingRetry?: boolean;
  attachments?: Array<{
    id: string;
    type: 'image' | 'file';
    url: string;
    name: string;
  }>;
}

// 聊天参与者类型定义
interface Participant {
  id: string;
  name: string;
  avatar?: string;
  role: 'patient' | 'doctor' | 'healthManager';
  status: 'online' | 'offline' | 'away' | 'busy';
  lastSeen?: Date;
}

// 组件属性定义
interface ChatComponentProps {
  currentUser: Participant;
  recipient: Participant;
  initialMessages?: Message[];
  onSendMessage?: (content: string, attachments?: File[]) => Promise<void>;
  onLoadMoreMessages?: () => Promise<Message[]>;
  loading?: boolean;
  conversationId?: string;
  enableWebSocket?: boolean;
}

// 常用表情包
const EMOJIS = [
  '😊', '😃', '😄', '😁', '😆', '😅', '😂', '🙂', '🙃', '😉',
  '😌', '😍', '🥰', '😘', '😗', '😙', '😚', '😋', '😛', '😝',
  '😜', '🤪', '🤨', '🧐', '🤓', '😎', '🤩', '🥳', '😏', '😒',
  '😞', '😔', '😟', '😕', '🙁', '☹️', '😣', '😖', '😫', '😩',
  '🥺', '😢', '😭', '😤', '😠', '😡', '🤬', '🤯', '😳', '🥵'
];

// 快速回复模板
const QUICK_REPLIES = [
  '好的，我明白了',
  '我稍后会处理这个问题',
  '谢谢您的反馈',
  '请问您现在感觉如何？',
  '需要我帮您安排复诊吗？',
  '请按照康复计划坚持训练'
];

// 新增在线状态类型
type OnlineStatus = 'online' | 'offline' | 'away' | 'busy';

// 在线状态颜色映射
const statusColors: Record<OnlineStatus, string> = {
  online: 'success',
  offline: 'default',
  away: 'warning',
  busy: 'error'
};

// 在线状态文本映射
const statusText: Record<OnlineStatus, string> = {
  online: '在线',
  offline: '离线',
  away: '暂时离开',
  busy: '忙碌中'
};

// 定义消息数据库结构
interface ChatDBSchema extends DBSchema {
  messages: {
    key: string;
    value: {
      id: string;
      content: string;
      sender: 'patient' | 'doctor' | 'system';
      timestamp: string; // 存储为ISO字符串
      status: 'sent' | 'delivered' | 'read' | 'error' | 'pending';
      conversationId?: string;
      isDeleted?: boolean;
      pendingRetry?: boolean;
      attachments?: Array<{
        id: string;
        type: 'image' | 'file';
        url: string;
        name: string;
      }>;
    };
    indexes: {
      'by-conversation': string;
      'by-status': string;
      'by-timestamp': string;
    };
  };
  pendingMessages: {
    key: string;
    value: {
      id: string;
      content: string;
      attachments?: File[];
      conversationId: string;
      timestamp: string;
      retryCount: number;
    };
  };
}

const ChatComponent: React.FC<ChatComponentProps> = ({
  currentUser,
  recipient,
  initialMessages = [],
  onSendMessage,
  onLoadMoreMessages,
  loading: initialLoading = false,
  conversationId,
  enableWebSocket = false
}) => {
  const theme = useTheme();
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [inputValue, setInputValue] = useState('');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(initialLoading);
  const [isTyping, setIsTyping] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [messageContextMenu, setMessageContextMenu] = useState<{
    mouseX: number;
    mouseY: number;
    messageId: string | null;
  } | null>(null);
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({
    open: false,
    message: '',
    severity: 'info'
  });
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // 使用WebSocket钩子替代原生WebSocket
  const wsUrl = conversationId 
    ? `${import.meta.env.VITE_WS_URL || 'wss://api.example.com'}/chat/${conversationId}`
    : '';
  
  const { 
    isConnected, 
    sendMessage: sendWsMessage, 
    lastMessage, 
    reconnectCount,
    error: wsError
  } = useWebSocket(enableWebSocket ? wsUrl : '', {
    reconnectInterval: 3000,
    reconnectAttempts: 10,
    onOpen: () => {
      setReconnecting(false);
      console.log('WebSocket连接已建立');
      setNotification({
        open: true,
        message: '实时聊天已连接',
        severity: 'success'
      });
    },
    onClose: () => {
      console.log('WebSocket连接已关闭');
      setReconnecting(true);
    },
    onError: (err) => {
      console.error('WebSocket错误:', err);
      setNotification({
        open: true,
        message: '消息同步连接失败，将尝试重新连接',
        severity: 'error'
      });
    }
  });
  
  // 新增状态用于表情选择器
  const [emojiAnchorEl, setEmojiAnchorEl] = useState<HTMLButtonElement | null>(null);
  // 新增状态用于快速回复菜单
  const [quickReplyAnchorEl, setQuickReplyAnchorEl] = useState<HTMLButtonElement | null>(null);
  // 新增状态用于文本格式
  const [textFormat, setTextFormat] = useState<{
    bold: boolean;
    italic: boolean;
  }>({
    bold: false,
    italic: false
  });
  
  // 新增虚拟滚动相关状态
  const [virtualScrollEnabled, setVirtualScrollEnabled] = useState(false);
  const messageListHeight = useRef(0);
  
  // 添加网络状态监测
  const isOnline = useOnlineStatus();
  const [pendingMessages, setPendingMessages] = useState<any[]>([]);
  const [dbInstance, setDbInstance] = useState<IDBPDatabase<ChatDBSchema> | null>(null);
  const [syncingMessages, setSyncingMessages] = useState(false);
  
  // 在消息数量超过阈值时启用虚拟滚动
  useEffect(() => {
    setVirtualScrollEnabled(messages.length > 50);
  }, [messages.length]);
  
  // 测量消息列表容器高度
  useEffect(() => {
    if (messageListRef.current) {
      messageListHeight.current = messageListRef.current.clientHeight;
    }
  }, [messages]);
  
  // 处理从WebSocket接收的消息
  useEffect(() => {
    if (lastMessage && lastMessage.data) {
      try {
        const data = JSON.parse(lastMessage.data);
        
        if (data.type === 'message') {
          // 处理新消息
          handleNewWebSocketMessage(data.message);
        } else if (data.type === 'typing') {
          // 处理对方正在输入的状态
          if (data.userId === recipient.id) {
            setIsTyping(data.isTyping);
          }
        } else if (data.type === 'status_update') {
          // 处理消息状态更新
          updateMessageStatus(data.messageId, data.status);
        } else if (data.type === 'delete_message') {
          // 处理消息删除
          handleMessageDeleted(data.messageId);
        } else if (data.type === 'read_receipt') {
          // 处理消息已读回执
          handleReadReceipt(data.messageIds);
        }
      } catch (error) {
        console.error('处理WebSocket消息时出错:', error);
      }
    }
  }, [lastMessage, recipient.id]);
  
  // 处理WebSocket错误后果
  useEffect(() => {
    if (wsError) {
      console.error('WebSocket错误:', wsError);
    }
  }, [wsError]);

  // 显示重连尝试通知
  useEffect(() => {
    if (reconnectCount > 0) {
      setReconnecting(true);
      setNotification({
        open: true,
        message: `正在尝试重新连接 (${reconnectCount}/10)`,
        severity: 'info'
      });
    }
  }, [reconnectCount]);

  // 处理从WebSocket接收的新消息
  const handleNewWebSocketMessage = useCallback((message: Message) => {
    // 检查消息是否已存在
    setMessages(prevMessages => {
      if (prevMessages.some(msg => msg.id === message.id)) {
        return prevMessages;
      }
      return [...prevMessages, {
        ...message,
        timestamp: new Date(message.timestamp)
      }];
    });
    
    // 如果消息是收到的，发送已读回执
    if (message.sender !== currentUser.role && isConnected && sendWsMessage) {
      sendWsMessage(JSON.stringify({
        type: 'read_receipt',
        messageId: message.id,
        conversationId
      }));
    }
  }, [currentUser.role, isConnected, sendWsMessage, conversationId]);
  
  // 处理消息删除
  const handleMessageDeleted = useCallback((messageId: string) => {
    setMessages(prevMessages => 
      prevMessages.map(msg => 
        msg.id === messageId 
          ? { ...msg, isDeleted: true } 
          : msg
      )
    );
  }, []);
  
  // 处理消息已读回执
  const handleReadReceipt = useCallback((messageIds: string[]) => {
    setMessages(prevMessages => 
      prevMessages.map(msg => 
        messageIds.includes(msg.id) 
          ? { ...msg, status: 'read' } 
          : msg
      )
    );
  }, []);

  // 初始化IndexedDB
  useEffect(() => {
    const initDB = async () => {
      try {
        const db = await openDB<ChatDBSchema>('chat-messages-db', 1, {
          upgrade(db) {
            // 创建消息存储
            const messagesStore = db.createObjectStore('messages', {
              keyPath: 'id'
            });
            messagesStore.createIndex('by-conversation', 'conversationId');
            messagesStore.createIndex('by-status', 'status');
            messagesStore.createIndex('by-timestamp', 'timestamp');
            
            // 创建待发送消息存储
            db.createObjectStore('pendingMessages', {
              keyPath: 'id'
            });
          }
        });
        
        setDbInstance(db);
        
        // 加载待发送消息
        if (conversationId) {
          loadPendingMessages(db, conversationId);
        }
      } catch (error) {
        console.error('初始化IndexedDB失败:', error);
        setNotification({
          open: true,
          message: '初始化本地存储失败，部分功能可能不可用',
          severity: 'error'
        });
      }
    };
    
    initDB();
    
    return () => {
      // 关闭数据库连接
      if (dbInstance) {
        dbInstance.close();
      }
    };
  }, []);
  
  // 加载待发送消息
  const loadPendingMessages = async (db: IDBPDatabase<ChatDBSchema>, convId: string) => {
    try {
      const tx = db.transaction('pendingMessages', 'readonly');
      const store = tx.objectStore('pendingMessages');
      const allPendingMessages = await store.getAll();
      
      // 过滤当前会话的待发送消息
      const conversationPendingMessages = allPendingMessages.filter(
        msg => msg.conversationId === convId
      );
      
      setPendingMessages(conversationPendingMessages);
    } catch (error) {
      console.error('加载待发送消息失败:', error);
    }
  };
  
  // 网络状态变化处理
  useEffect(() => {
    if (isOnline && !isConnected && enableWebSocket) {
      // 网络恢复，尝试重新连接WebSocket
      // WebSocket钩子会自动尝试重连
      
      // 尝试同步离线期间的消息
      syncMessages();
    }
  }, [isOnline, isConnected, enableWebSocket]);
  
  // 同步消息（从服务器获取新消息，发送本地待发送消息）
  const syncMessages = async () => {
    if (!conversationId || !isOnline || syncingMessages) return;
    
    setSyncingMessages(true);
    setNotification({
      open: true,
      message: '正在同步消息...',
      severity: 'info'
    });
    
    try {
      // 1. 先从服务器获取新消息
      await loadMessagesFromApi();
      
      // 2. 发送所有待发送的消息
      if (pendingMessages.length > 0 && onSendMessage) {
        for (const pendingMsg of pendingMessages) {
          try {
            await onSendMessage(pendingMsg.content, pendingMsg.attachments || []);
            
            // 发送成功，从待发送列表中移除
            if (dbInstance) {
              await dbInstance.delete('pendingMessages', pendingMsg.id);
            }
            
            // 更新消息列表中对应消息的状态
            setMessages(prev => 
              prev.map(msg => 
                msg.id === pendingMsg.id 
                  ? { ...msg, status: 'delivered', pendingRetry: false }
                  : msg
              )
            );
          } catch (error) {
            console.error(`重新发送消息 ${pendingMsg.id} 失败:`, error);
            
            // 更新重试计数
            if (dbInstance) {
              const updatedPendingMsg = {
                ...pendingMsg,
                retryCount: (pendingMsg.retryCount || 0) + 1
              };
              
              if (updatedPendingMsg.retryCount >= 3) {
                // 重试三次后标记为失败
                await dbInstance.delete('pendingMessages', pendingMsg.id);
                
                // 更新消息列表中对应消息的状态
                setMessages(prev => 
                  prev.map(msg => 
                    msg.id === pendingMsg.id 
                      ? { ...msg, status: 'error', pendingRetry: false }
                      : msg
                  )
                );
              } else {
                // 更新重试计数并保留待发送
                await dbInstance.put('pendingMessages', updatedPendingMsg);
              }
            }
          }
        }
      }
      
      setNotification({
        open: true,
        message: '消息同步完成',
        severity: 'success'
      });
    } catch (error) {
      console.error('同步消息失败:', error);
      setNotification({
        open: true,
        message: '消息同步失败',
        severity: 'error'
      });
    } finally {
      setSyncingMessages(false);
      
      // 重新加载待发送消息
      if (dbInstance && conversationId) {
        loadPendingMessages(dbInstance, conversationId);
      }
    }
  };
  
  // 将消息保存到IndexedDB
  const saveMessageToDb = async (message: Message) => {
    if (!dbInstance) return;
    
    try {
      const messageToSave = {
        ...message,
        timestamp: message.timestamp instanceof Date 
          ? message.timestamp.toISOString() 
          : message.timestamp
      };
      
      await dbInstance.put('messages', messageToSave);
    } catch (error) {
      console.error('保存消息到IndexedDB失败:', error);
    }
  };
  
  // 从本地存储加载消息历史，替代原有的loadChatHistory函数
  useEffect(() => {
    if (conversationId && dbInstance) {
      const loadChatHistoryFromDb = async () => {
        try {
          // 从IndexedDB加载消息
          const tx = dbInstance.transaction('messages', 'readonly');
          const index = tx.store.index('by-conversation');
          const messages = await index.getAll(IDBKeyRange.only(conversationId));
          
          if (messages.length > 0) {
            // 转换时间戳为Date对象
            const parsedMessages = messages.map(msg => ({
              ...msg,
              timestamp: new Date(msg.timestamp)
            }));
            
            // 按时间排序
            parsedMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
            
            // 只在没有初始消息时加载本地存储的消息
            if (initialMessages.length === 0) {
              setMessages(parsedMessages);
            }
          }
          
          // 如果没有WebSocket支持，或初始消息为空，尝试从API加载最新消息
          if ((!isConnected || !enableWebSocket) && initialMessages.length === 0) {
            await loadMessagesFromApi();
          }
        } catch (error) {
          console.error('从IndexedDB加载消息历史失败:', error);
        }
      };
      
      loadChatHistoryFromDb();
    }
  }, [conversationId, initialMessages.length, enableWebSocket, isConnected, dbInstance]);

  // 修改现有的loadMessagesFromApi函数，支持将消息保存到IndexedDB
  const loadMessagesFromApi = async () => {
    if (!conversationId || !isOnline) return;
    
    try {
      setLoading(true);
      
      // 调用实际的API服务
      const response = await chatApi.getMessages(conversationId, 30);
      
      if (response && response.messages) {
        const apiMessages = response.messages.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }));
        
        // 更新状态
        setMessages(prevMessages => {
          // 合并新消息，避免重复
          const existingIds = new Set(prevMessages.map(m => m.id));
          const uniqueNewMessages = apiMessages.filter(m => !existingIds.has(m.id));
          
          if (uniqueNewMessages.length === 0) {
            return prevMessages;
          }
          
          // 合并并按时间排序
          const mergedMessages = [...prevMessages, ...uniqueNewMessages];
          mergedMessages.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
          
          return mergedMessages;
        });
        
        // 保存到IndexedDB
        if (dbInstance) {
          const tx = dbInstance.transaction('messages', 'readwrite');
          const store = tx.objectStore('messages');
          
          for (const msg of apiMessages) {
            // 转换时间戳为ISO字符串
            const msgToSave = {
              ...msg,
              timestamp: msg.timestamp instanceof Date 
                ? msg.timestamp.toISOString() 
                : msg.timestamp
            };
            
            await store.put(msgToSave);
          }
          
          await tx.done;
        }
      }
    } catch (error) {
      console.error('从API加载消息失败:', error);
      setNotification({
        open: true,
        message: '加载聊天记录失败',
        severity: 'error'
      });
    } finally {
      setLoading(false);
    }
  };
  
  // 修改handleSendMessage函数，支持离线发送和消息重试
  const handleSendMessage = async () => {
    if (inputValue.trim() === '' && attachments.length === 0) return;

    // 创建一个临时消息ID
    const tempId = `temp-${Date.now()}`;
    
    // 添加消息到UI
    const newMessage: Message = {
      id: tempId,
      content: inputValue,
      sender: currentUser.role === 'patient' ? 'patient' : 'doctor',
      timestamp: new Date(),
      status: isOnline ? 'sent' : 'pending',
      conversationId,
      pendingRetry: !isOnline
    };
    
    // 如果有附件，添加到消息中
    if (attachments.length > 0) {
      newMessage.attachments = attachments.map((file, index) => ({
        id: `temp-attachment-${index}`,
        type: file.type.startsWith('image/') ? 'image' : 'file',
        name: file.name,
        url: URL.createObjectURL(file) // 创建临时URL用于预览
      }));
    }
    
    // 保存消息到状态
    setMessages([...messages, newMessage]);
    
    // 保存消息到IndexedDB
    saveMessageToDb(newMessage);
    
    // 清空输入框和附件
    setInputValue('');
    setAttachments([]);
    
    // 等待组件更新后滚动到底部
    setTimeout(scrollToBottom, 100);
    
    // 如果在线，尝试发送消息
    if (isOnline) {
      if (onSendMessage) {
        try {
          await onSendMessage(inputValue, attachments);
          // 更新消息状态为"已送达"
          setMessages(prev => 
            prev.map(msg => 
              msg.id === tempId 
                ? { ...msg, status: 'delivered', id: `actual-${Date.now()}` } 
                : msg
            )
          );
          
          // 更新IndexedDB中的消息状态
          if (dbInstance) {
            const messageInDb = await dbInstance.get('messages', tempId);
            if (messageInDb) {
              const updatedMessage = {
                ...messageInDb,
                status: 'delivered',
                id: `actual-${Date.now()}`
              };
              await dbInstance.delete('messages', tempId);
              await dbInstance.put('messages', updatedMessage);
            }
          }
        } catch (error) {
          // 更新消息状态为"错误"
          setMessages(prev => 
            prev.map(msg => 
              msg.id === tempId 
                ? { ...msg, status: 'error', pendingRetry: true } 
                : msg
            )
          );
          
          // 将失败的消息添加到待发送队列
          if (dbInstance) {
            const pendingMessage = {
              id: tempId,
              content: inputValue,
              attachments: attachments,
              conversationId,
              timestamp: new Date().toISOString(),
              retryCount: 0
            };
            
            await dbInstance.put('pendingMessages', pendingMessage);
            setPendingMessages(prev => [...prev, pendingMessage]);
          }
          
          console.error("Failed to send message:", error);
          setNotification({
            open: true,
            message: '发送消息失败，已加入重试队列',
            severity: 'warning'
          });
        }
      }
      
      // 如果WebSocket连接可用，通过WebSocket发送消息
      if (isConnected && conversationId) {
        try {
          sendWsMessage(JSON.stringify({
            type: 'message',
            message: {
              content: inputValue,
              conversationId,
              attachments: []
            }
          }));
        } catch (error) {
          console.error('通过WebSocket发送消息失败:', error);
        }
      }
    } else {
      // 离线状态，将消息添加到待发送队列
      if (dbInstance) {
        const pendingMessage = {
          id: tempId,
          content: inputValue,
          attachments: attachments,
          conversationId,
          timestamp: new Date().toISOString(),
          retryCount: 0
        };
        
        await dbInstance.put('pendingMessages', pendingMessage);
        setPendingMessages(prev => [...prev, pendingMessage]);
        
        setNotification({
          open: true,
          message: '您当前处于离线状态，消息将在网络恢复后发送',
          severity: 'info'
        });
      }
    }
  };
  
  // 添加重试发送消息功能
  const retryMessage = async (messageId: string) => {
    // 查找待发送消息
    const pendingMessage = pendingMessages.find(msg => msg.id === messageId);
    
    if (!pendingMessage) {
      console.error(`找不到ID为 ${messageId} 的待发送消息`);
      return;
    }
    
    // 更新UI状态
    setMessages(prev => 
      prev.map(msg => 
        msg.id === messageId 
          ? { ...msg, status: 'sent', pendingRetry: false } 
          : msg
      )
    );
    
    if (isOnline && onSendMessage) {
      try {
        await onSendMessage(pendingMessage.content, pendingMessage.attachments || []);
        
        // 发送成功，从待发送列表中移除
        if (dbInstance) {
          await dbInstance.delete('pendingMessages', messageId);
          setPendingMessages(prev => prev.filter(msg => msg.id !== messageId));
        }
        
        // 更新消息状态
        setMessages(prev => 
          prev.map(msg => 
            msg.id === messageId 
              ? { ...msg, status: 'delivered' } 
              : msg
          )
        );
        
        // 更新IndexedDB中的消息状态
        if (dbInstance) {
          const messageInDb = await dbInstance.get('messages', messageId);
          if (messageInDb) {
            await dbInstance.put('messages', {
              ...messageInDb,
              status: 'delivered'
            });
          }
        }
        
        setNotification({
          open: true,
          message: '消息重发成功',
          severity: 'success'
        });
      } catch (error) {
        console.error('重新发送消息失败:', error);
        
        // 更新消息状态
        setMessages(prev => 
          prev.map(msg => 
            msg.id === messageId 
              ? { ...msg, status: 'error', pendingRetry: true } 
              : msg
          )
        );
        
        // 更新重试计数
        if (dbInstance) {
          const updatedPendingMsg = {
            ...pendingMessage,
            retryCount: (pendingMessage.retryCount || 0) + 1
          };
          
          await dbInstance.put('pendingMessages', updatedPendingMsg);
        }
        
        setNotification({
          open: true,
          message: '消息重发失败，请稍后再试',
          severity: 'error'
        });
      }
    } else {
      setNotification({
        open: true,
        message: '您当前处于离线状态，无法发送消息',
        severity: 'warning'
      });
    }
  };
  
  // 滚动到最新消息
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // 发送正在输入状态
  const handleTyping = () => {
    if (isConnected && conversationId) {
      // 清除之前的定时器
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
      }
      
      // 发送正在输入状态
      sendWsMessage(JSON.stringify({
        type: 'typing',
        isTyping: true,
        userId: currentUser.id,
        conversationId
      }));
      
      // 5秒后发送停止输入状态
      typingTimeoutRef.current = setTimeout(() => {
        if (isConnected) {
          sendWsMessage(JSON.stringify({
            type: 'typing',
            isTyping: false,
            userId: currentUser.id,
            conversationId
          }));
        }
      }, 5000);
    }
  };

  // 处理文件选择
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      const filesArray = Array.from(event.target.files);
      setAttachments([...attachments, ...filesArray]);
    }
  };

  // 触发文件选择对话框
  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  // 移除附件
  const removeAttachment = (index: number) => {
    setAttachments(attachments.filter((_, i) => i !== index));
  };

  // 加载更多消息
  const loadMoreMessages = async () => {
    if (onLoadMoreMessages) {
      setLoadingMore(true);
      try {
        const olderMessages = await onLoadMoreMessages();
        
        // 转换日期格式
        const formattedOlderMessages = olderMessages.map(msg => ({
          ...msg,
          timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp)
        }));
        
        // 检查并防止重复消息
        const existingIds = new Set(messages.map(msg => msg.id));
        const uniqueOlderMessages = formattedOlderMessages.filter(
          msg => !existingIds.has(msg.id)
        );
        
        if (uniqueOlderMessages.length > 0) {
          setMessages([...uniqueOlderMessages, ...messages]);
          
          // 保存当前滚动位置，防止跳动
          if (messageListRef.current) {
            const scrollHeight = messageListRef.current.scrollHeight;
            const scrollTop = messageListRef.current.scrollTop;
            
            // 在消息列表更新后恢复滚动位置
            setTimeout(() => {
              if (messageListRef.current) {
                const newScrollHeight = messageListRef.current.scrollHeight;
                const heightDiff = newScrollHeight - scrollHeight;
                messageListRef.current.scrollTop = scrollTop + heightDiff;
              }
            }, 50);
          }
        } else {
          setNotification({
            open: true,
            message: '没有更早的消息了',
            severity: 'info'
          });
        }
      } catch (error) {
        console.error("加载更多消息失败:", error);
        setNotification({
          open: true,
          message: '加载更多消息失败',
          severity: 'error'
        });
      } finally {
        setLoadingMore(false);
      }
    }
  };
  
  // 打开消息上下文菜单
  const handleMessageContextMenu = (event: React.MouseEvent, messageId: string) => {
    event.preventDefault();
    setMessageContextMenu({
      mouseX: event.clientX - 2,
      mouseY: event.clientY - 4,
      messageId
    });
  };
  
  // 关闭消息上下文菜单
  const handleCloseMessageContextMenu = () => {
    setMessageContextMenu(null);
  };
  
  // 复制消息内容
  const handleCopyMessage = () => {
    if (messageContextMenu?.messageId) {
      const message = messages.find(msg => msg.id === messageContextMenu.messageId);
      if (message) {
        navigator.clipboard.writeText(message.content);
        setNotification({
          open: true,
          message: '消息已复制到剪贴板',
          severity: 'success'
        });
      }
    }
    handleCloseMessageContextMenu();
  };
  
  // 删除消息
  const handleDeleteMessage = () => {
    if (messageContextMenu?.messageId) {
      // 软删除消息
      setMessages(prevMessages => 
        prevMessages.map(msg => 
          msg.id === messageContextMenu.messageId 
            ? { ...msg, isDeleted: true } 
            : msg
        )
      );
      
      // 如果WebSocket连接可用，发送删除消息通知
      if (isConnected && conversationId) {
        sendWsMessage(JSON.stringify({
          type: 'delete_message',
          messageId: messageContextMenu.messageId,
          conversationId
        }));
      }
      
      setNotification({
        open: true,
        message: '消息已删除',
        severity: 'success'
      });
    }
    handleCloseMessageContextMenu();
  };
  
  // 关闭通知
  const handleCloseNotification = () => {
    setNotification({
      ...notification,
      open: false
    });
  };

  // 监听消息变化，滚动到底部
  useEffect(() => {
    if (messages.length > 0 && initialMessages.length === 0) {
      scrollToBottom();
    }
  }, [messages, initialMessages.length]);

  // 格式化时间
  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // 格式化日期
  const formatDate = (date: Date) => {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    if (date.toDateString() === today.toDateString()) {
      return '今天';
    } else if (date.toDateString() === yesterday.toDateString()) {
      return '昨天';
    } else {
      return date.toLocaleDateString();
    }
  };

  // 表情选择器打开/关闭状态
  const isEmojiPickerOpen = Boolean(emojiAnchorEl);
  
  // 快速回复菜单打开/关闭状态
  const isQuickReplyMenuOpen = Boolean(quickReplyAnchorEl);
  
  // 打开表情选择器
  const handleEmojiPickerOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setEmojiAnchorEl(event.currentTarget);
  };
  
  // 关闭表情选择器
  const handleEmojiPickerClose = () => {
    setEmojiAnchorEl(null);
  };
  
  // 选择表情
  const handleEmojiSelect = (emoji: string) => {
    setInputValue(prevValue => prevValue + emoji);
    handleEmojiPickerClose();
  };
  
  // 打开快速回复菜单
  const handleQuickReplyMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
    setQuickReplyAnchorEl(event.currentTarget);
  };
  
  // 关闭快速回复菜单
  const handleQuickReplyMenuClose = () => {
    setQuickReplyAnchorEl(null);
  };
  
  // 选择快速回复
  const handleQuickReplySelect = (reply: string) => {
    setInputValue(reply);
    handleQuickReplyMenuClose();
  };
  
  // 切换文本格式
  const toggleTextFormat = (format: 'bold' | 'italic') => {
    setTextFormat(prev => ({
      ...prev,
      [format]: !prev[format]
    }));
  };
  
  // 添加格式化标记到文本
  const addFormatToText = (text: string): string => {
    let formattedText = text;
    
    if (textFormat.bold) {
      formattedText = `**${formattedText}**`;
    }
    
    if (textFormat.italic) {
      formattedText = `*${formattedText}*`;
    }
    
    return formattedText;
  };
  
  // 解析格式化文本
  const parseFormattedText = (text: string): React.ReactNode => {
    // 简单的Markdown解析
    const boldRegex = /\*\*(.*?)\*\*/g;
    const italicRegex = /\*(.*?)\*/g;
    const emojiRegex = /([\u{1F300}-\u{1F6FF}])/gu;
    
    // 先替换加粗文本
    let parts = text.split(boldRegex);
    let result: React.ReactNode[] = [];
    
    for (let i = 0; i < parts.length; i++) {
      if (i % 2 === 0) {
        // 普通文本或斜体
        const italicParts = parts[i].split(italicRegex);
        for (let j = 0; j < italicParts.length; j++) {
          if (j % 2 === 0) {
            // 普通文本或表情
            const emojiParts = italicParts[j].split(emojiRegex);
            for (let k = 0; k < emojiParts.length; k++) {
              if (emojiParts[k].match(emojiRegex)) {
                // 表情
                result.push(
                  <span key={`emoji-${i}-${j}-${k}`} style={{ fontSize: '1.2em' }}>
                    {emojiParts[k]}
                  </span>
                );
              } else if (emojiParts[k]) {
                // 普通文本
                result.push(emojiParts[k]);
              }
            }
          } else {
            // 斜体
            result.push(<em key={`italic-${i}-${j}`}>{italicParts[j]}</em>);
          }
        }
      } else {
        // 加粗文本
        result.push(<strong key={`bold-${i}`}>{parts[i]}</strong>);
      }
    }
    
    return result;
  };
  
  // 更新渲染消息气泡函数，支持格式化文本
  const renderMessage = (message: Message) => {
    if (message.isDeleted) {
      return (
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            mb: 2,
          }}
        >
          <Typography variant="body2" color="text.secondary" fontStyle="italic">
            此消息已被删除
          </Typography>
        </Box>
      );
    }
    
    const isCurrentUser = message.sender === (currentUser.role === 'patient' ? 'patient' : 'doctor');
    
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: isCurrentUser ? 'flex-end' : 'flex-start',
          mb: 2,
        }}
        onContextMenu={(e) => handleMessageContextMenu(e, message.id)}
      >
        {!isCurrentUser && (
          <ListItemAvatar sx={{ minWidth: 40 }}>
            <Avatar
              src={recipient.avatar}
              alt={recipient.name}
              sx={{ width: 36, height: 36 }}
            />
          </ListItemAvatar>
        )}
        
        <Box sx={{ maxWidth: '70%' }}>
          <Card
            variant="outlined"
            sx={{
              bgcolor: isCurrentUser ? theme.palette.primary.light : theme.palette.background.paper,
              color: isCurrentUser ? theme.palette.primary.contrastText : 'inherit',
              borderRadius: 2,
              boxShadow: 1,
            }}
          >
            <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
              <Typography variant="body1">
                {parseFormattedText(message.content)}
              </Typography>
              
              {message.attachments && message.attachments.length > 0 && (
                <Box sx={{ mt: 1 }}>
                  {message.attachments.map(attachment => (
                    <Box
                      key={attachment.id}
                      component="a"
                      href={attachment.url}
                      target="_blank"
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        textDecoration: 'none',
                        color: 'inherit',
                        mt: 0.5,
                      }}
                    >
                      {attachment.type === 'image' ? (
                        <Box>
                          <ImageIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="caption">{attachment.name}</Typography>
                          <Box 
                            component="img" 
                            src={attachment.url} 
                            alt={attachment.name}
                            sx={{ 
                              mt: 1, 
                              maxWidth: '100%', 
                              maxHeight: 200, 
                              borderRadius: 1 
                            }}
                          />
                        </Box>
                      ) : (
                        <Box>
                          <AttachFileIcon fontSize="small" sx={{ mr: 0.5 }} />
                          <Typography variant="caption">{attachment.name}</Typography>
                        </Box>
                      )}
                    </Box>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>
          
          <Box
            sx={{
              display: 'flex',
              justifyContent: isCurrentUser ? 'flex-end' : 'flex-start',
              alignItems: 'center',
              mt: 0.5,
            }}
          >
            <Typography variant="caption" color="textSecondary">
              {formatTime(message.timestamp)}
            </Typography>
            
            {isCurrentUser && (
              <Box component="span" ml={0.5} display="flex" alignItems="center">
                {message.status === 'pending' && (
                  <Typography component="span" color="text.secondary" variant="caption">
                    待发送
                  </Typography>
                )}
                {message.status === 'sent' && '✓'}
                {message.status === 'delivered' && '✓✓'}
                {message.status === 'read' && (
                  <Typography component="span" color="primary" variant="caption">
                    ✓✓
                  </Typography>
                )}
                {message.status === 'error' && (
                  <>
                    <Typography component="span" color="error" variant="caption" sx={{ mr: 0.5 }}>
                      !
                    </Typography>
                    {message.pendingRetry && (
                      <Button 
                        size="small" 
                        color="error" 
                        variant="text" 
                        sx={{ minWidth: 'auto', p: '2px 5px', fontSize: '0.7rem' }}
                        onClick={() => retryMessage(message.id)}
                      >
                        重试
                      </Button>
                    )}
                  </>
                )}
              </Box>
            )}
          </Box>
        </Box>
        
        {isCurrentUser && (
          <ListItemAvatar sx={{ minWidth: 40, ml: 1 }}>
            <Avatar
              src={currentUser.avatar}
              alt={currentUser.name}
              sx={{ width: 36, height: 36 }}
            />
          </ListItemAvatar>
        )}
      </Box>
    );
  };

  // 渲染虚拟滚动行项目
  const renderVirtualRow = useCallback(({ index, style }: ListChildComponentProps) => {
    // 防止渲染空行
    if (index >= messages.length) return null;
    
    const message = messages[index];
    
    // 获取前一条消息，用于决定是否显示日期分隔线
    const prevMessage = index > 0 ? messages[index - 1] : null;
    const showDateDivider = !prevMessage || !isSameDay(message.timestamp, prevMessage.timestamp);
    
    return (
      <div style={{ ...style, height: 'auto' }}>
        {showDateDivider && (
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              my: 2,
            }}
          >
            <Divider sx={{ flexGrow: 1 }} />
            <Typography variant="caption" color="textSecondary" sx={{ mx: 1 }}>
              {formatDate(message.timestamp)}
            </Typography>
            <Divider sx={{ flexGrow: 1 }} />
          </Box>
        )}
        {renderMessage(message)}
      </div>
    );
  }, [messages]);
  
  // 估算每行的高度（考虑消息长度和附件）
  const estimateRowHeight = useCallback((index: number) => {
    const message = messages[index];
    let height = 80; // 基础高度
    
    // 根据消息内容长度增加高度
    const contentLength = message.content?.length || 0;
    height += Math.floor(contentLength / 50) * 20; // 每50个字符增加20px
    
    // 如果有附件，增加高度
    if (message.attachments && message.attachments.length > 0) {
      // 图片附件需要更多空间
      const hasImageAttachment = message.attachments.some(a => a.type === 'image');
      height += hasImageAttachment ? 220 : 40 * message.attachments.length;
    }
    
    // 如果需要显示日期分隔线，增加高度
    const prevMessage = index > 0 ? messages[index - 1] : null;
    if (!prevMessage || !isSameDay(message.timestamp, prevMessage.timestamp)) {
      height += 40;
    }
    
    return height;
  }, [messages]);
  
  // 滚动到底部的实现，支持虚拟滚动
  const scrollToBottomEnhanced = useCallback(() => {
    if (virtualScrollEnabled && messages.length > 0) {
      // 对于虚拟滚动，我们需要滚动到最后一个元素
      const listInstance = messageListRef.current;
      if (listInstance && typeof listInstance.scrollToItem === 'function') {
        listInstance.scrollToItem(messages.length - 1, 'end');
      }
    } else {
      // 使用常规的滚动方法
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [virtualScrollEnabled, messages.length]);
  
  // 替换原有的scrollToBottom
  const scrollToBottom = scrollToBottomEnhanced;

  return (
    <Paper elevation={0} sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* 聊天头部 */}
      <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider', bgcolor: theme.palette.background.paper }}>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box display="flex" alignItems="center">
            <Badge
              overlap="circular"
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              variant="dot"
              color={statusColors[recipient.status as OnlineStatus] || 'default'}
            >
              <Avatar src={recipient.avatar} alt={recipient.name} />
            </Badge>
            <Box ml={2}>
              <Typography variant="h6">{recipient.name}</Typography>
              <Typography variant="body2" color="textSecondary">
                {isTyping ? (
                  '正在输入...'
                ) : (
                  statusText[recipient.status as OnlineStatus] || '离线'
                )}
                {recipient.status === 'offline' && recipient.lastSeen && (
                  <>, 上次在线: {formatDate(recipient.lastSeen)}</>
                )}
              </Typography>
            </Box>
          </Box>
          
          <Box>
            {/* 增加通话按钮 */}
            <Tooltip title="语音通话">
              <IconButton>
                <PhoneIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="视频通话">
              <IconButton>
                <VideoCallIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title={isConnected ? '消息同步已连接' : '消息同步未连接'}>
              <IconButton color={isConnected ? 'success' : 'default'}>
                <SyncIcon />
              </IconButton>
            </Tooltip>
            <Tooltip title="更多信息">
              <IconButton>
                <MoreVertIcon />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>
      </Box>
      
      {/* 消息列表 - 使用虚拟滚动或标准滚动 */}
      <Box
        ref={messageListRef}
        sx={{
          flexGrow: 1,
          overflow: 'auto',
          bgcolor: theme.palette.grey[50],
          p: 2,
        }}
      >
        {/* 加载更多按钮 */}
        {onLoadMoreMessages && messages.length > 0 && (
          <Box textAlign="center" mb={2}>
            <Button
              variant="text"
              disabled={loadingMore}
              onClick={loadMoreMessages}
              startIcon={loadingMore && <CircularProgress size={16} />}
            >
              {loadingMore ? '加载中...' : '加载更多消息'}
            </Button>
          </Box>
        )}
        
        {/* 连接中指示器 */}
        {reconnecting && (
          <Box 
            sx={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              mb: 2,
              p: 1
            }}
          >
            <CircularProgress size={14} sx={{ mr: 1 }} />
            <Typography variant="body2" color="text.secondary">
              正在重新连接...
            </Typography>
          </Box>
        )}
        
        {/* 消息组 - 有条件地使用虚拟滚动 */}
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height="100%">
            <CircularProgress />
          </Box>
        ) : messages.length === 0 ? (
          <Box 
            display="flex" 
            flexDirection="column"
            justifyContent="center" 
            alignItems="center" 
            height="100%"
            p={3}
          >
            <InfoOutlinedIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
            <Typography variant="body1" color="textSecondary" align="center">
              没有消息记录，发送一条消息开始对话吧
            </Typography>
            <Button 
              variant="outlined" 
              sx={{ mt: 2 }}
              onClick={() => setInputValue("您好，我有一些问题想咨询您。")}
            >
              开始对话
            </Button>
          </Box>
        ) : virtualScrollEnabled ? (
          // 使用虚拟滚动渲染大量消息
          <Box sx={{ height: '100%', width: '100%' }}>
            <AutoSizer>
              {({ height, width }) => (
                <FixedSizeList
                  ref={messageListRef}
                  height={height}
                  width={width}
                  itemCount={messages.length}
                  itemSize={120} // 使用动态估算的高度
                  overscanCount={5}
                  onItemsRendered={({ visibleStartIndex, visibleStopIndex }) => {
                    // 如果最后一个消息可见，设置所有消息为已读
                    if (visibleStopIndex === messages.length - 1) {
                      const unreadMessages = messages.filter(
                        m => m.sender !== currentUser.role && m.status !== 'read'
                      );
                      if (unreadMessages.length > 0 && isConnected && sendWsMessage) {
                        sendWsMessage(JSON.stringify({
                          type: 'read_receipt',
                          messageIds: unreadMessages.map(m => m.id),
                          conversationId
                        }));
                      }
                    }
                  }}
                >
                  {renderVirtualRow}
                </FixedSizeList>
              )}
            </AutoSizer>
          </Box>
        ) : (
          // 常规渲染少量消息
          messages.map((message, index) => (
            <React.Fragment key={message.id}>
              {/* 日期分隔线 */}
              {index === 0 || !isSameDay(message.timestamp, messages[index - 1].timestamp) ? (
                <Box
                  sx={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    my: 2,
                  }}
                >
                  <Divider sx={{ flexGrow: 1 }} />
                  <Typography variant="caption" color="textSecondary" sx={{ mx: 1 }}>
                    {formatDate(message.timestamp)}
                  </Typography>
                  <Divider sx={{ flexGrow: 1 }} />
                </Box>
              ) : null}
              
              {renderMessage(message)}
            </React.Fragment>
          ))
        )}
        
        {/* 用于滚动到底部的引用元素 */}
        <div ref={messagesEndRef} />
      </Box>
      
      {/* 附件预览 */}
      {attachments.length > 0 && (
        <Box sx={{ p: 1, borderTop: 1, borderColor: 'divider', bgcolor: theme.palette.background.paper }}>
          <Box display="flex" flexWrap="wrap" gap={1}>
            {attachments.map((file, index) => (
              <Chip
                key={index}
                label={file.name}
                onDelete={() => removeAttachment(index)}
                icon={file.type.startsWith('image/') ? <ImageIcon /> : <AttachFileIcon />}
                variant="outlined"
              />
            ))}
          </Box>
        </Box>
      )}
      
      {/* 输入区域 */}
      <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider', bgcolor: theme.palette.background.paper }}>
        <Box display="flex" flexDirection="column">
          {/* 格式化工具栏 */}
          <Box display="flex" alignItems="center" mb={1}>
            <Tooltip title="加粗">
              <IconButton 
                size="small" 
                onClick={() => toggleTextFormat('bold')}
                color={textFormat.bold ? 'primary' : 'default'}
              >
                <FormatBoldIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="斜体">
              <IconButton 
                size="small" 
                onClick={() => toggleTextFormat('italic')}
                color={textFormat.italic ? 'primary' : 'default'}
              >
                <FormatItalicIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="快速回复">
              <IconButton size="small" onClick={handleQuickReplyMenuOpen}>
                <MarkChatReadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          
          <Box display="flex" alignItems="center">
            <TextField
              placeholder="输入消息..."
              variant="outlined"
              fullWidth
              multiline
              maxRows={4}
              value={inputValue}
              onChange={(e) => {
                setInputValue(e.target.value);
                handleTyping();
              }}
              onKeyPress={handleKeyPress}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={triggerFileSelect} size="small">
                      <AttachFileIcon />
                    </IconButton>
                    <IconButton size="small" onClick={handleEmojiPickerOpen}>
                      <EmojiEmotionsIcon />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{ mr: 1 }}
            />
            <Button
              variant="contained"
              color="primary"
              endIcon={<SendIcon />}
              onClick={() => {
                const formattedText = addFormatToText(inputValue);
                setInputValue(formattedText);
                handleSendMessage();
              }}
              disabled={inputValue.trim() === '' && attachments.length === 0}
            >
              发送
            </Button>
          </Box>
        </Box>
        
        {/* 隐藏的文件输入 */}
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          onChange={handleFileSelect}
          multiple
        />
        
        {/* 表情选择器 */}
        <Popover
          open={isEmojiPickerOpen}
          anchorEl={emojiAnchorEl}
          onClose={handleEmojiPickerClose}
          anchorOrigin={{
            vertical: 'top',
            horizontal: 'left',
          }}
          transformOrigin={{
            vertical: 'bottom',
            horizontal: 'left',
          }}
        >
          <Box sx={{ p: 2, maxWidth: 300 }}>
            <Grid container spacing={1}>
              {EMOJIS.map((emoji, index) => (
                <Grid item key={index}>
                  <IconButton
                    onClick={() => handleEmojiSelect(emoji)}
                    size="small"
                    sx={{ fontSize: '1.2rem' }}
                  >
                    {emoji}
                  </IconButton>
                </Grid>
              ))}
            </Grid>
          </Box>
        </Popover>
        
        {/* 快速回复菜单 */}
        <Menu
          anchorEl={quickReplyAnchorEl}
          open={isQuickReplyMenuOpen}
          onClose={handleQuickReplyMenuClose}
        >
          {QUICK_REPLIES.map((reply, index) => (
            <MenuItem key={index} onClick={() => handleQuickReplySelect(reply)}>
              {reply}
            </MenuItem>
          ))}
        </Menu>
      </Box>
      
      {/* 消息上下文菜单 */}
      <Menu
        open={messageContextMenu !== null}
        onClose={handleCloseMessageContextMenu}
        anchorReference="anchorPosition"
        anchorPosition={
          messageContextMenu !== null
            ? { top: messageContextMenu.mouseY, left: messageContextMenu.mouseX }
            : undefined
        }
      >
        <MenuItem onClick={handleCopyMessage}>
          <ContentCopyIcon fontSize="small" sx={{ mr: 1 }} />
          复制消息
        </MenuItem>
        <MenuItem onClick={handleDeleteMessage}>
          <DeleteOutlineIcon fontSize="small" sx={{ mr: 1 }} />
          删除消息
        </MenuItem>
      </Menu>
      
      {/* 通知提示 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={4000}
        onClose={handleCloseNotification}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={handleCloseNotification} 
          severity={notification.severity}
          variant="filled"
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Paper>
  );
};

// 检查两个日期是否是同一天
function isSameDay(date1: Date, date2: Date): boolean {
  return (
    date1.getFullYear() === date2.getFullYear() &&
    date1.getMonth() === date2.getMonth() &&
    date1.getDate() === date2.getDate()
  );
}

export default ChatComponent; 