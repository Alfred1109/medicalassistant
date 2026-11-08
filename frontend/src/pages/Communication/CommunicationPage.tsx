import React from 'react';
import { useSelector } from 'react-redux';
import {
  Box,
  Typography,
  Paper,
  Grid,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  ListItemSecondaryAction,
  Avatar,
  TextField,
  Button,
  Divider,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import PersonIcon from '@mui/icons-material/Person';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import RefreshIcon from '@mui/icons-material/Refresh';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import AddIcon from '@mui/icons-material/Add';
import type { RootState } from '../../store';
import { chatApi } from '../../services/chatService';
import type { ConversationDto, MessageDto } from '../../services/chatService';
import {
  ChatWsClient,
  applyChatReadReceipt,
  ChatWsSendError,
  generateClientMessageId,
  type ChatWsStatus,
  type ChatWsStatusInfo,
  type PendingChatMessage,
  type WsChatMessage,
} from '../../services/chatWsService';

const CONVERSATIONS_PAGE_SIZE = 50;
const MESSAGES_PAGE_SIZE = 30;
// 实时通道：/ws/chat/{id}（协议确认见 services/chatWsService.ts 文件头）。
// 发送与接收对方消息走 WS；会话列表/未读/已读仍走 REST。
// 降级策略：WS 断连或非成员 4403 时，消息轮询恢复 15s 兜底并明示「轮询模式」；
// WS 在线时消息轮询放缓到 60s 仅作漂移修正。会话列表轮询恒为 30s（REST）。
const CONVERSATIONS_POLL_MS = 30_000;
const MESSAGES_POLL_WS_MS = 60_000;
const MESSAGES_POLL_FALLBACK_MS = 15_000;

const formatTime = (iso?: string) => {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};

type CommunicationView = 'medical-staff' | 'patient';

const viewContent = {
  'medical-staff': {
    title: '患者沟通',
    createLabel: '新建会话',
    emptyText: '暂无会话，点击「新建会话」开始沟通',
    participantHint: '输入患者端的用户ID发起会话（会话对方为患者）。',
    missingParticipant: '该用户ID不存在，请确认对方已注册',
    ParticipantIcon: PersonIcon,
    roleLabel: (role?: string) => role === 'patient' ? '患者' : role || '',
  },
  patient: {
    title: '医生沟通',
    createLabel: '联系医生/健康管理师',
    emptyText: '暂无会话，点击「联系医生/健康管理师」发起沟通',
    participantHint: '输入医生或健康管理师的用户ID发起会话（对方 ID 请向本人/机构获取；系统暂无患者可用的联系人目录接口）。',
    missingParticipant: '该用户ID不存在，请向您的医生/健康管理师确认账号ID',
    ParticipantIcon: LocalHospitalIcon,
    roleLabel: (role?: string) => role === 'doctor' ? '医生' : role === 'health_manager' ? '健康管理师' : role || '',
  },
};

const CommunicationPage: React.FC<{ view: CommunicationView }> = ({ view }) => {
  const content = viewContent[view];
  const { ParticipantIcon } = content;
  const currentUser = useSelector((state: RootState) => state.auth.user);

  const [conversations, setConversations] = React.useState<ConversationDto[]>([]);
  const [conversationsLoading, setConversationsLoading] = React.useState(true);
  const [conversationsError, setConversationsError] = React.useState<string | null>(null);

  const [unreadTotal, setUnreadTotal] = React.useState(0);

  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<MessageDto[]>([]);
  const [messagesLoading, setMessagesLoading] = React.useState(false);
  const [messagesError, setMessagesError] = React.useState<string | null>(null);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [sending, setSending] = React.useState(false);

  const [newMessage, setNewMessage] = React.useState('');
  const [createOpen, setCreateOpen] = React.useState(false);
  const [participantInput, setParticipantInput] = React.useState('');
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // WS 实时通道状态与乐观消息
  const [wsStatus, setWsStatus] = React.useState<ChatWsStatus>('idle');
  const [wsInfo, setWsInfo] = React.useState<ChatWsStatusInfo>({});
  const [pendingMessages, setPendingMessages] = React.useState<PendingChatMessage[]>([]);
  const [sendError, setSendError] = React.useState<string | null>(null);

  const activeIdRef = React.useRef<string | null>(null);
  activeIdRef.current = activeId;

  // 以服务端消息 upsert：按 id 替换（广播与轮询重复/已读状态刷新），否则追加；
  // 并按 client_message_id 清掉对应的乐观占位（去重：挂起队列比对）
  const upsertMessage = React.useCallback((message: WsChatMessage) => {
    setMessages((prev) => {
      if (message.conversation_id && message.conversation_id !== activeIdRef.current) {
        return prev;
      }
      const idx = prev.findIndex((m) => m.id === message.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = message;
        return next;
      }
      return [...prev, message];
    });
    if (message.client_message_id) {
      const clientMessageId = message.client_message_id;
      setPendingMessages((prev) => prev.filter((p) => p.clientMessageId !== clientMessageId));
    }
  }, []);

  const markPendingFailed = React.useCallback((clientMessageId: string) => {
    setPendingMessages((prev) =>
      prev.map((p) =>
        p.clientMessageId === clientMessageId ? { ...p, status: 'failed' as const } : p
      )
    );
  }, []);

  const loadConversations = React.useCallback(async (silent = false) => {
    if (!silent) setConversationsLoading(true);
    try {
      const data = await chatApi.getConversations({ limit: CONVERSATIONS_PAGE_SIZE });
      setConversations(data);
      setConversationsError(null);
    } catch (error: any) {
      setConversationsError(error?.response?.data?.detail || '加载会话列表失败');
    } finally {
      setConversationsLoading(false);
    }
  }, []);

  const loadUnreadTotal = React.useCallback(async () => {
    try {
      const data = await chatApi.getUnreadCount();
      setUnreadTotal(data.count);
    } catch {
      // 未读总数拉取失败不阻塞主流程，等待下一轮刷新
    }
  }, []);

  // 广播到达时合并刷新会话列表/未读数（REST，去抖避免消息突发时打爆接口）
  const conversationsRefreshTimerRef = React.useRef<number | null>(null);
  const scheduleConversationsRefresh = React.useCallback(() => {
    if (conversationsRefreshTimerRef.current !== null) return;
    conversationsRefreshTimerRef.current = window.setTimeout(() => {
      conversationsRefreshTimerRef.current = null;
      loadConversations(true);
      loadUnreadTotal();
    }, 800);
  }, [loadConversations, loadUnreadTotal]);

  // WS 接通（含断线重连成功）后用 REST 回补断连窗口内可能漏掉的消息
  const backfillAfterReconnect = React.useCallback(async () => {
    const conversationId = activeIdRef.current;
    if (!conversationId) return;
    try {
      const data = await chatApi.getMessages(conversationId, MESSAGES_PAGE_SIZE);
      if (activeIdRef.current === conversationId) {
        setMessages(data);
      }
    } catch {
      // 回补失败由消息轮询兜底
    }
    loadConversations(true);
  }, [loadConversations]);

  const wsClientRef = React.useRef<ChatWsClient | null>(null);
  const onServerMessageRef = React.useRef<(message: WsChatMessage) => void>(() => {});
  onServerMessageRef.current = (message) => {
    const currentId = activeIdRef.current;
    if (currentId && message.conversation_id === currentId) {
      upsertMessage(message);
      if (currentUser && message.sender_id !== currentUser.id) {
        // 查看会话期间收到对方消息：通过 REST 标读，后端落库后向双方广播回执
        chatApi.markConversationAsRead(currentId).catch(() => {});
      }
    }
    scheduleConversationsRefresh();
  };
  const onStatusChangeRef = React.useRef<(status: ChatWsStatus, info: ChatWsStatusInfo) => void>(
    () => {}
  );
  onStatusChangeRef.current = (status, info) => {
    setWsStatus(status);
    setWsInfo(info);
    if (status === 'connected') {
      backfillAfterReconnect();
    }
  };

  // WS 客户端生命周期：随登录态创建/销毁，连接目标随当前会话切换
  React.useEffect(() => {
    if (!currentUser) return;
    const client = new ChatWsClient({
      onReadReceipt: (receipt) => {
        setMessages((previous) => applyChatReadReceipt(
          previous, receipt, activeIdRef.current, currentUser.id,
        ));
        scheduleConversationsRefresh();
      },
      onBroadcastMessage: (message) => onServerMessageRef.current(message),
      onAck: (message) => onServerMessageRef.current(message),
      onStatusChange: (status, info) => onStatusChangeRef.current(status, info),
    });
    wsClientRef.current = client;
    return () => {
      client.disconnect();
      wsClientRef.current = null;
    };
  }, [currentUser]);

  React.useEffect(() => {
    const client = wsClientRef.current;
    if (!client) return;
    if (!activeId) {
      client.disconnect();
      return;
    }
    client.connect(activeId);
  }, [activeId, currentUser]);

  // 打开会话：拉取最新一页消息（后端会把收到的消息自动置为已读），再显式标记整段已读
  const openConversation = React.useCallback(async (conversationId: string) => {
    setActiveId(conversationId);
    setMessages([]);
    setMessagesError(null);
    setMessagesLoading(true);
    try {
      const data = await chatApi.getMessages(conversationId, MESSAGES_PAGE_SIZE);
      setMessages(data);
      try {
        await chatApi.markConversationAsRead(conversationId);
      } catch {
        // 已读标记失败不阻塞消息展示，未读数会在下轮刷新修正
      }
      await Promise.all([loadConversations(true), loadUnreadTotal()]);
    } catch (error: any) {
      setMessagesError(error?.response?.data?.detail || '加载消息失败');
    } finally {
      setMessagesLoading(false);
    }
  }, [loadConversations, loadUnreadTotal]);

  // 初始加载 + REST 轮询（会话列表/未读数恒走 REST，30s 兜底刷新）
  React.useEffect(() => {
    if (!currentUser) return;
    loadConversations();
    loadUnreadTotal();
    const timer = window.setInterval(() => {
      loadConversations(true);
      loadUnreadTotal();
    }, CONVERSATIONS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [currentUser, loadConversations, loadUnreadTotal]);

  // 当前会话消息轮询：WS 在线时 60s 仅作漂移修正；断连/降级时恢复 15s 兜底
  React.useEffect(() => {
    if (!activeId) return;
    const interval = wsStatus === 'connected' ? MESSAGES_POLL_WS_MS : MESSAGES_POLL_FALLBACK_MS;
    const timer = window.setInterval(async () => {
      try {
        const data = await chatApi.getMessages(activeId, MESSAGES_PAGE_SIZE);
        if (activeIdRef.current === activeId) {
          setMessages(data);
        }
      } catch {
        // 轮询失败静默等待下一轮
      }
    }, interval);
    return () => window.clearInterval(timer);
  }, [activeId, wsStatus]);

  const handleLoadEarlier = async () => {
    if (!activeId || messages.length === 0 || loadingMore) return;
    setLoadingMore(true);
    try {
      const earlier = await chatApi.getMessages(activeId, MESSAGES_PAGE_SIZE, messages[0].id);
      const existingIds = new Set(messages.map((m) => m.id));
      setMessages([...earlier.filter((m) => !existingIds.has(m.id)), ...messages]);
    } catch (error: any) {
      setMessagesError(error?.response?.data?.detail || '加载更早消息失败');
    } finally {
      setLoadingMore(false);
    }
  };

  const handleSendMessage = async () => {
    const content = newMessage.trim();
    if (!content || !activeId || sending) return;
    const client = wsClientRef.current;

    if (client && client.isConnected()) {
      // WS 路径：乐观占位 → ack/广播后以服务端落库消息替换；失败保留占位供重试。
      // 发送守卫（sending）保证同一时刻至多一条在途消息，错误帧可无歧义映射。
      const clientMessageId = generateClientMessageId();
      setPendingMessages((prev) => [...prev, { clientMessageId, content, status: 'pending' }]);
      setNewMessage('');
      setSendError(null);
      setSending(true);
      try {
        const saved = await client.send(content, clientMessageId);
        upsertMessage(saved);
      } catch (error: any) {
        markPendingFailed(clientMessageId);
        setSendError(
          error instanceof ChatWsSendError && error.errorCode === 'MESSAGE_PERSIST_FAILED'
            ? '消息落库失败，请重试'
            : '发送失败，请重试'
        );
      } finally {
        setSending(false);
      }
      return;
    }

    // WS 未连接（降级/重连期间）：REST 兜底发送，同步等待结果
    setSending(true);
    try {
      const saved = await chatApi.sendMessage(activeId, content);
      setMessages((prev) => [...prev, saved]);
      setNewMessage('');
      loadConversations(true);
    } catch (error: any) {
      setSendError(error?.response?.data?.detail || error?.message || '发送失败，请重试');
    } finally {
      setSending(false);
    }
  };

  const handleRetryPending = async (pending: PendingChatMessage) => {
    if (sending) return;
    const client = wsClientRef.current;
    if (!client || !client.isConnected() || !activeId) {
      // 降级期重试：改走 REST，成功后移除占位
      setSending(true);
      try {
        const saved = await chatApi.sendMessage(activeId!, pending.content);
        setMessages((prev) => [...prev, saved]);
        setPendingMessages((prev) =>
          prev.filter((p) => p.clientMessageId !== pending.clientMessageId)
        );
        setSendError(null);
        loadConversations(true);
      } catch (error: any) {
        setSendError(error?.response?.data?.detail || error?.message || '发送失败，请重试');
      } finally {
        setSending(false);
      }
      return;
    }
    setSendError(null);
    setPendingMessages((prev) =>
      prev.map((p) =>
        p.clientMessageId === pending.clientMessageId ? { ...p, status: 'pending' as const } : p
      )
    );
    setSending(true);
    try {
      // 复用同一 client_message_id：服务端幂等，若首投已落库则直接返回既有消息
      const saved = await client.send(pending.content, pending.clientMessageId);
      upsertMessage(saved);
    } catch {
      markPendingFailed(pending.clientMessageId);
    } finally {
      setSending(false);
    }
  };

  const handleCreateConversation = async () => {
    const participantId = participantInput.trim();
    if (!participantId || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      // participant_id 是对方的用户ID；后端按参与者校验读写权限
      const { id } = await chatApi.createConversation(participantId);
      setCreateOpen(false);
      setParticipantInput('');
      await loadConversations(true);
      await openConversation(id);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      setCreateError(
        detail === '指定的参与者不存在'
          ? content.missingParticipant
          : detail || '创建会话失败'
      );
    } finally {
      setCreating(false);
    }
  };

  if (!currentUser) {
    return (
      <Box>
        <Typography variant="h5" component="h1" gutterBottom>
          {content.title}
        </Typography>
        <Alert severity="warning">请先登录后再使用沟通功能。</Alert>
      </Box>
    );
  }

  const activeConversation = conversations.find((c) => c.id === activeId) || null;

  const renderWsStatusChip = () => {
    if (!activeId) return null;
    if (wsStatus === 'connected') {
      return <Chip size="small" color="success" variant="outlined" label="实时连接" />;
    }
    if (wsStatus === 'connecting') {
      return <Chip size="small" variant="outlined" label="连接中…" />;
    }
    if (wsStatus === 'reconnecting') {
      return <Chip size="small" color="warning" variant="outlined" label="实时连接中断，重连中…" />;
    }
    if (wsStatus === 'degraded') {
      return <Chip size="small" color="warning" variant="outlined" label="轮询模式" />;
    }
    return null;
  };

  const wsDegradedText =
    wsInfo.reason === 'forbidden'
      ? '无法接入实时通道：你不是该会话成员或会话不存在，已切换为轮询刷新。'
      : wsInfo.reason === 'auth'
        ? '实时通道登录校验未通过，已切换为轮询刷新；如长时间不恢复请重新登录。'
        : '实时通道暂不可用，已切换为轮询刷新。';

  const renderConversationItem = (conv: ConversationDto) => {
    const other = conv.other_user;
    const isActive = conv.id === activeId;
    return (
      <React.Fragment key={conv.id}>
        <ListItem button onClick={() => openConversation(conv.id)} selected={isActive}>
          <ListItemAvatar>
            <Avatar>
              <ParticipantIcon />
            </Avatar>
          </ListItemAvatar>
          <ListItemText
            primary={
              <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography component="span" variant="body1" noWrap>
                  {other?.name || '未知用户'}
                </Typography>
                {content.roleLabel(other?.role) && (
                  <Chip
                    component="span"
                    size="small"
                    label={content.roleLabel(other?.role)}
                    variant="outlined"
                  />
                )}
              </Box>
            }
            secondary={conv.last_message_preview || '暂无消息'}
          />
          {conv.unread_count > 0 && (
            <ListItemSecondaryAction>
              <Chip color="primary" size="small" label={conv.unread_count} />
            </ListItemSecondaryAction>
          )}
        </ListItem>
        <Divider />
      </React.Fragment>
    );
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h5" component="h1">
          {content.title}
          {unreadTotal > 0 && (
            <Chip color="primary" size="small" label={`未读 ${unreadTotal}`} sx={{ ml: 1 }} />
          )}
        </Typography>
        <Box>
          <Button startIcon={<AddIcon />} onClick={() => setCreateOpen(true)} sx={{ mr: 1 }}>
            {content.createLabel}
          </Button>
          <Button startIcon={<RefreshIcon />} onClick={() => { loadConversations(); loadUnreadTotal(); }}>
            刷新
          </Button>
        </Box>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={4}>
          <Paper sx={{ height: '70vh', overflow: 'auto' }}>
            {conversationsLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                <CircularProgress />
              </Box>
            ) : conversationsError ? (
              <Alert
                severity="error"
                sx={{ m: 2 }}
                action={
                  <Button color="inherit" size="small" onClick={() => loadConversations()}>
                    重试
                  </Button>
                }
              >
                {conversationsError}
              </Alert>
            ) : conversations.length === 0 ? (
              <Box sx={{ textAlign: 'center', py: 6, px: 2 }}>
                <ChatBubbleOutlineIcon sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                <Typography color="text.secondary">{content.emptyText}</Typography>
              </Box>
            ) : (
              <List>{conversations.map(renderConversationItem)}</List>
            )}
          </Paper>
        </Grid>

        <Grid item xs={8}>
          <Paper sx={{ height: '70vh', display: 'flex', flexDirection: 'column' }}>
            {!activeId ? (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                <Typography color="text.secondary">从左侧选择一个会话开始沟通</Typography>
              </Box>
            ) : (
              <>
                <Box
                  sx={{
                    p: 2,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <Typography variant="h6">
                    与 {activeConversation?.other_user?.name || '未知用户'} 的对话
                  </Typography>
                  {renderWsStatusChip()}
                </Box>

                {wsStatus === 'degraded' && (
                  <Alert severity="warning" sx={{ m: 2, mb: 0 }}>
                    {wsDegradedText}
                  </Alert>
                )}

                <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto' }}>
                  {messagesLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
                      <CircularProgress />
                    </Box>
                  ) : messagesError ? (
                    <Alert
                      severity="error"
                      action={
                        <Button color="inherit" size="small" onClick={() => activeId && openConversation(activeId)}>
                          重试
                        </Button>
                      }
                    >
                      {messagesError}
                    </Alert>
                  ) : messages.length === 0 ? (
                    <Typography color="text.secondary" align="center" sx={{ py: 6 }}>
                      暂无消息记录，发送一条消息开始对话吧
                    </Typography>
                  ) : (
                    <>
                      <Box sx={{ textAlign: 'center', mb: 2 }}>
                        <Button size="small" disabled={loadingMore} onClick={handleLoadEarlier}>
                          {loadingMore ? '加载中...' : '加载更早消息'}
                        </Button>
                      </Box>
                      {messages.map((message) => {
                        const isOwn = message.sender_id === currentUser.id;
                        return (
                          <Box
                            key={message.id}
                            sx={{
                              display: 'flex',
                              justifyContent: isOwn ? 'flex-end' : 'flex-start',
                              mb: 2,
                            }}
                          >
                            <Paper
                              sx={{
                                p: 2,
                                maxWidth: '70%',
                                bgcolor: isOwn ? 'primary.light' : 'grey.100',
                                color: isOwn ? 'white' : 'inherit',
                                opacity: message.deleted ? 0.6 : 1,
                              }}
                            >
                              <Typography variant="body1">
                                {message.deleted ? '此消息已被删除' : message.content}
                              </Typography>
                              <Typography variant="caption" display="block" sx={{ mt: 1, opacity: 0.7 }}>
                                {formatTime(message.timestamp)}
                                {isOwn && !message.deleted && (message.read ? ' · 已读' : ' · 未读')}
                              </Typography>
                            </Paper>
                          </Box>
                        );
                      })}
                      {/* WS 乐观消息：ack/广播后由服务端落库消息替换（upsert），失败保留重试 */}
                      {pendingMessages.map((pending) => (
                        <Box
                          key={pending.clientMessageId}
                          sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}
                        >
                          <Paper
                            sx={{
                              p: 2,
                              maxWidth: '70%',
                              bgcolor: pending.status === 'failed' ? 'error.main' : 'primary.light',
                              color: 'white',
                              opacity: pending.status === 'failed' ? 0.9 : 0.75,
                            }}
                          >
                            <Typography variant="body1">{pending.content}</Typography>
                            <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Typography variant="caption" sx={{ opacity: 0.85 }}>
                                {pending.status === 'pending' ? '发送中…' : '发送失败'}
                              </Typography>
                              {pending.status === 'failed' && (
                                <Button
                                  size="small"
                                  color="inherit"
                                  disabled={sending}
                                  onClick={() => handleRetryPending(pending)}
                                >
                                  重试
                                </Button>
                              )}
                            </Box>
                          </Paper>
                        </Box>
                      ))}
                    </>
                  )}
                </Box>

                {sendError && (
                  <Alert severity="error" sx={{ mx: 2, mb: 1 }} onClose={() => setSendError(null)}>
                    {sendError}
                  </Alert>
                )}

                <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider', display: 'flex' }}>
                  <TextField
                    fullWidth
                    placeholder="输入消息..."
                    variant="outlined"
                    value={newMessage}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewMessage(e.target.value)}
                    onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => {
                      if (e.key === 'Enter') handleSendMessage();
                    }}
                  />
                  <Button
                    variant="contained"
                    endIcon={<SendIcon />}
                    sx={{ ml: 1 }}
                    disabled={sending || !newMessage.trim()}
                    onClick={handleSendMessage}
                  >
                    发送
                  </Button>
                </Box>
              </>
            )}
          </Paper>
        </Grid>
      </Grid>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{content.createLabel}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {content.participantHint}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            label="对方用户ID"
            value={participantInput}
            onChange={(e) => setParticipantInput(e.target.value)}
          />
          {createError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {createError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>取消</Button>
          <Button variant="contained" disabled={creating || !participantInput.trim()} onClick={handleCreateConversation}>
            {creating ? '创建中...' : '创建'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CommunicationPage;
