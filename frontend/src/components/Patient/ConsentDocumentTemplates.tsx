import React, { useState } from 'react';
import {
  Box, Paper, Typography, List, ListItem, ListItemIcon, 
  ListItemText, Button, TextField, Dialog, DialogActions, 
  DialogContent, DialogTitle, FormControl, InputLabel, 
  Select, MenuItem, FormHelperText, Grid, Card, CardContent,
  CardActions, Divider, Chip, IconButton, Tooltip
} from '@mui/material';
import ArticleIcon from '@mui/icons-material/Article';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import PreviewIcon from '@mui/icons-material/Preview';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import SearchIcon from '@mui/icons-material/Search';
import FilterListIcon from '@mui/icons-material/FilterList';

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
}

// 组件属性类型
interface ConsentDocumentTemplatesProps {
  templates: DocumentTemplate[];
  onSelectTemplate?: (templateId: string) => void;
  onCreateTemplate?: (template: Omit<DocumentTemplate, 'id' | 'createdAt' | 'updatedAt' | 'usageCount'>) => Promise<void>;
  onUpdateTemplate?: (id: string, template: Partial<DocumentTemplate>) => Promise<void>;
  onDeleteTemplate?: (id: string) => Promise<void>;
  onPreviewTemplate?: (id: string) => void;
  onGenerateDocument?: (templateId: string, variables: Record<string, string>) => Promise<void>;
}

const ConsentDocumentTemplates: React.FC<ConsentDocumentTemplatesProps> = ({
  templates,
  onSelectTemplate,
  onCreateTemplate,
  onUpdateTemplate,
  onDeleteTemplate,
  onPreviewTemplate,
  onGenerateDocument
}) => {
  // 状态定义
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [currentTemplate, setCurrentTemplate] = useState<DocumentTemplate | null>(null);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    category: '',
    content: '',
    tags: [] as string[],
    variables: [] as string[]
  });
  const [variableDialogOpen, setVariableDialogOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<DocumentTemplate | null>(null);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  
  // 获取唯一类别列表
  const categories = Array.from(new Set(templates.map(t => t.category)));
  
  // 处理搜索查询变更
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  };
  
  // 处理类别过滤变更
  const handleCategoryChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setCategoryFilter(event.target.value as string);
  };
  
  // 过滤模板
  const filteredTemplates = templates.filter(template => {
    // 类别过滤
    if (categoryFilter !== 'all' && template.category !== categoryFilter) {
      return false;
    }
    
    // 搜索过滤
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      return (
        template.title.toLowerCase().includes(query) ||
        template.description.toLowerCase().includes(query) ||
        template.tags.some(tag => tag.toLowerCase().includes(query))
      );
    }
    
    return true;
  });
  
  // 处理编辑对话框打开
  const handleEditDialogOpen = (template?: DocumentTemplate) => {
    if (template) {
      setCurrentTemplate(template);
      setFormData({
        title: template.title,
        description: template.description,
        category: template.category,
        content: template.content,
        tags: [...template.tags],
        variables: [...template.variables]
      });
    } else {
      setCurrentTemplate(null);
      setFormData({
        title: '',
        description: '',
        category: '',
        content: '',
        tags: [],
        variables: []
      });
    }
    setFormErrors({});
    setEditDialogOpen(true);
  };
  
  // 处理编辑对话框关闭
  const handleEditDialogClose = () => {
    setEditDialogOpen(false);
  };
  
  // 处理表单输入变更
  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target;
    setFormData({
      ...formData,
      [name]: value
    });
    
    // 清除相应字段的错误
    if (formErrors[name]) {
      setFormErrors({
        ...formErrors,
        [name]: ''
      });
    }
  };
  
  // 处理下拉选择变更
  const handleSelectChange = (event: React.ChangeEvent<{ name?: string; value: unknown }>) => {
    const name = event.target.name as string;
    const value = event.target.value as string;
    
    setFormData({
      ...formData,
      [name]: value
    });
    
    // 清除相应字段的错误
    if (formErrors[name]) {
      setFormErrors({
        ...formErrors,
        [name]: ''
      });
    }
  };
  
  // 处理标签输入
  const handleTagInput = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && (event.target as HTMLInputElement).value) {
      event.preventDefault();
      const newTag = (event.target as HTMLInputElement).value.trim();
      
      if (newTag && !formData.tags.includes(newTag)) {
        setFormData({
          ...formData,
          tags: [...formData.tags, newTag]
        });
        (event.target as HTMLInputElement).value = '';
      }
    }
  };
  
  // 删除标签
  const handleDeleteTag = (tagToDelete: string) => {
    setFormData({
      ...formData,
      tags: formData.tags.filter(tag => tag !== tagToDelete)
    });
  };
  
  // 处理变量输入
  const handleVariableInput = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter' && (event.target as HTMLInputElement).value) {
      event.preventDefault();
      const newVariable = (event.target as HTMLInputElement).value.trim();
      
      if (newVariable && !formData.variables.includes(newVariable)) {
        setFormData({
          ...formData,
          variables: [...formData.variables, newVariable]
        });
        (event.target as HTMLInputElement).value = '';
      }
    }
  };
  
  // 删除变量
  const handleDeleteVariable = (variableToDelete: string) => {
    setFormData({
      ...formData,
      variables: formData.variables.filter(variable => variable !== variableToDelete)
    });
  };
  
  // 验证表单
  const validateForm = () => {
    const errors: Record<string, string> = {};
    
    if (!formData.title) {
      errors.title = '请输入模板标题';
    }
    
    if (!formData.category) {
      errors.category = '请选择模板类别';
    }
    
    if (!formData.content) {
      errors.content = '请输入模板内容';
    }
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };
  
  // 处理表单提交
  const handleSubmit = async () => {
    if (!validateForm()) {
      return;
    }
    
    try {
      if (currentTemplate) {
        // 更新现有模板
        await onUpdateTemplate?.(currentTemplate.id, formData);
      } else {
        // 创建新模板
        await onCreateTemplate?.(formData);
      }
      
      handleEditDialogClose();
    } catch (error) {
      console.error('保存模板失败:', error);
    }
  };
  
  // 处理删除模板
  const handleDeleteTemplate = async (id: string) => {
    if (window.confirm('确定要删除此模板吗？此操作无法撤销。')) {
      try {
        await onDeleteTemplate?.(id);
      } catch (error) {
        console.error('删除模板失败:', error);
      }
    }
  };
  
  // 处理预览模板
  const handlePreviewTemplate = (id: string) => {
    onPreviewTemplate?.(id);
  };
  
  // 打开变量填写对话框
  const handleOpenVariableDialog = (template: DocumentTemplate) => {
    setSelectedTemplate(template);
    
    // 初始化变量值为空字符串
    const initialValues: Record<string, string> = {};
    template.variables.forEach(variable => {
      initialValues[variable] = '';
    });
    
    setVariableValues(initialValues);
    setVariableDialogOpen(true);
  };
  
  // 关闭变量填写对话框
  const handleCloseVariableDialog = () => {
    setVariableDialogOpen(false);
    setSelectedTemplate(null);
  };
  
  // 处理变量值变更
  const handleVariableValueChange = (variable: string, value: string) => {
    setVariableValues({
      ...variableValues,
      [variable]: value
    });
  };
  
  // 生成文档
  const handleGenerateDocument = async () => {
    if (!selectedTemplate) return;
    
    // 验证所有必需的变量都已填写
    const emptyVariables = selectedTemplate.variables.filter(v => !variableValues[v]);
    if (emptyVariables.length > 0) {
      alert(`请填写以下变量: ${emptyVariables.join(', ')}`);
      return;
    }
    
    try {
      await onGenerateDocument?.(selectedTemplate.id, variableValues);
      handleCloseVariableDialog();
    } catch (error) {
      console.error('生成文档失败:', error);
    }
  };
  
  // 获取模板卡片样式
  const getCardStyle = (category: string) => {
    const styles: Record<string, any> = {
      '手术': { borderLeft: '4px solid #f44336' },
      '检查': { borderLeft: '4px solid #2196f3' },
      '治疗': { borderLeft: '4px solid #4caf50' },
      '用药': { borderLeft: '4px solid #ff9800' },
      '研究': { borderLeft: '4px solid #9c27b0' }
    };
    
    return styles[category] || { borderLeft: '4px solid #757575' };
  };
  
  return (
    <Box>
      {/* 搜索和过滤工具栏 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <TextField
              fullWidth
              variant="outlined"
              placeholder="搜索模板..."
              value={searchQuery}
              onChange={handleSearchChange}
              InputProps={{
                startAdornment: <SearchIcon sx={{ color: 'action.active', mr: 1 }} />
              }}
              size="small"
            />
          </Grid>
          <Grid item xs={8} md={4}>
            <FormControl variant="outlined" fullWidth size="small">
              <InputLabel id="category-filter-label">类别</InputLabel>
              <Select
                labelId="category-filter-label"
                value={categoryFilter}
                onChange={handleCategoryChange}
                label="类别"
                startAdornment={<FilterListIcon sx={{ color: 'action.active', mr: 1 }} />}
              >
                <MenuItem value="all">所有类别</MenuItem>
                {categories.map(category => (
                  <MenuItem key={category} value={category}>{category}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4} md={2}>
            <Button
              variant="contained"
              color="primary"
              startIcon={<AddCircleOutlineIcon />}
              onClick={() => handleEditDialogOpen()}
              fullWidth
            >
              新建模板
            </Button>
          </Grid>
        </Grid>
      </Paper>
      
      {/* 模板列表 */}
      {filteredTemplates.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="textSecondary" gutterBottom>
            没有找到匹配的模板
          </Typography>
          <Button
            variant="outlined"
            startIcon={<AddCircleOutlineIcon />}
            onClick={() => handleEditDialogOpen()}
            sx={{ mt: 2 }}
          >
            创建新模板
          </Button>
        </Paper>
      ) : (
        <Grid container spacing={3}>
          {filteredTemplates.map(template => (
            <Grid item xs={12} sm={6} md={4} key={template.id}>
              <Card 
                variant="outlined" 
                sx={{ 
                  ...getCardStyle(template.category),
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'transform 0.2s',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: 2
                  }
                }}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  <Box display="flex" alignItems="center" mb={1}>
                    <ArticleIcon sx={{ color: 'primary.main', mr: 1 }} />
                    <Typography variant="h6" component="div">
                      {template.title}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                    {template.description}
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                  <Box display="flex" alignItems="center" mb={1}>
                    <MedicalServicesIcon fontSize="small" sx={{ color: 'text.secondary', mr: 1 }} />
                    <Typography variant="body2" color="textSecondary">
                      类别: {template.category}
                    </Typography>
                  </Box>
                  <Box display="flex" flexWrap="wrap" gap={0.5} mb={1}>
                    {template.tags.map(tag => (
                      <Chip key={tag} label={tag} size="small" variant="outlined" />
                    ))}
                  </Box>
                  <Typography variant="caption" color="textSecondary">
                    变量: {template.variables.length > 0 ? template.variables.join(', ') : '无'}
                  </Typography>
                </CardContent>
                <Divider />
                <CardActions>
                  <Tooltip title="编辑模板">
                    <IconButton 
                      size="small" 
                      onClick={() => handleEditDialogOpen(template)}
                    >
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="预览模板">
                    <IconButton 
                      size="small"
                      onClick={() => handlePreviewTemplate(template.id)}
                    >
                      <PreviewIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="使用模板">
                    <IconButton 
                      size="small" 
                      color="primary"
                      onClick={() => {
                        if (template.variables.length > 0) {
                          handleOpenVariableDialog(template);
                        } else {
                          onSelectTemplate?.(template.id);
                        }
                      }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Box flexGrow={1} />
                  <Tooltip title="删除模板">
                    <IconButton 
                      size="small" 
                      color="error"
                      onClick={() => handleDeleteTemplate(template.id)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
      
      {/* 编辑/创建模板对话框 */}
      <Dialog 
        open={editDialogOpen} 
        onClose={handleEditDialogClose}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {currentTemplate ? '编辑知情同意书模板' : '创建新的知情同意书模板'}
        </DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={8}>
              <TextField
                name="title"
                label="模板标题"
                fullWidth
                margin="normal"
                value={formData.title}
                onChange={handleInputChange}
                error={!!formErrors.title}
                helperText={formErrors.title}
                required
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth margin="normal" error={!!formErrors.category} required>
                <InputLabel id="category-label">类别</InputLabel>
                <Select
                  labelId="category-label"
                  name="category"
                  value={formData.category}
                  onChange={handleSelectChange}
                  label="类别"
                >
                  <MenuItem value="">选择类别</MenuItem>
                  <MenuItem value="手术">手术</MenuItem>
                  <MenuItem value="检查">检查</MenuItem>
                  <MenuItem value="治疗">治疗</MenuItem>
                  <MenuItem value="用药">用药</MenuItem>
                  <MenuItem value="研究">研究</MenuItem>
                  <MenuItem value="其他">其他</MenuItem>
                </Select>
                {formErrors.category && <FormHelperText>{formErrors.category}</FormHelperText>}
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                name="description"
                label="模板描述"
                fullWidth
                margin="normal"
                value={formData.description}
                onChange={handleInputChange}
                multiline
                rows={2}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                name="content"
                label="模板内容"
                fullWidth
                margin="normal"
                value={formData.content}
                onChange={handleInputChange}
                multiline
                rows={10}
                error={!!formErrors.content}
                helperText={formErrors.content || '使用 {{变量名}} 格式插入变量，例如：患者姓名：{{patientName}}'}
                required
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="subtitle2" gutterBottom>
                标签
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={0.5} mb={1}>
                {formData.tags.map(tag => (
                  <Chip
                    key={tag}
                    label={tag}
                    size="small"
                    onDelete={() => handleDeleteTag(tag)}
                  />
                ))}
              </Box>
              <TextField
                fullWidth
                size="small"
                placeholder="输入标签并按Enter添加"
                onKeyPress={handleTagInput}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="subtitle2" gutterBottom>
                变量
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={0.5} mb={1}>
                {formData.variables.map(variable => (
                  <Chip
                    key={variable}
                    label={variable}
                    size="small"
                    onDelete={() => handleDeleteVariable(variable)}
                  />
                ))}
              </Box>
              <TextField
                fullWidth
                size="small"
                placeholder="输入变量名并按Enter添加"
                onKeyPress={handleVariableInput}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleEditDialogClose}>取消</Button>
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleSubmit}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 变量填写对话框 */}
      <Dialog
        open={variableDialogOpen}
        onClose={handleCloseVariableDialog}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          填写文档变量
        </DialogTitle>
        <DialogContent dividers>
          {selectedTemplate && (
            <>
              <Typography variant="subtitle1" gutterBottom>
                {selectedTemplate.title}
              </Typography>
              <Typography variant="body2" color="textSecondary" paragraph>
                请填写以下变量以生成知情同意书
              </Typography>
              <Grid container spacing={2}>
                {selectedTemplate.variables.map(variable => (
                  <Grid item xs={12} key={variable}>
                    <TextField
                      fullWidth
                      label={variable}
                      value={variableValues[variable] || ''}
                      onChange={(e) => handleVariableValueChange(variable, e.target.value)}
                      margin="normal"
                    />
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseVariableDialog}>取消</Button>
          <Button
            variant="contained"
            color="primary"
            onClick={handleGenerateDocument}
          >
            生成文档
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ConsentDocumentTemplates; 