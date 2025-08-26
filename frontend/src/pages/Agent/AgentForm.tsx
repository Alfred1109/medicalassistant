import React from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import {
  Box,
  Button,
  Container,
  Grid,
  Paper,
  TextField,
  Typography,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  CircularProgress,
  Snackbar,
  Alert,
  Tooltip,
} from '@mui/material';
import { 
  ArrowBack as ArrowBackIcon, 
  Save as SaveIcon,
  AutoFixHigh as AutoFixHighIcon
} from '@mui/icons-material';
import axios from 'axios';

// 导入store类型和action
import { RootState } from '../../store';
import { fetchAgentById, createAgent, updateAgent } from '../../store/slices/agentSlice';

// 使用环境变量获取API基础URL
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5502';

// 助手类型选项
const AGENT_TYPES = [
  { value: 'conversation', label: '对话助手' },
  { value: 'rehabilitation', label: '康复指导助手' },
  { value: 'assessment', label: '评估助手' },
  { value: 'education', label: '健康教育助手' },
];

// 模型选项
const MODEL_OPTIONS = [
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'deepseek-v3-241226', label: 'DeepSeek V3' },
  { value: 'claude-3', label: 'Claude 3' },
];

const AgentForm = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const { id } = useParams<{ id: string }>();
  
  const isEditMode = !!id;
  const agentState = useSelector((state: RootState) => state.agents);
  const { selectedAgent, loading, error } = agentState || { selectedAgent: null, loading: false, error: null };
  
  // 表单状态
  const [formData, setFormData] = React.useState({
    name: '',
    description: '',
    type: 'conversation',
    model: 'deepseek-v3-241226',
    system_prompt: '你是一个医疗康复助手，可以帮助患者回答康复相关的问题。',
    parameters: {},
  });
  
  // 参数配置字符串（JSON格式）
  const [parametersJson, setParametersJson] = React.useState('{}');
  const [jsonError, setJsonError] = React.useState('');
  
  // 添加状态用于控制AI生成参数的加载状态和错误消息
  const [generatingParameters, setGeneratingParameters] = React.useState(false);
  const [snackbarOpen, setSnackbarOpen] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState('');
  const [snackbarSeverity, setSnackbarSeverity] = React.useState<'success' | 'error'>('success');
  
  React.useEffect(() => {
    if (isEditMode && id && id !== 'undefined') {
      dispatch(fetchAgentById(id));
    } else if (isEditMode && (!id || id === 'undefined')) {
      navigate('/agents');
    }
  }, [dispatch, id, isEditMode, navigate]);
  
  React.useEffect(() => {
    if (isEditMode && selectedAgent) {
      setFormData({
        name: selectedAgent.name || '',
        description: selectedAgent.description || '',
        type: selectedAgent.type || 'conversation',
        model: selectedAgent.model || 'deepseek-v3-241226',
        system_prompt: selectedAgent.system_prompt || '你是一个医疗康复助手，可以帮助患者回答康复相关的问题。',
        parameters: selectedAgent.parameters || {},
      });
      
      // 格式化参数为JSON字符串
      setParametersJson(JSON.stringify(selectedAgent.parameters || {}, null, 2));
    }
  }, [isEditMode, selectedAgent]);
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | { name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name as string]: value,
    }));
  };
  
  const handleParametersChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setParametersJson(e.target.value);
    
    // 验证JSON格式
    try {
      JSON.parse(e.target.value);
      setJsonError('');
    } catch (err) {
      setJsonError('参数格式无效，请输入有效的JSON');
    }
  };
  
  // 处理AI生成参数
  const handleGenerateParameters = async () => {
    try {
      setGeneratingParameters(true);
      
      // 准备请求数据
      const requestData = {
        type: formData.type,
        model: formData.model,
        system_prompt: formData.system_prompt
      };
      
      // 调用API生成参数
      const response = await axios.post(
        `${BASE_URL}/api/agents/generate-parameters`, 
        requestData
      );
      
      // 更新参数JSON
      if (response.data && response.data.parameters) {
        const generatedParams = JSON.stringify(response.data.parameters, null, 2);
        setParametersJson(generatedParams);
        setJsonError('');
        
        // 显示成功消息
        setSnackbarMessage('参数配置已成功生成！');
        setSnackbarSeverity('success');
        setSnackbarOpen(true);
      } else {
        throw new Error('生成的参数无效');
      }
    } catch (error) {
      console.error('生成参数时出错:', error);
      setSnackbarMessage('生成参数失败，请重试');
      setSnackbarSeverity('error');
      setSnackbarOpen(true);
    } finally {
      setGeneratingParameters(false);
    }
  };
  
  // 处理Snackbar关闭
  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
  };
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (jsonError) {
      return; // 不提交表单如果JSON有错误
    }
    
    // 解析参数JSON
    let parameters = {};
    try {
      parameters = JSON.parse(parametersJson);
    } catch (err) {
      setJsonError('参数格式无效，请输入有效的JSON');
      return;
    }
    
    const agentData = {
      ...formData,
      parameters,
    };
    
    if (isEditMode && id) {
      dispatch(updateAgent({ id, agentData }))
        .then((result: any) => {
          if (!result.error) {
            navigate(`/agents/${id}`);
          }
        });
    } else {
      dispatch(createAgent(agentData))
        .then((result: any) => {
          if (!result.error) {
            navigate('/agents');
          }
        });
    }
  };

  // 渲染组件
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" alignItems="center" mb={4}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/agents')}
          sx={{ mr: 2 }}
        >
          返回
        </Button>
        <Typography variant="h4" component="h1">
          {isEditMode ? '编辑助手' : '创建助手'}
        </Typography>
      </Box>
      
      {loading && isEditMode && !selectedAgent ? (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      ) : (
        <Paper sx={{ p: 4 }}>
          {error && (
            <Typography color="error" sx={{ mb: 2 }}>
              {error}
            </Typography>
          )}
          
          <Snackbar 
            open={snackbarOpen} 
            autoHideDuration={6000} 
            onClose={handleSnackbarClose}
            anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
          >
            <Alert onClose={handleSnackbarClose} severity={snackbarSeverity}>
              {snackbarMessage}
            </Alert>
          </Snackbar>
          
          <Box component="form" onSubmit={handleSubmit} noValidate>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <TextField
                  required
                  fullWidth
                  id="name"
                  name="name"
                  label="助手名称"
                  value={formData.name}
                  onChange={handleChange}
                  disabled={loading}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  id="description"
                  name="description"
                  label="描述"
                  multiline
                  rows={3}
                  value={formData.description}
                  onChange={handleChange}
                  disabled={loading}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth disabled={loading}>
                  <InputLabel id="type-label">助手类型</InputLabel>
                  <Select
                    labelId="type-label"
                    id="type"
                    name="type"
                    value={formData.type}
                    label="助手类型"
                    onChange={handleChange}
                  >
                    {AGENT_TYPES.map((type) => (
                      <MenuItem key={type.value} value={type.value}>
                        {type.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth disabled={loading} required>
                  <InputLabel id="model-label">模型</InputLabel>
                  <Select
                    labelId="model-label"
                    id="model"
                    name="model"
                    value={formData.model}
                    label="模型"
                    onChange={handleChange}
                  >
                    {MODEL_OPTIONS.map((model) => (
                      <MenuItem key={model.value} value={model.value}>
                        {model.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  required
                  fullWidth
                  id="system_prompt"
                  name="system_prompt"
                  label="系统提示词"
                  multiline
                  rows={3}
                  value={formData.system_prompt}
                  onChange={handleChange}
                  disabled={loading}
                  helperText="定义助手的行为、角色和能力范围"
                />
              </Grid>
              
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
                  <TextField
                    fullWidth
                    id="parameters"
                    name="parameters"
                    label="参数配置（JSON格式）"
                    multiline
                    rows={8}
                    value={parametersJson}
                    onChange={handleParametersChange}
                    error={!!jsonError}
                    helperText={jsonError || "配置AI助手的参数，使用JSON格式"}
                    disabled={loading || generatingParameters}
                    sx={{ fontFamily: 'monospace' }}
                  />
                  <Tooltip title="使用AI自动生成最佳参数配置">
                    <Button
                      variant="contained"
                      color="secondary"
                      onClick={handleGenerateParameters}
                      disabled={loading || generatingParameters}
                      startIcon={generatingParameters ? <CircularProgress size={20} /> : <AutoFixHighIcon />}
                      sx={{ ml: 1, minWidth: '120px', height: '56px' }}
                    >
                      {generatingParameters ? '生成中...' : 'AI生成参数'}
                    </Button>
                  </Tooltip>
                </Box>
              </Grid>
              
              <Grid item xs={12} sx={{ mt: 2 }}>
                <Box display="flex" justifyContent="flex-end">
                  <Button
                    variant="contained"
                    color="primary"
                    type="submit"
                    disabled={loading || !!jsonError}
                    startIcon={<SaveIcon />}
                  >
                    {loading ? (
                      <>
                        <CircularProgress size={24} sx={{ mr: 1 }} />
                        保存中...
                      </>
                    ) : (
                      isEditMode ? '保存修改' : '创建助手'
                    )}
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Paper>
      )}
    </Container>
  );
};

export default AgentForm; 