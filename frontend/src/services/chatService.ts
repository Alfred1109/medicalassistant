import api from './api';

// 后端通信路由挂载于 /api/communications（见 backend/app/api/routers/communication_router.py），
// 本服务历史上指向不存在的 /chat/* 前缀，已全部修正为后端实际注册的路径。

// 消息类型
export interface ChatMessage {
  id: string;
  content: string;
  sender: 'patient' | 'doctor' | 'system';
  timestamp: Date | string;
  status: 'sent' | 'delivered' | 'read' | 'error';
  conversationId?: string;
  attachments?: Array<{
    id: string;
    type: 'image' | 'file';
    url: string;
    name: string;
  }>;
}

// 对话类型
export interface Conversation {
  id: string;
  participants: Array<{
    id: string;
    name: string;
    role: 'patient' | 'doctor' | 'healthManager';
  }>;
  lastMessage?: {
    content: string;
    timestamp: Date | string;
    sender: string;
  };
  unreadCount: number;
  createdAt: Date | string;
  updatedAt: Date | string;
}

// 创建聊天API服务
export const chatApi = {
  // 获取用户的所有对话（后端 GET /communications/conversations）
  async getConversations(params?: { limit?: number; skip?: number; status?: string }) {
    try {
      const response = await api.get('/communications/conversations', { params });
      return response.data;
    } catch (error) {
      console.error('获取对话列表失败:', error);
      throw error;
    }
  },

  // 获取特定对话的消息（后端 GET /communications/conversations/{id}/messages，
  // 分页参数为 limit / before_id）
  async getMessages(conversationId: string, limit = 30, before?: string) {
    try {
      const params: Record<string, any> = { limit };
      if (before) {
        params.before_id = before;
      }
      const response = await api.get(
        `/communications/conversations/${conversationId}/messages`,
        { params }
      );
      return response.data;
    } catch (error) {
      console.error('获取消息失败:', error);
      throw error;
    }
  },

  // 发送消息（后端 POST /communications/conversations/{id}/messages，
  // body 为 MessageCreate: { content, type?, attachments?, metadata? }，JSON 而非 FormData）
  async sendMessage(conversationId: string, content: string, attachments?: Array<Record<string, any>>) {
    try {
      const response = await api.post(
        `/communications/conversations/${conversationId}/messages`,
        {
          content,
          ...(attachments && attachments.length > 0 ? { attachments } : {}),
        }
      );
      return response.data;
    } catch (error) {
      console.error('发送消息失败:', error);
      throw error;
    }
  },

  // 创建新对话（后端 POST /communications/conversations，body 为
  // ConversationCreate: { participant_id, type? }，单个参与者）
  async createConversation(participantId: string, type = 'chat') {
    try {
      const response = await api.post('/communications/conversations', {
        participant_id: participantId,
        type,
      });
      return response.data;
    } catch (error) {
      console.error('创建对话失败:', error);
      throw error;
    }
  },

  // 标记单条消息为已读（后端 PUT /communications/messages/{message_id}/read；
  // 后端无批量已读端点，整段对话请配合 markConversationAsRead）
  async markAsRead(messageId: string) {
    try {
      const response = await api.put(`/communications/messages/${messageId}/read`);
      return response.data;
    } catch (error) {
      console.error('标记消息已读失败:', error);
      throw error;
    }
  },

  // 标记对话所有消息为已读（后端 PUT /communications/conversations/{conversation_id}/read）
  async markConversationAsRead(conversationId: string) {
    try {
      const response = await api.put(`/communications/conversations/${conversationId}/read`);
      return response.data;
    } catch (error) {
      console.error('标记对话已读失败:', error);
      throw error;
    }
  },

  // 删除消息（后端 DELETE /communications/messages/{message_id}，软删除）
  async deleteMessage(messageId: string) {
    try {
      const response = await api.delete(`/communications/messages/${messageId}`);
      return response.data;
    } catch (error) {
      console.error('删除消息失败:', error);
      throw error;
    }
  },

  // 获取未读消息数量（后端 GET /communications/unread-count）
  async getUnreadCount() {
    try {
      const response = await api.get('/communications/unread-count');
      return response.data;
    } catch (error) {
      console.error('获取未读消息数量失败:', error);
      throw error;
    }
  },

  // 获取特定对话详情（后端 GET /communications/conversations/{conversation_id}）
  async getConversation(conversationId: string) {
    try {
      const response = await api.get(`/communications/conversations/${conversationId}`);
      return response.data;
    } catch (error) {
      console.error('获取对话详情失败:', error);
      throw error;
    }
  },

  // 同步离线消息（后端 POST /communications/sync，body 为 { last_sync_time }）
  async syncOfflineMessages(lastSyncTime: string) {
    try {
      const response = await api.post('/communications/sync', {
        last_sync_time: lastSyncTime,
      });
      return response.data;
    } catch (error) {
      console.error('同步离线消息失败:', error);
      throw error;
    }
  }

  // 注意：后端 /api/communications 无消息搜索端点，原 searchMessages 死链已删除
  //（后端能力待建设）。
};
