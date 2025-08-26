import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Paper,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
  IconButton,
  Button,
  Divider,
  TextField,
  InputAdornment,
  Chip,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Tooltip
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import FilterListIcon from '@mui/icons-material/FilterList';
import ArticleIcon from '@mui/icons-material/Article';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import PendingActionsIcon from '@mui/icons-material/PendingActions';
import WarningIcon from '@mui/icons-material/Warning';
import DescriptionIcon from '@mui/icons-material/Description';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CreateIcon from '@mui/icons-material/Create';
import AccessTimeIcon from '@mui/icons-material/AccessTime';

// 导入API服务
import * as consentApi from '../../services/consentService';

// 文档状态类型
type DocumentStatus = 'pending' | 'signed' | 'expired' | 'all';

// 知情同意文档类型
interface ConsentDocument {
  id: string;
  title: string;
  description: string;
  category: string;
  provider: string;
  createdAt: string;
  expiresAt?: string;
  status: 'pending' | 'signed' | 'expired';
  signedAt?: string;
  urgent: boolean;
}

const ConsentDocumentList: React.FC = () => {
  const navigate = useNavigate();
  
  // 状态定义
  const [documents, setDocuments] = useState<ConsentDocument[]>([]);
  const [filteredDocuments, setFilteredDocuments] = useState<ConsentDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<DocumentStatus>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [tabValue, setTabValue] = useState(0);
  
  // 获取文档类别列表
  const categories = Array.from(
    new Set(documents.map(doc => doc.category))
  ).filter(Boolean);
  
  // 页面加载时获取文档列表
  useEffect(() => {
    const loadDocuments = async () => {
      try {
        setLoading(true);
        // 调用API获取知情同意文档列表
        const response = await consentApi.getConsentDocuments();
        setDocuments(response);
        setFilteredDocuments(response);
      } catch (err) {
        console.error('获取知情同意文档列表失败:', err);
        setError('获取文档列表失败，请稍后重试');
      } finally {
        setLoading(false);
      }
    };
    
    loadDocuments();
  }, []);
  
  // 当筛选条件变化时更新文档列表
  useEffect(() => {
    let filtered = [...documents];
    
    // 根据状态筛选
    if (statusFilter !== 'all') {
      filtered = filtered.filter(doc => doc.status === statusFilter);
    }
    
    // 根据类别筛选
    if (categoryFilter !== 'all') {
      filtered = filtered.filter(doc => doc.category === categoryFilter);
    }
    
    // 根据搜索关键词筛选
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(doc => 
        doc.title.toLowerCase().includes(query) || 
        doc.description?.toLowerCase().includes(query) ||
        doc.provider?.toLowerCase().includes(query)
      );
    }
    
    // 根据标签页筛选
    if (tabValue === 1) {
      // 待签署文档
      filtered = filtered.filter(doc => doc.status === 'pending');
    } else if (tabValue === 2) {
      // 已签署文档
      filtered = filtered.filter(doc => doc.status === 'signed');
    } else if (tabValue === 3) {
      // 已过期文档
      filtered = filtered.filter(doc => doc.status === 'expired');
    }
    
    // 更新过滤后的文档列表
    setFilteredDocuments(filtered);
  }, [documents, statusFilter, categoryFilter, searchQuery, tabValue]);
  
  // 处理搜索输入变化
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  };
  
  // 处理状态筛选变化
  const handleStatusFilterChange = (event: React.ChangeEvent<{value: unknown}>) => {
    setStatusFilter(event.target.value as DocumentStatus);
  };
  
  // 处理类别筛选变化
  const handleCategoryFilterChange = (event: React.ChangeEvent<{value: unknown}>) => {
    setCategoryFilter(event.target.value as string);
  };
  
  // 处理标签页切换
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 查看文档详情
  const handleViewDocument = (id: string) => {
    navigate(`/patient/documents/${id}`);
  };
  
  // 签署文档
  const handleSignDocument = (id: string) => {
    navigate(`/patient/documents/${id}/sign`);
  };
  
  // 获取文档状态标签
  const getStatusChip = (status: string, urgent: boolean) => {
    if (status === 'pending') {
      return (
        <Chip 
          icon={urgent ? <WarningIcon /> : <PendingActionsIcon />} 
          label={urgent ? "紧急待签" : "待签署"} 
          color={urgent ? "error" : "warning"} 
          size="small" 
          variant={urgent ? "filled" : "outlined"}
        />
      );
    } else if (status === 'signed') {
      return (
        <Chip 
          icon={<CheckCircleIcon />} 
          label="已签署" 
          color="success" 
          size="small" 
          variant="outlined" 
        />
      );
    } else if (status === 'expired') {
      return (
        <Chip 
          icon={<AccessTimeIcon />} 
          label="已过期" 
          color="default" 
          size="small" 
          variant="outlined" 
        />
      );
    }
    return null;
  };
  
  // 渲染文档列表项
  const renderDocumentItem = (document: ConsentDocument) => {
    const isPending = document.status === 'pending';
    
    return (
      <ListItem
        key={document.id}
        alignItems="flex-start"
        sx={{
          mb: 1,
          borderLeft: document.urgent ? '4px solid #f44336' : 'none',
          bgcolor: document.urgent ? 'rgba(244, 67, 54, 0.05)' : 'transparent'
        }}
      >
        <ListItemIcon>
          <ArticleIcon color={isPending ? "primary" : "action"} />
        </ListItemIcon>
        <ListItemText
          primary={
            <Box display="flex" alignItems="center">
              <Typography variant="subtitle1" component="span">
                {document.title}
              </Typography>
              <Box ml={1}>
                {getStatusChip(document.status, document.urgent)}
              </Box>
            </Box>
          }
          secondary={
            <>
              <Typography variant="body2" color="textSecondary" component="span">
                {document.description}
              </Typography>
              <Box mt={1} display="flex" alignItems="center">
                <Typography variant="caption" color="textSecondary">
                  提供方: {document.provider} | 
                  类别: {document.category} | 
                  创建时间: {new Date(document.createdAt).toLocaleDateString()}
                </Typography>
              </Box>
              {document.status === 'signed' && document.signedAt && (
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 0.5 }}>
                  签署时间: {new Date(document.signedAt).toLocaleString()}
                </Typography>
              )}
              {document.status === 'expired' && document.expiresAt && (
                <Typography variant="caption" color="error" sx={{ display: 'block', mt: 0.5 }}>
                  过期时间: {new Date(document.expiresAt).toLocaleString()}
                </Typography>
              )}
            </>
          }
        />
        <ListItemSecondaryAction>
          <Box>
            <Tooltip title="查看文档">
              <IconButton edge="end" aria-label="查看" onClick={() => handleViewDocument(document.id)}>
                <VisibilityIcon />
              </IconButton>
            </Tooltip>
            {isPending && (
              <Tooltip title="签署文档">
                <IconButton 
                  edge="end" 
                  aria-label="签署" 
                  onClick={() => handleSignDocument(document.id)}
                  color="primary"
                  sx={{ ml: 1 }}
                >
                  <CreateIcon />
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </ListItemSecondaryAction>
      </ListItem>
    );
  };
  
  // 渲染加载状态
  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress sx={{ mb: 2 }} />
        <Typography variant="h6">加载知情同意文档列表...</Typography>
      </Container>
    );
  }
  
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <DescriptionIcon color="primary" sx={{ mr: 2 }} />
          <Typography variant="h5" component="h1">
            知情同意文档
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <Button 
            variant="outlined"
            onClick={() => navigate('/app/patient/documents/templates')}
          >
            浏览文档模板
          </Button>
        </Box>
        
        <Divider sx={{ mb: 3 }} />
        
        {/* 筛选工具栏 */}
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                placeholder="搜索文档..."
                value={searchQuery}
                onChange={handleSearchChange}
                variant="outlined"
                size="small"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  )
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <FormControl variant="outlined" size="small" fullWidth>
                <InputLabel id="status-filter-label">文档状态</InputLabel>
                <Select
                  labelId="status-filter-label"
                  value={statusFilter}
                  onChange={handleStatusFilterChange as any}
                  label="文档状态"
                  startAdornment={<FilterListIcon sx={{ mr: 1 }} />}
                >
                  <MenuItem value="all">所有状态</MenuItem>
                  <MenuItem value="pending">待签署</MenuItem>
                  <MenuItem value="signed">已签署</MenuItem>
                  <MenuItem value="expired">已过期</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <FormControl variant="outlined" size="small" fullWidth>
                <InputLabel id="category-filter-label">文档类别</InputLabel>
                <Select
                  labelId="category-filter-label"
                  value={categoryFilter}
                  onChange={handleCategoryFilterChange as any}
                  label="文档类别"
                >
                  <MenuItem value="all">所有类别</MenuItem>
                  {categories.map(category => (
                    <MenuItem key={category} value={category}>
                      {category}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>
        
        {/* 标签页导航 */}
        <Box sx={{ mb: 3 }}>
          <Tabs 
            value={tabValue} 
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
          >
            <Tab label="所有文档" />
            <Tab 
              label={
                <Box display="flex" alignItems="center">
                  待签署
                  <Chip 
                    label={documents.filter(d => d.status === 'pending').length} 
                    size="small" 
                    color="warning" 
                    sx={{ ml: 1 }} 
                  />
                </Box>
              } 
            />
            <Tab 
              label={
                <Box display="flex" alignItems="center">
                  已签署
                  <Chip 
                    label={documents.filter(d => d.status === 'signed').length} 
                    size="small" 
                    color="success" 
                    sx={{ ml: 1 }} 
                  />
                </Box>
              } 
            />
            <Tab 
              label={
                <Box display="flex" alignItems="center">
                  已过期
                  <Chip 
                    label={documents.filter(d => d.status === 'expired').length} 
                    size="small" 
                    color="default" 
                    sx={{ ml: 1 }} 
                  />
                </Box>
              } 
            />
          </Tabs>
        </Box>
        
        {/* 文档列表 */}
        {error ? (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        ) : filteredDocuments.length === 0 ? (
          <Box sx={{ py: 4, textAlign: 'center' }}>
            <Typography variant="h6" color="textSecondary" gutterBottom>
              没有找到匹配的文档
            </Typography>
            <Typography variant="body2" color="textSecondary">
              尝试调整搜索条件或查看所有文档
            </Typography>
            {tabValue !== 0 && (
              <Button 
                variant="outlined" 
                sx={{ mt: 2 }}
                onClick={() => setTabValue(0)}
              >
                查看所有文档
              </Button>
            )}
          </Box>
        ) : (
          <Paper variant="outlined" sx={{ mb: 3 }}>
            <List>
              {filteredDocuments.map((document, index) => (
                <React.Fragment key={document.id}>
                  {renderDocumentItem(document)}
                  {index < filteredDocuments.length - 1 && <Divider component="li" />}
                </React.Fragment>
              ))}
            </List>
          </Paper>
        )}
        
        {/* 紧急文档提示 */}
        {documents.some(doc => doc.status === 'pending' && doc.urgent) && (
          <Alert severity="warning" sx={{ mt: 3 }}>
            您有紧急待签署的知情同意文档，请尽快处理。
          </Alert>
        )}
      </Paper>
    </Container>
  );
};

export default ConsentDocumentList; 