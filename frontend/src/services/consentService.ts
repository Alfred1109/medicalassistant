import axios from 'axios';
import { API_BASE_URL } from '../config/constants';

// API基础URL
const API_URL = `${API_BASE_URL}/consent`;

// 知情同意文档类型
export interface ConsentDocument {
  id: string;
  title: string;
  description: string;
  content: string;
  category: string;
  provider: string;
  createdAt: string;
  expiresAt?: string;
  status: 'pending' | 'signed' | 'expired';
  signedAt?: string;
  urgent: boolean;
  requirePatientSignature: boolean;
  requireGuardianSignature: boolean;
  requireWitnessSignature: boolean;
  patientName: string;
  patientId: string;
  specialClauses?: string;
  attachments?: Array<{
    id: string;
    name: string;
    url: string;
  }>;
}

// 文档模板类型
export interface DocumentTemplate {
  id: string;
  title: string;
  description: string;
  category: string;
  content: string;
  variables: string[];
  createdAt: Date;
  updatedAt: Date;
  usageCount: number;
  tags: string[];
  specialClauses?: string;
}

// 签名提交类型
export interface SignatureSubmission {
  documentId: string;
  patientId: string;
  patientSignature: string;
  patientAcknowledgements: string[];
  guardianSignature?: string;
  guardianName?: string;
  witnessSignature?: string;
  witnessName?: string;
  signedAt: string;
}

// 获取知情同意文档列表
export const getConsentDocuments = async (): Promise<ConsentDocument[]> => {
  try {
    const response = await axios.get(`${API_URL}/documents`);
    return response.data;
  } catch (error) {
    console.error('获取知情同意文档列表失败:', error);
    throw error;
  }
};

// 获取单个知情同意文档
export const getConsentDocument = async (documentId: string): Promise<ConsentDocument> => {
  try {
    const response = await axios.get(`${API_URL}/documents/${documentId}`);
    return response.data;
  } catch (error) {
    console.error(`获取知情同意文档 ${documentId} 失败:`, error);
    throw error;
  }
};

// 提交签名记录
export const submitConsentSignature = async (data: SignatureSubmission): Promise<any> => {
  try {
    const response = await axios.post(`${API_URL}/signatures`, data);
    return response.data;
  } catch (error) {
    console.error('提交签名记录失败:', error);
    throw error;
  }
};

// 下载知情同意文档PDF
export const downloadConsentPdf = async (documentId: string): Promise<Blob> => {
  try {
    const response = await axios.get(`${API_URL}/documents/${documentId}/pdf`, {
      responseType: 'blob'
    });
    
    // 创建文件下载
    const blob = new Blob([response.data], { type: 'application/pdf' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `consent-document-${documentId}.pdf`;
    link.click();
    
    // 释放URL对象
    setTimeout(() => window.URL.revokeObjectURL(url), 100);
    
    return blob;
  } catch (error) {
    console.error(`下载知情同意文档 ${documentId} PDF失败:`, error);
    throw error;
  }
};

// 获取知情同意文档模板列表
export const getConsentTemplates = async (): Promise<DocumentTemplate[]> => {
  try {
    const response = await axios.get(`${API_URL}/templates`);
    return response.data;
  } catch (error) {
    console.error('获取知情同意文档模板列表失败:', error);
    throw error;
  }
};

// 获取单个知情同意文档模板
export const getConsentTemplate = async (templateId: string): Promise<DocumentTemplate> => {
  try {
    const response = await axios.get(`${API_URL}/templates/${templateId}`);
    return response.data;
  } catch (error) {
    console.error(`获取知情同意文档模板 ${templateId} 失败:`, error);
    throw error;
  }
};

// 创建知情同意文档模板
export const createConsentTemplate = async (template: Omit<DocumentTemplate, 'id' | 'createdAt' | 'updatedAt' | 'usageCount'>): Promise<DocumentTemplate> => {
  try {
    const response = await axios.post(`${API_URL}/templates`, template);
    return response.data;
  } catch (error) {
    console.error('创建知情同意文档模板失败:', error);
    throw error;
  }
};

// 更新知情同意文档模板
export const updateConsentTemplate = async (templateId: string, template: Partial<DocumentTemplate>): Promise<DocumentTemplate> => {
  try {
    const response = await axios.put(`${API_URL}/templates/${templateId}`, template);
    return response.data;
  } catch (error) {
    console.error(`更新知情同意文档模板 ${templateId} 失败:`, error);
    throw error;
  }
};

// 删除知情同意文档模板
export const deleteConsentTemplate = async (templateId: string): Promise<void> => {
  try {
    await axios.delete(`${API_URL}/templates/${templateId}`);
  } catch (error) {
    console.error(`删除知情同意文档模板 ${templateId} 失败:`, error);
    throw error;
  }
};

// 生成知情同意文档
export const generateConsentDocument = async (templateId: string, variables: Record<string, string>): Promise<ConsentDocument> => {
  try {
    const response = await axios.post(`${API_URL}/documents/generate`, {
      templateId,
      variables
    });
    return response.data;
  } catch (error) {
    console.error('生成知情同意文档失败:', error);
    throw error;
  }
};

// 获取患者签名历史
export const getPatientSignatureHistory = async (patientId: string): Promise<any[]> => {
  try {
    const response = await axios.get(`${API_URL}/signatures/patient/${patientId}`);
    return response.data;
  } catch (error) {
    console.error(`获取患者 ${patientId} 签名历史失败:`, error);
    throw error;
  }
};

// 获取文档签名状态
export const getDocumentSignatureStatus = async (documentId: string): Promise<any> => {
  try {
    const response = await axios.get(`${API_URL}/signatures/document/${documentId}`);
    return response.data;
  } catch (error) {
    console.error(`获取文档 ${documentId} 签名状态失败:`, error);
    throw error;
  }
}; 