import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Grid,
  Chip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  CircularProgress,
  SelectChangeEvent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import apiClient from '../../services/api';

// 标签管理：数据来自 GET /api/admin/tags
// 该接口目前为后端占位实现（恒返回 []），创建/编辑/删除接口未持久化，故禁用相关入口
interface TagRow {
  id?: string | number;
  name?: string;
  category?: string;
  color?: string;
}

const TagManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [tags, setTags] = useState<TagRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [currentCategory, setCurrentCategory] = useState('全部');
  const [reloadKey, setReloadKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [tagName, setTagName] = useState('');
  const [tagCategory, setTagCategory] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchTags = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get('/admin/tags');
        if (!cancelled) {
          setTags(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取标签数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取标签数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchTags();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 标签类别从真实数据中提取
  const allCategories = useMemo(() => {
    const categories = Array.from(new Set(tags.map(tag => tag.category).filter(Boolean)));
    return ['全部', ...categories];
  }, [tags]);

  // 根据当前选择的类别筛选标签
  const filteredTags = useMemo(
    () =>
      currentCategory === '全部'
        ? tags
        : tags.filter(tag => tag.category === currentCategory),
    [tags, currentCategory]
  );

  const handleCategoryChange = (event: SelectChangeEvent<string>) => {
    setCurrentCategory(event.target.value);
  };

  // 加载中
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <CircularProgress />
        <Typography variant="body1" sx={{ ml: 2 }}>
          标签数据加载中...
        </Typography>
      </Box>
    );
  }

  // 加载失败：真实错误状态 + 重试
  if (error) {
    return (
      <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="300px">
        <Typography color="error" variant="body1" gutterBottom>
          {error}
        </Typography>
        <Button variant="outlined" onClick={() => setReloadKey(key => key + 1)}>
          重试
        </Button>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          标签管理
        </Typography>
        <Box textAlign="right">
          <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            添加标签
          </Button>
        </Box>
      </Box>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" alignItems="center" mb={3}>
          <Typography variant="subtitle1" sx={{ mr: 2 }}>
            按类别筛选:
          </Typography>
          <FormControl variant="outlined" size="small" sx={{ minWidth: 200 }}>
            <Select value={currentCategory} onChange={handleCategoryChange}>
              {allCategories.map((category) => (
                <MenuItem key={category} value={category}>
                  {category}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <Typography variant="h6" gutterBottom>
          {currentCategory === '全部' ? '所有标签' : `${currentCategory} 标签`}
        </Typography>
        <Divider sx={{ mb: 2 }} />

        {filteredTags.length === 0 ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="body1" color="text.secondary">
              暂无标签数据
            </Typography>
            <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
              后端管理接口建设中，暂无数据
            </Typography>
          </Box>
        ) : (
          <Grid container spacing={2}>
            {filteredTags.map((tag, index) => (
              <Grid item key={tag.id !== undefined ? tag.id : `tag-${index}`}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    bgcolor: 'background.paper',
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: 1,
                    p: 1,
                    '&:hover': {
                      boxShadow: 1,
                    },
                  }}
                >
                  <Chip
                    icon={<LocalOfferIcon />}
                    label={tag.name || '未命名标签'}
                    color={(tag.color as any) || 'default'}
                    sx={{ mr: 1 }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ ml: 1, mr: 2 }}>
                    {tag.category || '—'}
                  </Typography>
                  {tag.id !== undefined && <Button size="small" onClick={async () => { await apiClient.delete(`/admin/tags/${tag.id}`); setReloadKey(key => key + 1); }}>删除</Button>}
                </Box>
              </Grid>
            ))}
          </Grid>
        )}
      </Paper>
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>添加标签</DialogTitle>
        <DialogContent>
          <TextField fullWidth margin="dense" label="名称" value={tagName} onChange={event => setTagName(event.target.value)} />
          <TextField fullWidth margin="dense" label="类别" value={tagCategory} onChange={event => setTagCategory(event.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>取消</Button>
          <Button variant="contained" onClick={async () => {
            await apiClient.post('/admin/tags', { name: tagName.trim(), category: tagCategory.trim() });
            setTagName(''); setTagCategory(''); setCreateOpen(false); setReloadKey(key => key + 1);
          }}>保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default TagManagement;
