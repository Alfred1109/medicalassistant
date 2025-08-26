import api from './api';

// API基础URL
const API_URL = import.meta.env.VITE_API_URL || '/api';

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
  // 获取用户的所有对话
  async getConversations() {
    try {
      const response = await api.get('/chat/conversations');
      return response.data;
    } catch (error) {
      console.error('获取对话列表失败:', error);
      throw error;
    }
  },

  // 获取特定对话的消息
  async getMessages(conversationId: string, limit = 30, before?: string) {
    try {
      let url = `/chat/conversations/${conversationId}/messages`;
      const params: Record<string, any> = { limit };
      if (before) {
        params.before = before;
      }
      const response = await api.get(url, { params });
      return response.data;
    } catch (error) {
      console.error('获取消息失败:', error);
      throw error;
    }
  },

  // 发送消息
  async sendMessage(conversationId: string, content: string, attachments: File[] = []) {
    try {
      // 如果有附件，使用FormData
      if (attachments.length > 0) {
        const formData = new FormData();
        formData.append('content', content);
        formData.append('conversationId', conversationId);
        
        attachments.forEach((file, index) => {
          formData.append(`attachment_${index}`, file);
        });
        
        const response = await api.post('/chat/messages', formData, {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        });
        return response.data;
      } else {
        // 无附件的简单消息
        const response = await api.post('/chat/messages', {
          content,
          conversationId
        });
        return response.data;
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      throw error;
    }
  },

  // 创建新对话
  async createConversation(participantIds: string[]) {
    try {
      const response = await api.post('/chat/conversations', {
        participantIds
      });
      return response.data;
    } catch (error) {
      console.error('创建对话失败:', error);
      throw error;
    }
  },

  // 标记消息为已读
  async markAsRead(messageIds: string[]) {
    try {
      const response = await api.post('/chat/messages/read', {
        messageIds
      });
      return response.data;
    } catch (error) {
      console.error('标记消息已读失败:', error);
      throw error;
    }
  },

  // 删除消息
  async deleteMessage(messageId: string) {
    try {
      const response = await api.delete(`/chat/messages/${messageId}`);
      return response.data;
    } catch (error) {
      console.error('删除消息失败:', error);
      throw error;
    }
  },

  // 获取离线消息
  async getOfflineMessages() {
    try {
      const response = await api.get('/chat/messages/offline');
      return response.data;
    } catch (error) {
      console.error('获取离线消息失败:', error);
      throw error;
    }
  },

  // 获取未读消息数量
  async getUnreadCount() {
    try {
      const response = await api.get('/chat/messages/unread/count');
      return response.data;
    } catch (error) {
      console.error('获取未读消息数量失败:', error);
      throw error;
    }
  },

  // 搜索消息
  async searchMessages(query: string, conversationId?: string) {
    try {
      const params: Record<string, any> = { query };
      if (conversationId) {
        params.conversationId = conversationId;
      }
      const response = await api.get('/chat/messages/search', { params });
      return response.data;
    } catch (error) {
      console.error('搜索消息失败:', error);
      throw error;
    }
  }
}; 