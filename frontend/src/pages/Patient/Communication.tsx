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
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import RefreshIcon from '@mui/icons-material/Refresh';
import ChatBubbleOutlineIcon from '@mui/icons-material/ChatBubbleOutline';
import AddIcon from '@mui/icons-material/Add';
import type { RootState } from '../../store';
import { chatApi } from '../../services/chatService';
import type { ConversationDto, MessageDto } from '../../services/chatService';

const CONVERSATIONS_PAGE_SIZE = 50;
const MESSAGES_PAGE_SIZE = 30;
// WS 实时性本轮不接（后端 websockets/service 层并行改造中）：
// 使用 REST 轮询 + 手动刷新，不假装实时。轮询周期仅作兜底。
const CONVERSATIONS_POLL_MS = 30_000;
const MESSAGES_POLL_MS = 15_000;

const formatTime = (iso?: string) => {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const Communication: React.FC = () => {
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

  const activeIdRef = React.useRef<string | null>(null);
  activeIdRef.current = activeId;

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

  // 初始加载 + REST 轮询（WS 待后端改造完成后接入）
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

  // 当前会话消息轮询：只覆盖当前选中的会话
  React.useEffect(() => {
    if (!activeId) return;
    const timer = window.setInterval(async () => {
      try {
        const data = await chatApi.getMessages(activeId, MESSAGES_PAGE_SIZE);
        if (activeIdRef.current === activeId) {
          setMessages(data);
        }
      } catch {
        // 轮询失败静默等待下一轮
      }
    }, MESSAGES_POLL_MS);
    return () => window.clearInterval(timer);
  }, [activeId]);

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
    setSending(true);
    try {
      const saved = await chatApi.sendMessage(activeId, content);
      setMessages((prev) => [...prev, saved]);
      setNewMessage('');
      loadConversations(true);
    } catch (error: any) {
      setMessagesError(error?.response?.data?.detail || error?.message || '发送失败，请重试');
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
      // 患者端角色语义：participant_id 传对方（医生/健康管理师）的用户ID，
      // 后端按会话参与者身份校验读写权限，前端不做额外权限判断
      const { id } = await chatApi.createConversation(participantId);
      setCreateOpen(false);
      setParticipantInput('');
      await loadConversations(true);
      await openConversation(id);
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      setCreateError(
        detail === '指定的参与者不存在'
          ? '该用户ID不存在，请向您的医生/健康管理师确认账号ID'
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
          医生沟通
        </Typography>
        <Alert severity="warning">请先登录后再使用沟通功能。</Alert>
      </Box>
    );
  }

  const activeConversation = conversations.find((c) => c.id === activeId) || null;

  const renderConversationItem = (conv: ConversationDto) => {
    const other = conv.other_user;
    const isActive = conv.id === activeId;
    const roleLabel =
      other?.role === 'doctor' ? '医生' : other?.role === 'health_manager' ? '健康管理师' : other?.role || '';
    return (
      <React.Fragment key={conv.id}>
        <ListItem button onClick={() => openConversation(conv.id)} selected={isActive}>
          <ListItemAvatar>
            <Avatar>
              <LocalHospitalIcon />
            </Avatar>
          </ListItemAvatar>
          <ListItemText
            primary={
              <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography component="span" variant="body1" noWrap>
                  {other?.name || '未知用户'}
                </Typography>
                {roleLabel && <Chip component="span" size="small" label={roleLabel} variant="outlined" />}
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
          医生沟通
          {unreadTotal > 0 && (
            <Chip color="primary" size="small" label={`未读 ${unreadTotal}`} sx={{ ml: 1 }} />
          )}
        </Typography>
        <Box>
          <Button startIcon={<AddIcon />} onClick={() => setCreateOpen(true)} sx={{ mr: 1 }}>
            联系医生/健康管理师
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
                <Typography color="text.secondary">
                  暂无会话，点击「联系医生/健康管理师」发起沟通
                </Typography>
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
                <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="h6">
                    与 {activeConversation?.other_user?.name || '未知用户'} 的对话
                  </Typography>
                </Box>

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
                    </>
                  )}
                </Box>

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
        <DialogTitle>联系医生/健康管理师</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            输入医生或健康管理师的用户ID发起会话（对方 ID 请向本人/机构获取；系统暂无患者可用的联系人目录接口）。
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

export default Communication;
