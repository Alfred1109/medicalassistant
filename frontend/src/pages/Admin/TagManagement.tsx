import React from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Grid,
  TextField,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';

// 模拟标签数据
const mockTags = [
  { id: 1, name: '骨科康复', category: '康复类型', color: 'primary' },
  { id: 2, name: '神经康复', category: '康复类型', color: 'secondary' },
  { id: 3, name: '老年康复', category: '康复类型', color: 'success' },
  { id: 4, name: '物理治疗', category: '治疗方式', color: 'info' },
  { id: 5, name: '运动疗法', category: '治疗方式', color: 'warning' },
  { id: 6, name: '作业疗法', category: '治疗方式', color: 'error' },
  { id: 7, name: '言语治疗', category: '治疗方式', color: 'primary' },
  { id: 8, name: '高血压', category: '疾病类型', color: 'secondary' },
  { id: 9, name: '糖尿病', category: '疾病类型', color: 'success' },
  { id: 10, name: '中风', category: '疾病类型', color: 'warning' },
  { id: 11, name: '膝关节损伤', category: '疾病类型', color: 'error' },
  { id: 12, name: '腰椎间盘突出', category: '疾病类型', color: 'info' },
];

// 标签类别
const tagCategories = [
  '康复类型',
  '治疗方式',
  '疾病类型',
  '患者分类',
  '设备类型',
  '其他'
];

// 标签颜色
const tagColors = [
  { name: '蓝色', value: 'primary' },
  { name: '紫色', value: 'secondary' },
  { name: '绿色', value: 'success' },
  { name: '青色', value: 'info' },
  { name: '橙色', value: 'warning' },
  { name: '红色', value: 'error' },
  { name: '默认', value: 'default' },
];

interface TagData {
  id: number;
  name: string;
  category: string;
  color: string;
}

const TagManagement: React.FC = () => {
  const [tags, setTags] = React.useState<TagData[]>(mockTags);
  const [openDialog, setOpenDialog] = React.useState(false);
  const [selectedTag, setSelectedTag] = React.useState<TagData | null>(null);
  const [newTag, setNewTag] = React.useState<Partial<TagData>>({
    name: '',
    category: '',
    color: 'primary'
  });
  const [currentCategory, setCurrentCategory] = React.useState<string>('全部');

  const handleAddTag = () => {
    setSelectedTag(null);
    setNewTag({
      name: '',
      category: '',
      color: 'primary'
    });
    setOpenDialog(true);
  };

  const handleEditTag = (tag: TagData) => {
    setSelectedTag(tag);
    setNewTag({
      name: tag.name,
      category: tag.category,
      color: tag.color
    });
    setOpenDialog(true);
  };

  const handleDeleteTag = (id: number) => {
    setTags(tags.filter(tag => tag.id !== id));
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setSelectedTag(null);
  };

  const handleSaveTag = () => {
    if (newTag.name && newTag.category) {
      if (selectedTag) {
        // 编辑现有标签
        setTags(tags.map(tag => 
          tag.id === selectedTag.id 
            ? { ...tag, name: newTag.name!, category: newTag.category!, color: newTag.color! } 
            : tag
        ));
      } else {
        // 添加新标签
        const newId = Math.max(...tags.map(tag => tag.id)) + 1;
        setTags([...tags, { 
          id: newId, 
          name: newTag.name, 
          category: newTag.category, 
          color: newTag.color || 'primary' 
        } as TagData]);
      }
      handleCloseDialog();
    }
  };

  const handleCategoryChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setCurrentCategory(event.target.value as string);
  };

  const handleTagNameChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setNewTag({...newTag, name: event.target.value});
  };

  const handleTagCategoryChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setNewTag({...newTag, category: event.target.value as string});
  };

  const handleTagColorChange = (event: React.ChangeEvent<{ value: unknown }>) => {
    setNewTag({...newTag, color: event.target.value as string});
  };

  // 根据当前选择的类别筛选标签
  const filteredTags = currentCategory === '全部' 
    ? tags 
    : tags.filter(tag => tag.category === currentCategory);

  // 获取所有标签类别（包括自定义类别）
  const allCategories = ['全部', ...new Set(tags.map(tag => tag.category))];

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          标签管理
        </Typography>
        <Button 
          variant="contained" 
          color="primary" 
          startIcon={<AddIcon />}
          onClick={handleAddTag}
        >
          添加标签
        </Button>
      </Box>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" alignItems="center" mb={3}>
          <Typography variant="subtitle1" sx={{ mr: 2 }}>
            按类别筛选:
          </Typography>
          <FormControl variant="outlined" size="small" sx={{ minWidth: 200 }}>
            <Select
              value={currentCategory}
              onChange={handleCategoryChange}
            >
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

        <Grid container spacing={2}>
          {filteredTags.map((tag) => (
            <Grid item key={tag.id}>
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
                    boxShadow: 1
                  }
                }}
              >
                <Chip 
                  icon={<LocalOfferIcon />}
                  label={tag.name}
                  color={tag.color as any}
                  sx={{ mr: 1 }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ ml: 1, mr: 2 }}>
                  {tag.category}
                </Typography>
                <IconButton 
                  size="small" 
                  color="primary"
                  onClick={() => handleEditTag(tag)}
                >
                  <EditIcon fontSize="small" />
                </IconButton>
                <IconButton 
                  size="small" 
                  color="error"
                  onClick={() => handleDeleteTag(tag.id)}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Paper>

      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedTag ? '编辑标签' : '添加新标签'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                label="标签名称"
                fullWidth
                value={newTag.name}
                onChange={handleTagNameChange}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>标签类别</InputLabel>
                <Select
                  label="标签类别"
                  value={newTag.category}
                  onChange={handleTagCategoryChange}
                >
                  {tagCategories.map((category) => (
                    <MenuItem key={category} value={category}>
                      {category}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>标签颜色</InputLabel>
                <Select
                  label="标签颜色"
                  value={newTag.color}
                  onChange={handleTagColorChange}
                >
                  {tagColors.map((color) => (
                    <MenuItem key={color.value} value={color.value}>
                      <Box display="flex" alignItems="center">
                        <Box 
                          sx={{ 
                            width: 20, 
                            height: 20, 
                            borderRadius: '50%', 
                            bgcolor: `${color.value}.main`,
                            mr: 1
                          }} 
                        />
                        {color.name}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2" gutterBottom>
                预览:
              </Typography>
              <Box sx={{ p: 1 }}>
                <Chip 
                  icon={<LocalOfferIcon />}
                  label={newTag.name || '标签名称'}
                  color={newTag.color as any || 'primary'}
                />
              </Box>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button 
            onClick={handleSaveTag} 
            variant="contained" 
            color="primary"
            disabled={!newTag.name || !newTag.category}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default TagManagement; 