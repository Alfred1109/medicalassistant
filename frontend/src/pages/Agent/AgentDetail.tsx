import React, { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import {
  Box,
  Button,
  Container,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  TextField,
  CircularProgress,
  Divider,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import { 
  ArrowBack as ArrowBackIcon, 
  Edit as EditIcon,
  Delete as DeleteIcon,
  Send as SendIcon 
} from '@mui/icons-material';

// 导入store类型
import { RootState } from '../../store';
import { fetchAgentById, deleteAgent, queryAgent } from '../../store/slices/agentSlice';

const AgentDetail = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  
  const { selectedAgent, loading, error, queryResponse } = useSelector((state: RootState) => state.agents);
  
  // 查询输入状态
  const [query, setQuery] = React.useState('');
  
  useEffect(() => {
    if (id && id !== 'undefined') {
      // 获取助手详情
      dispatch(fetchAgentById(id));
    } else {
      // 如果ID无效，重定向到助手列表页面
      navigate('/app/agents');
    }
  }, [dispatch, id, navigate]);
  
  const handleDelete = () => {
    if (id && window.confirm('确定要删除这个助手吗？')) {
      dispatch(deleteAgent(id))
        .then(() => {
          navigate('/app/agents');
        });
    }
  };
  
  const handleSubmitQuery = (e: React.FormEvent) => {
    e.preventDefault();
    if (id && query.trim()) {
      dispatch(queryAgent({ id, query }));
      setQuery('');
    }
  };
  
  if (loading && !selectedAgent) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="50vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }
  
  if (error && !selectedAgent) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography color="error">{error}</Typography>
          <Button 
            variant="contained" 
            onClick={() => navigate('/app/agents')} 
            sx={{ mt: 2 }}
          >
            返回助手列表
          </Button>
        </Paper>
      </Container>
    );
  }
  
  if (!selectedAgent) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography>未找到助手信息</Typography>
          <Button 
            variant="contained" 
            onClick={() => navigate('/app/agents')} 
            sx={{ mt: 2 }}
          >
            返回助手列表
          </Button>
        </Paper>
      </Container>
    );
  }
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" alignItems="center" mb={4}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/app/agents')}
          sx={{ mr: 2 }}
        >
          返回
        </Button>
        <Typography variant="h4" component="h1" sx={{ flexGrow: 1 }}>
          {selectedAgent.name}
        </Typography>
        <Button
          variant="outlined"
          color="primary"
          startIcon={<EditIcon />}
          component={Link}
          to={`/app/agents/edit/${selectedAgent._id}`}
          sx={{ mr: 1 }}
        >
          编辑
        </Button>
        <Button
          variant="outlined"
          color="error"
          startIcon={<DeleteIcon />}
          onClick={handleDelete}
        >
          删除
        </Button>
      </Box>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>助手信息</Typography>
            <Divider sx={{ mb: 2 }} />
            
            <Typography variant="body1" gutterBottom>
              <strong>类型：</strong> {selectedAgent.type}
            </Typography>
            
            <Typography variant="body1" gutterBottom>
              <strong>描述：</strong> {selectedAgent.description}
            </Typography>
            
            <Typography variant="body1" gutterBottom>
              <strong>创建时间：</strong> {new Date(selectedAgent.createdAt).toLocaleString()}
            </Typography>
            
            <Typography variant="body1" gutterBottom>
              <strong>更新时间：</strong> {new Date(selectedAgent.updatedAt).toLocaleString()}
            </Typography>
          </Paper>
          
          {selectedAgent.parameters && Object.keys(selectedAgent.parameters).length > 0 && (
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>参数配置</Typography>
              <Divider sx={{ mb: 2 }} />
              
              <List>
                {Object.entries(selectedAgent.parameters).map(([key, value]) => (
                  <ListItem key={key} sx={{ py: 1 }}>
                    <ListItemText 
                      primary={<strong>{key}</strong>} 
                      secondary={typeof value === 'object' ? JSON.stringify(value) : String(value)} 
                    />
                  </ListItem>
                ))}
              </List>
            </Paper>
          )}
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>与助手对话</Typography>
            <Divider sx={{ mb: 2 }} />
            
            <Box 
              component="form" 
              onSubmit={handleSubmitQuery}
              sx={{ 
                display: 'flex',
                mb: 2
              }}
            >
              <TextField
                fullWidth
                variant="outlined"
                placeholder="输入您的问题..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                disabled={loading}
                sx={{ mr: 1 }}
              />
              <Button
                type="submit"
                variant="contained"
                color="primary"
                disabled={loading || !query.trim()}
                startIcon={<SendIcon />}
              >
                发送
              </Button>
            </Box>
            
            {loading && (
              <Box display="flex" justifyContent="center" my={2}>
                <CircularProgress size={24} />
              </Box>
            )}
            
            {error && (
              <Typography color="error" sx={{ my: 2 }}>
                {error}
              </Typography>
            )}
            
            {queryResponse && (
              <Card variant="outlined" sx={{ mt: 2 }}>
                <CardContent>
                  <Typography variant="body1" style={{ whiteSpace: 'pre-wrap' }}>
                    {queryResponse}
                  </Typography>
                </CardContent>
              </Card>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default AgentDetail; 