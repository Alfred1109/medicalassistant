import React, { useState, useEffect } from 'react';
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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  IconButton,
  Card,
  CardContent,
  CircularProgress,
  FormHelperText,
  Alert,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  SelectChangeEvent,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
} from '@mui/icons-material';

import { AppDispatch, RootState } from '../../store';
import {
  fetchExerciseById,
  createExercise,
  updateExercise
} from '../../store/slices/rehabSlice';
import { ExerciseFormValues } from '../../types/rehab';
import httpClient from '../../services/httpClient';

// 表单状态类型:难度使用与后端一致的字面量联合类型
interface ExerciseFormState {
  name: string;
  description: string;
  body_part: string;
  difficulty: 'easy' | 'medium' | 'hard';
  duration_minutes: number;
  repetitions: number;
  sets: number;
  image_url: string;
  video_url: string;
  instructions: string[];
  contraindications: string[];
  benefits: string[];
}

// 身体部位选项
const bodyParts = [
  { value: 'shoulder', label: '肩部' },
  { value: 'knee', label: '膝盖' },
  { value: 'back', label: '背部' },
  { value: 'neck', label: '颈部' },
  { value: 'ankle', label: '踝部' },
  { value: 'wrist', label: '手腕' },
  { value: 'hip', label: '髋部' },
  { value: 'elbow', label: '肘部' },
];

// 难度级别选项
const difficultyLevels = [
  { value: 'easy', label: '简单' },
  { value: 'medium', label: '中等' },
  { value: 'hard', label: '困难' },
];

const ExerciseForm: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  
  const { selectedExercise, loading, error } = useSelector((state: RootState) => state.rehab);
  
  // 是否为编辑模式
  const isEditMode = !!id;
  
  // 表单状态
  const [formData, setFormData] = useState<ExerciseFormState>({
    name: '',
    description: '',
    body_part: 'shoulder',
    difficulty: 'medium',
    duration_minutes: 10,
    repetitions: 10,
    sets: 3,
    image_url: '',
    video_url: '',
    instructions: [] as string[],
    contraindications: [] as string[],
    benefits: [] as string[],
  });
  
  // 表单验证错误
  const [formErrors, setFormErrors] = useState({
    name: '',
    description: '',
    body_part: '',
    difficulty: '',
    duration_minutes: '',
    repetitions: '',
    sets: '',
  });

  // 媒体链接校验错误（宽松校验：非空时必须是 http/https 链接）
  const [mediaErrors, setMediaErrors] = useState({
    image_url: '',
    video_url: '',
  });
  
  // 临时输入字段
  const [newInstruction, setNewInstruction] = useState('');
  const [newContraindication, setNewContraindication] = useState('');
  const [newBenefit, setNewBenefit] = useState('');
  
  // 提交状态
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  
  // 获取练习详情（编辑模式）
  useEffect(() => {
    if (isEditMode && id) {
      dispatch(fetchExerciseById(id));
    }
  }, [dispatch, id, isEditMode]);
  
  // 填充表单数据（编辑模式）
  useEffect(() => {
    if (isEditMode && selectedExercise) {
      setFormData({
        name: selectedExercise.name || '',
        description: selectedExercise.description || '',
        body_part: selectedExercise.body_part || 'shoulder',
        difficulty: selectedExercise.difficulty || 'medium',
        duration_minutes: selectedExercise.duration_minutes || 10,
        repetitions: selectedExercise.repetitions || 10,
        sets: selectedExercise.sets || 3,
        image_url: selectedExercise.image_url || '',
        video_url: selectedExercise.video_url || '',
        instructions: selectedExercise.instructions || [],
        contraindications: selectedExercise.contraindications || [],
        benefits: selectedExercise.benefits || [],
      });
    }
  }, [isEditMode, selectedExercise]);
  
  // 处理文本输入变化
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement> | SelectChangeEvent<string>) => {
    const { name, value } = e.target;
    
    setFormData((prev) => ({
      ...prev,
      [name as string]: value,
    }));
    
    // 清除对应的错误
    if (formErrors[name as keyof typeof formErrors]) {
      setFormErrors((prev) => ({
        ...prev,
        [name as string]: '',
      }));
    }
  };
  
  // 处理数字输入变化
  const handleNumberInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    const numValue = parseInt(value);
    
    if (!isNaN(numValue) && numValue >= 0) {
      setFormData((prev) => ({
        ...prev,
        [name]: numValue,
      }));
    }
    
    // 清除对应的错误
    if (formErrors[name as keyof typeof formErrors]) {
      setFormErrors((prev) => ({
        ...prev,
        [name]: '',
      }));
    }
  };
  
  // 处理媒体链接输入：后端暂无文件上传接口，此处仅接受用户粘贴的已有 URL
  const handleMediaUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    // 输入时清除该字段的校验错误
    setMediaErrors((prev) => ({
      ...prev,
      [name]: '',
    }));
  };

  // 宽松校验媒体链接：非空时必须是 http/https 开头的 URL
  const validateMediaUrls = (): boolean => {
    const errors = { image_url: '', video_url: '' };
    let isValid = true;

    const localMedia = /^\/api\/rehabilitation\/exercises\/media\/[a-z0-9]+\.(jpg|png|mp4|webm)$/;
    if (formData.image_url.trim() && !/^https?:\/\//i.test(formData.image_url.trim()) && !localMedia.test(formData.image_url.trim())) {
      errors.image_url = '请输入以 http:// 或 https:// 开头的图片链接';
      isValid = false;
    }
    if (formData.video_url.trim() && !/^https?:\/\//i.test(formData.video_url.trim()) && !localMedia.test(formData.video_url.trim())) {
      errors.video_url = '请输入以 http:// 或 https:// 开头的视频链接';
      isValid = false;
    }

    setMediaErrors(errors);
    return isValid;
  };

  // 添加指导说明
  const handleAddInstruction = () => {
    if (newInstruction.trim()) {
      setFormData((prev) => ({
        ...prev,
        instructions: [...prev.instructions, newInstruction.trim()],
      }));
      setNewInstruction('');
    }
  };
  
  // 删除指导说明
  const handleDeleteInstruction = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      instructions: prev.instructions.filter((_, i) => i !== index),
    }));
  };
  
  // 添加禁忌症
  const handleAddContraindication = () => {
    if (newContraindication.trim()) {
      setFormData((prev) => ({
        ...prev,
        contraindications: [...prev.contraindications, newContraindication.trim()],
      }));
      setNewContraindication('');
    }
  };
  
  // 删除禁忌症
  const handleDeleteContraindication = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      contraindications: prev.contraindications.filter((_, i) => i !== index),
    }));
  };
  
  // 添加康复获益
  const handleAddBenefit = () => {
    if (newBenefit.trim()) {
      setFormData((prev) => ({
        ...prev,
        benefits: [...prev.benefits, newBenefit.trim()],
      }));
      setNewBenefit('');
    }
  };
  
  // 删除康复获益
  const handleDeleteBenefit = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      benefits: prev.benefits.filter((_, i) => i !== index),
    }));
  };
  
  // 表单验证
  const validateForm = () => {
    const errors = {
      name: '',
      description: '',
      body_part: '',
      difficulty: '',
      duration_minutes: '',
      repetitions: '',
      sets: '',
    };
    
    let isValid = true;
    
    if (!formData.name.trim()) {
      errors.name = '请输入练习名称';
      isValid = false;
    }
    
    if (!formData.description.trim()) {
      errors.description = '请输入练习描述';
      isValid = false;
    }
    
    if (!formData.body_part) {
      errors.body_part = '请选择身体部位';
      isValid = false;
    }
    
    if (!formData.difficulty) {
      errors.difficulty = '请选择难度级别';
      isValid = false;
    }
    
    if (formData.duration_minutes <= 0) {
      errors.duration_minutes = '持续时间必须大于0';
      isValid = false;
    }
    
    if (formData.repetitions <= 0) {
      errors.repetitions = '重复次数必须大于0';
      isValid = false;
    }
    
    if (formData.sets <= 0) {
      errors.sets = '组数必须大于0';
      isValid = false;
    }
    
    setFormErrors(errors);
    return isValid;
  };
  
  // 提交表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }

    // 媒体链接宽松校验（后端无上传接口，仅接受合法 URL）
    if (!validateMediaUrls()) {
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const submitData: ExerciseFormValues = {
        ...formData,
        image_url: formData.image_url.trim(),
        video_url: formData.video_url.trim(),
      };
      
      if (isEditMode && id) {
        // 更新现有练习
        await dispatch(updateExercise({ id, exerciseData: submitData })).unwrap();
      } else {
        // 创建新练习
        await dispatch(createExercise(submitData)).unwrap();
      }
      
      // 导航回练习列表
      navigate('/app/exercises');
    } catch (err: any) {
      setSubmitError(err.message || '保存练习失败');
    } finally {
      setIsSubmitting(false);
    }
  };
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/app/exercises')}
          sx={{ mb: 2 }}
        >
          返回练习列表
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          {isEditMode ? '编辑练习' : '创建新练习'}
        </Typography>
      </Box>
      
      {submitError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {submitError}
        </Alert>
      )}
      
      {loading && isEditMode ? (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      ) : (
        <Box component="form" onSubmit={handleSubmit}>
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              基本信息
            </Typography>
            <Divider sx={{ mb: 3 }} />
            
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <TextField
                  required
                  fullWidth
                  label="练习名称"
                  name="name"
                  value={formData.name}
                  onChange={handleInputChange}
                  error={!!formErrors.name}
                  helperText={formErrors.name}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  required
                  fullWidth
                  label="描述"
                  name="description"
                  value={formData.description}
                  onChange={handleInputChange}
                  multiline
                  rows={3}
                  error={!!formErrors.description}
                  helperText={formErrors.description}
                />
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth required error={!!formErrors.body_part}>
                  <InputLabel id="body-part-label">身体部位</InputLabel>
                  <Select
                    labelId="body-part-label"
                    id="body-part"
                    name="body_part"
                    value={formData.body_part}
                    label="身体部位"
                    onChange={handleInputChange}
                  >
                    {bodyParts.map((part) => (
                      <MenuItem key={part.value} value={part.value}>
                        {part.label}
                      </MenuItem>
                    ))}
                  </Select>
                  {formErrors.body_part && (
                    <FormHelperText>{formErrors.body_part}</FormHelperText>
                  )}
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth required error={!!formErrors.difficulty}>
                  <InputLabel id="difficulty-label">难度级别</InputLabel>
                  <Select
                    labelId="difficulty-label"
                    id="difficulty"
                    name="difficulty"
                    value={formData.difficulty}
                    label="难度级别"
                    onChange={handleInputChange}
                  >
                    {difficultyLevels.map((level) => (
                      <MenuItem key={level.value} value={level.value}>
                        {level.label}
                      </MenuItem>
                    ))}
                  </Select>
                  {formErrors.difficulty && (
                    <FormHelperText>{formErrors.difficulty}</FormHelperText>
                  )}
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sm={4}>
                <TextField
                  required
                  fullWidth
                  label="持续时间（分钟）"
                  name="duration_minutes"
                  type="number"
                  value={formData.duration_minutes}
                  onChange={handleNumberInputChange}
                  InputProps={{ inputProps: { min: 1 } }}
                  error={!!formErrors.duration_minutes}
                  helperText={formErrors.duration_minutes}
                />
              </Grid>
              
              <Grid item xs={12} sm={4}>
                <TextField
                  required
                  fullWidth
                  label="重复次数"
                  name="repetitions"
                  type="number"
                  value={formData.repetitions}
                  onChange={handleNumberInputChange}
                  InputProps={{ inputProps: { min: 1 } }}
                  error={!!formErrors.repetitions}
                  helperText={formErrors.repetitions}
                />
              </Grid>
              
              <Grid item xs={12} sm={4}>
                <TextField
                  required
                  fullWidth
                  label="组数"
                  name="sets"
                  type="number"
                  value={formData.sets}
                  onChange={handleNumberInputChange}
                  InputProps={{ inputProps: { min: 1 } }}
                  error={!!formErrors.sets}
                  helperText={formErrors.sets}
                />
              </Grid>
            </Grid>
          </Paper>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 3, mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  图片链接
                </Typography>
                <Divider sx={{ mb: 2 }} />

                <Alert severity="info" sx={{ mb: 2 }}>
                  可以上传 JPG、PNG，或继续粘贴已有的 http/https 链接。
                </Alert>
                <Button component="label" sx={{ mb: 2 }}>上传图片
                  <input hidden accept="image/jpeg,image/png" type="file" onChange={async event => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    const form = new FormData();
                    form.set('file', file);
                    try {
                      const { data } = await httpClient.post('/rehabilitation/exercises/media', form);
                      setFormData(current => ({ ...current, image_url: data.url }));
                    } catch {
                      setMediaErrors(current => ({ ...current, image_url: '图片没有上传。' }));
                    }
                  }} />
                </Button>

                <TextField
                  fullWidth
                  label="图片 URL"
                  name="image_url"
                  placeholder="https://example.com/exercise.jpg"
                  value={formData.image_url}
                  onChange={handleMediaUrlChange}
                  error={!!mediaErrors.image_url}
                  helperText={mediaErrors.image_url || '选填'}
                />

                {/* 仅在链接合法时展示预览，避免渲染非法内容 */}
                {formData.image_url.trim() && (/^https?:\/\//i.test(formData.image_url.trim()) || formData.image_url.startsWith('/api/rehabilitation/exercises/media/')) && (
                  <Box mt={2} textAlign="center">
                    <img
                      src={formData.image_url.trim()}
                      alt="练习图片预览"
                      style={{ maxWidth: '100%', maxHeight: '200px' }}
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                      }}
                    />
                  </Box>
                )}
              </Paper>
            </Grid>

            <Grid item xs={12} md={6}>
              <Paper sx={{ p: 3, mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  视频链接
                </Typography>
                <Divider sx={{ mb: 2 }} />

                <Alert severity="info" sx={{ mb: 2 }}>
                  可以上传 MP4、WebM，或继续粘贴已有的 http/https 链接。
                </Alert>
                <Button component="label" sx={{ mb: 2 }}>上传视频
                  <input hidden accept="video/mp4,video/webm" type="file" onChange={async event => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    const form = new FormData();
                    form.set('file', file);
                    try {
                      const { data } = await httpClient.post('/rehabilitation/exercises/media', form);
                      setFormData(current => ({ ...current, video_url: data.url }));
                    } catch {
                      setMediaErrors(current => ({ ...current, video_url: '视频没有上传。' }));
                    }
                  }} />
                </Button>

                <TextField
                  fullWidth
                  label="视频 URL"
                  name="video_url"
                  placeholder="https://example.com/exercise.mp4"
                  value={formData.video_url}
                  onChange={handleMediaUrlChange}
                  error={!!mediaErrors.video_url}
                  helperText={mediaErrors.video_url || '选填'}
                />
              </Paper>
            </Grid>
          </Grid>
          
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 3, mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  执行步骤
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <Box sx={{ mb: 2 }}>
                  <TextField
                    fullWidth
                    label="添加执行步骤"
                    value={newInstruction}
                    onChange={(e) => setNewInstruction(e.target.value)}
                    multiline
                    rows={2}
                    sx={{ mb: 1 }}
                  />
                  <Button
                    variant="outlined"
                    startIcon={<AddIcon />}
                    onClick={handleAddInstruction}
                    disabled={!newInstruction.trim()}
                    fullWidth
                  >
                    添加步骤
                  </Button>
                </Box>
                
                <List>
                  {formData.instructions.map((instruction, index) => (
                    <ListItem key={index} divider>
                      <ListItemText
                        primary={`${index + 1}. ${instruction}`}
                      />
                      <ListItemSecondaryAction>
                        <IconButton 
                          edge="end" 
                          onClick={() => handleDeleteInstruction(index)}
                          size="small"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                  {formData.instructions.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                      暂无执行步骤
                    </Typography>
                  )}
                </List>
              </Paper>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 3, mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  禁忌症
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <Box sx={{ mb: 2 }}>
                  <TextField
                    fullWidth
                    label="添加禁忌症"
                    value={newContraindication}
                    onChange={(e) => setNewContraindication(e.target.value)}
                    multiline
                    rows={2}
                    sx={{ mb: 1 }}
                  />
                  <Button
                    variant="outlined"
                    startIcon={<AddIcon />}
                    onClick={handleAddContraindication}
                    disabled={!newContraindication.trim()}
                    fullWidth
                  >
                    添加禁忌症
                  </Button>
                </Box>
                
                <List>
                  {formData.contraindications.map((contraindication, index) => (
                    <ListItem key={index} divider>
                      <ListItemText
                        primary={contraindication}
                      />
                      <ListItemSecondaryAction>
                        <IconButton 
                          edge="end" 
                          onClick={() => handleDeleteContraindication(index)}
                          size="small"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                  {formData.contraindications.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                      暂无禁忌症
                    </Typography>
                  )}
                </List>
              </Paper>
            </Grid>
            
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 3, mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  康复获益
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <Box sx={{ mb: 2 }}>
                  <TextField
                    fullWidth
                    label="添加康复获益"
                    value={newBenefit}
                    onChange={(e) => setNewBenefit(e.target.value)}
                    multiline
                    rows={2}
                    sx={{ mb: 1 }}
                  />
                  <Button
                    variant="outlined"
                    startIcon={<AddIcon />}
                    onClick={handleAddBenefit}
                    disabled={!newBenefit.trim()}
                    fullWidth
                  >
                    添加获益
                  </Button>
                </Box>
                
                <List>
                  {formData.benefits.map((benefit, index) => (
                    <ListItem key={index} divider>
                      <ListItemText
                        primary={benefit}
                      />
                      <ListItemSecondaryAction>
                        <IconButton 
                          edge="end" 
                          onClick={() => handleDeleteBenefit(index)}
                          size="small"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                  {formData.benefits.length === 0 && (
                    <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                      暂无康复获益
                    </Typography>
                  )}
                </List>
              </Paper>
            </Grid>
          </Grid>
          
          <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="outlined"
              onClick={() => navigate('/app/exercises')}
              sx={{ mr: 2 }}
            >
              取消
            </Button>
            <Button
              type="submit"
              variant="contained"
              color="primary"
              startIcon={isSubmitting ? <CircularProgress size={24} /> : <SaveIcon />}
              disabled={isSubmitting}
            >
              {isSubmitting ? '保存中...' : '保存练习'}
            </Button>
          </Box>
        </Box>
      )}
    </Container>
  );
};

export default ExerciseForm; 