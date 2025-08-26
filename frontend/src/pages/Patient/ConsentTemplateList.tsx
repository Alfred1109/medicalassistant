import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Paper,
  Divider,
  CircularProgress,
  Alert,
  IconButton
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';

// 导入组件
import ConsentDocumentTemplates from '../../components/Patient/ConsentDocumentTemplates';
// 导入API服务
import * as consentApi from '../../services/consentService';

// 文档模板类型
interface DocumentTemplate {
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

const ConsentTemplateList: React.FC = () => {
  const navigate = useNavigate();
  
  // 状态定义
  const [templates, setTemplates] = useState<DocumentTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<DocumentTemplate | null>(null);
  
  // 页面加载时获取模板列表
  useEffect(() => {
    const loadTemplates = async () => {
      try {
        setLoading(true);
        // 调用API获取知情同意文档模板列表
        const response = await consentApi.getConsentTemplates();
        
        // 转换日期字符串为Date对象
        const formattedTemplates = response.map((template: any) => ({
          ...template,
          createdAt: new Date(template.createdAt),
          updatedAt: new Date(template.updatedAt)
        }));
        
        setTemplates(formattedTemplates);
      } catch (err) {
        console.error('获取知情同意文档模板列表失败:', err);
        setError('获取模板列表失败，请稍后重试');
      } finally {
        setLoading(false);
      }
    };
    
    loadTemplates();
  }, []);
  
  // 处理模板选择
  const handleSelectTemplate = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (!template) return;
    
    setSelectedTemplate(template);
    
    // 如果模板没有变量，直接生成文档
    if (template.variables.length === 0) {
      handleGenerateDocument(templateId, {});
    } else {
      // 显示变量输入对话框 - 通过ConsentDocumentTemplates组件内部的对话框处理
    }
  };
  
  // 处理预览模板
  const handlePreviewTemplate = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    if (template) {
      setSelectedTemplate(template);
      setPreviewOpen(true);
    }
  };
  
  // 处理关闭预览
  const handleClosePreview = () => {
    setPreviewOpen(false);
  };
  
  // 处理创建模板
  const handleCreateTemplate = async (template: Omit<DocumentTemplate, 'id' | 'createdAt' | 'updatedAt' | 'usageCount'>) => {
    try {
      const newTemplate = await consentApi.createConsentTemplate(template);
      
      // 添加到模板列表
      setTemplates(prev => [
        {
          ...newTemplate,
          createdAt: new Date(newTemplate.createdAt),
          updatedAt: new Date(newTemplate.updatedAt)
        },
        ...prev
      ]);
      
      return Promise.resolve();
    } catch (err) {
      console.error('创建知情同意文档模板失败:', err);
      return Promise.reject(err);
    }
  };
  
  // 处理更新模板
  const handleUpdateTemplate = async (id: string, template: Partial<DocumentTemplate>) => {
    try {
      const updatedTemplate = await consentApi.updateConsentTemplate(id, template);
      
      // 更新模板列表
      setTemplates(prev => 
        prev.map(t => 
          t.id === id 
            ? {
                ...updatedTemplate,
                createdAt: new Date(updatedTemplate.createdAt),
                updatedAt: new Date(updatedTemplate.updatedAt)
              }
            : t
        )
      );
      
      return Promise.resolve();
    } catch (err) {
      console.error(`更新知情同意文档模板 ${id} 失败:`, err);
      return Promise.reject(err);
    }
  };
  
  // 处理删除模板
  const handleDeleteTemplate = async (id: string) => {
    try {
      await consentApi.deleteConsentTemplate(id);
      
      // 从模板列表中移除
      setTemplates(prev => prev.filter(t => t.id !== id));
      
      return Promise.resolve();
    } catch (err) {
      console.error(`删除知情同意文档模板 ${id} 失败:`, err);
      return Promise.reject(err);
    }
  };
  
  // 处理生成文档
  const handleGenerateDocument = async (templateId: string, variables: Record<string, string>) => {
    try {
      // 调用API生成文档
      const document = await consentApi.generateConsentDocument(templateId, variables);
      
      // 跳转到文档查看页面
      navigate(`/patient/documents/${document.id}`);
    } catch (err) {
      console.error('生成知情同意文档失败:', err);
      setError('生成文档失败，请稍后重试');
    }
  };
  
  // 渲染加载状态
  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress sx={{ mb: 2 }} />
        <Typography variant="h6">加载知情同意文档模板列表...</Typography>
      </Container>
    );
  }
  
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <IconButton 
            edge="start" 
            onClick={() => navigate('/patient/documents')} 
            sx={{ mr: 2 }}
            aria-label="返回"
          >
            <ArrowBackIcon />
          </IconButton>
          <LibraryBooksIcon color="primary" sx={{ mr: 2 }} />
          <Typography variant="h5" component="h1">
            知情同意文档模板
          </Typography>
        </Box>
        
        <Divider sx={{ mb: 3 }} />
        
        {error ? (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        ) : (
          <ConsentDocumentTemplates 
            templates={templates}
            onSelectTemplate={handleSelectTemplate}
            onCreateTemplate={handleCreateTemplate}
            onUpdateTemplate={handleUpdateTemplate}
            onDeleteTemplate={handleDeleteTemplate}
            onPreviewTemplate={handlePreviewTemplate}
            onGenerateDocument={handleGenerateDocument}
          />
        )}
      </Paper>
    </Container>
  );
};

export default ConsentTemplateList; 