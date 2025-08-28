import React, { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import {
  Box,
  Button,
  Container,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  CardMedia,
  CardActions,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  CircularProgress,
  Divider,
  Alert,
} from '@mui/material';
import {
  Add as AddIcon,
  Search as SearchIcon,
  FitnessCenter as FitnessCenterIcon,
} from '@mui/icons-material';

import { RootState, AppDispatch } from '../../store';
import { fetchExercises } from '../../store/slices/rehabSlice';
import { useSelector as useReduxSelector } from 'react-redux';
import { createSelector } from 'reselect';

// 创建记忆化选择器
const selectExercises = createSelector(
  [(state: RootState) => state.rehab?.exercises || []],
  (exercises) => exercises
);

// 预定义的身体部位和难度级别
const bodyParts = [
  { value: 'all', label: '全部' },
  { value: 'shoulder', label: '肩部' },
  { value: 'knee', label: '膝盖' },
  { value: 'back', label: '背部' },
  { value: 'neck', label: '颈部' },
  { value: 'ankle', label: '踝部' },
  { value: 'wrist', label: '手腕' },
  { value: 'hip', label: '髋部' },
  { value: 'elbow', label: '肘部' },
];

const difficultyLevels = [
  { value: 'all', label: '全部' },
  { value: 'easy', label: '简单' },
  { value: 'medium', label: '中等' },
  { value: 'hard', label: '困难' },
];

const Exercises: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const exercises = useSelector(selectExercises);
  const { loading, error } = useReduxSelector((state: RootState) => state.rehab);
  const { user } = useReduxSelector((state: RootState) => state.auth);
  
  // 过滤和搜索状态
  const [searchTerm, setSearchTerm] = useState('');
  const [bodyPartFilter, setBodyPartFilter] = useState('all');
  const [difficultyFilter, setDifficultyFilter] = useState('all');
  
  // 获取练习列表
  useEffect(() => {
    dispatch(fetchExercises());
  }, [dispatch]);
  
  // 过滤练习列表
  const filteredExercises = exercises.filter((exercise: any) => {
    const matchesSearch = exercise.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                         exercise.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesBodyPart = bodyPartFilter === 'all' || exercise.body_part === bodyPartFilter;
    const matchesDifficulty = difficultyFilter === 'all' || exercise.difficulty.toLowerCase() === difficultyFilter.toLowerCase();
    
    return matchesSearch && matchesBodyPart && matchesDifficulty;
  });
  
  // 处理搜索输入变化
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
  };
  
  // 处理身体部位过滤变化
  const handleBodyPartChange = (e: React.ChangeEvent<{ value: unknown }>) => {
    setBodyPartFilter(e.target.value as string);
  };
  
  // 处理难度级别过滤变化
  const handleDifficultyChange = (e: React.ChangeEvent<{ value: unknown }>) => {
    setDifficultyFilter(e.target.value as string);
  };
  
  // 获取难度级别对应的颜色
  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty.toLowerCase()) {
      case 'easy':
        return 'success';
      case 'medium':
        return 'warning';
      case 'hard':
        return 'error';
      default:
        return 'default';
    }
  };
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          康复练习库
        </Typography>
        {/* 只有医生和管理员可以创建新练习 */}
        {user?.role === 'doctor' || user?.role === 'admin' ? (
          <Button
            variant="contained"
            color="primary"
            startIcon={<AddIcon />}
            component={Link}
            to="/app/exercises/new"
          >
            新建练习
          </Button>
        ) : null}
      </Box>
      
      {/* 过滤器和搜索栏 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              placeholder="搜索康复练习..."
              value={searchTerm}
              onChange={handleSearchChange}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
              variant="outlined"
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel id="body-part-filter-label">身体部位</InputLabel>
              <Select
                labelId="body-part-filter-label"
                id="body-part-filter"
                value={bodyPartFilter}
                label="身体部位"
                onChange={handleBodyPartChange}
              >
                {bodyParts.map((part) => (
                  <MenuItem key={part.value} value={part.value}>
                    {part.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel id="difficulty-filter-label">难度级别</InputLabel>
              <Select
                labelId="difficulty-filter-label"
                id="difficulty-filter"
                value={difficultyFilter}
                label="难度级别"
                onChange={handleDifficultyChange}
              >
                {difficultyLevels.map((level) => (
                  <MenuItem key={level.value} value={level.value}>
                    {level.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>
      
      {/* 加载中显示 */}
      {loading && (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      )}
      
      {/* 错误提示 */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      
      {/* 没有练习时的提示 */}
      {!loading && filteredExercises.length === 0 && (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1" gutterBottom>
            没有找到符合条件的康复练习。
          </Typography>
          {searchTerm || bodyPartFilter !== 'all' || difficultyFilter !== 'all' ? (
            <Button 
              variant="outlined" 
              onClick={() => {
                setSearchTerm('');
                setBodyPartFilter('all');
                setDifficultyFilter('all');
              }}
              sx={{ mt: 1 }}
            >
              清除过滤条件
            </Button>
          ) : (
            user?.role === 'doctor' || user?.role === 'admin' ? (
              <Button
                variant="contained"
                color="primary"
                startIcon={<AddIcon />}
                component={Link}
                to="/app/exercises/new"
                sx={{ mt: 1 }}
              >
                创建第一个练习
              </Button>
            ) : null
          )}
        </Paper>
      )}
      
      {/* 练习列表 */}
      {!loading && filteredExercises.length > 0 && (
        <Grid container spacing={3}>
          {filteredExercises.map((exercise: any) => (
            <Grid item xs={12} sm={6} md={4} key={exercise._id || exercise.id}>
              <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                {exercise.image_url ? (
                  <CardMedia
                    component="img"
                    sx={{ height: 140 }}
                    image={exercise.image_url}
                    alt={exercise.name}
                  />
                ) : (
                  <Box 
                    sx={{ 
                      height: 140, 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center',
                      bgcolor: 'grey.200'
                    }}
                  >
                    <FitnessCenterIcon fontSize="large" color="disabled" />
                  </Box>
                )}
                <CardContent sx={{ flexGrow: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <Typography gutterBottom variant="h6" component="h2">
                      {exercise.name}
                    </Typography>
                    <Chip 
                      label={
                        exercise.difficulty === 'easy' ? '简单' :
                        exercise.difficulty === 'medium' ? '中等' : '困难'
                      }
                      color={getDifficultyColor(exercise.difficulty) as any}
                      size="small"
                    />
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                    {exercise.description.length > 120 
                      ? `${exercise.description.substring(0, 120)}...` 
                      : exercise.description
                    }
                  </Typography>
                  <Chip 
                    label={
                      bodyParts.find(part => part.value === exercise.body_part)?.label || 
                      exercise.body_part
                    }
                    size="small"
                    variant="outlined"
                  />
                </CardContent>
                <Divider />
                <CardActions>
                  <Button 
                    size="small" 
                    component={Link} 
                    to={`/app/exercises/${exercise._id || exercise.id}`}
                  >
                    查看详情
                  </Button>
                  {user?.role === 'doctor' || user?.role === 'admin' ? (
                    <Button 
                      size="small"
                      component={Link}
                      to={`/app/exercises/edit/${exercise._id || exercise.id}`}
                    >
                      编辑
                    </Button>
                  ) : null}
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Container>
  );
};

export default Exercises; 