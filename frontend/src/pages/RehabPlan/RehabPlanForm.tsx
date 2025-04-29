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
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  CircularProgress,
  Divider,
  Alert,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Collapse,
  Stepper,
  Step,
  StepLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Save as SaveIcon,
  SmartToy as AIIcon,
  Edit as EditIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Check as CheckIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { RootState, AppDispatch } from '../../store';
import {
  createRehabPlan,
  updateRehabPlan,
  fetchRehabPlanById
} from '../../store/slices/rehabSlice';
import axios from 'axios';

// 添加BASE_URL常量
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5502';

// 生成计划所需的患者信息类型
interface PatientInfo {
  patient_id: string;
  patient_name: string;
  condition: string;
  goal: string;
}

// 运动信息类型
interface Exercise {
  name: string;
  description: string;
  body_part: string;
  difficulty: string;
  duration_minutes: number;
  repetitions: number;
  sets: number;
  instructions: string[];
  contraindications: string[];
  benefits: string[];
}

// 生成的康复计划类型
interface GeneratedPlan {
  _id?: string;
  name: string;
  description: string;
  patient_id: string;
  patient_name: string;
  condition: string;
  goal: string;
  frequency: string;
  duration_weeks: number;
  exercises: Exercise[];
  notes: string;
  status: string;
  metadata?: {
    generated_by: string;
    is_approved: boolean;
  };
}

// 根据索引定义可能有的TabPanel内容
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 选项卡面板组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`rehab-tabpanel-${index}`}
      aria-labelledby={`rehab-tab-${index}`}
      {...other}
      style={{ paddingTop: '20px' }}
    >
      {value === index && <Box>{children}</Box>}
    </div>
  );
}

const RehabPlanForm: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { id } = useParams<{ id: string }>();
  
  const isEditMode = !!id;
  
  // 选项卡状态
  const [tabValue, setTabValue] = useState(0);
  
  // 生成计划的步骤状态
  const [activeStep, setActiveStep] = useState(0);
  
  // 患者信息表单状态
  const [patientInfo, setPatientInfo] = useState<PatientInfo>({
    patient_id: '',
    patient_name: '',
    condition: '',
    goal: ''
  });
  
  // 生成的计划状态
  const [generatedPlan, setGeneratedPlan] = useState<GeneratedPlan | null>(null);
  
  // 修改后的计划状态
  const [modifiedPlan, setModifiedPlan] = useState<GeneratedPlan | null>(null);
  
  // 加载状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 运动展开状态
  const [expandedExercise, setExpandedExercise] = useState<number | null>(null);
  
  // 修改确认对话框状态
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);
  
  // 表单切换处理
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 患者信息表单变更处理
  const handlePatientInfoChange = (e: React.ChangeEvent<HTMLInputElement | { name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    setPatientInfo(prev => ({
      ...prev,
      [name as string]: value,
    }));
  };
  
  // 生成计划步骤前进
  const handleNext = () => {
    setActiveStep((prevStep) => prevStep + 1);
  };
  
  // 生成计划步骤后退
  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
  };
  
  // 生成康复计划
  const handleGeneratePlan = async () => {
    // 验证必填字段
    const requiredFields = ['patient_id', 'patient_name', 'condition', 'goal'];
    for (const field of requiredFields) {
      if (!patientInfo[field as keyof PatientInfo]) {
        setError(`请填写${field}字段`);
        return;
      }
    }
    
    setLoading(true);
    setError(null);
    
    try {
      // 调用后端API生成计划
      const response = await axios.post(
        `${BASE_URL}/api/rehabilitation/plans/generate`,
        patientInfo
      );
      
      setGeneratedPlan(response.data);
      setModifiedPlan(response.data);
      handleNext();
    } catch (err: any) {
      setError(err.response?.data?.detail || '生成康复计划失败');
    } finally {
      setLoading(false);
    }
  };
  
  // 运动项展开/折叠处理
  const handleToggleExercise = (index: number) => {
    setExpandedExercise(expandedExercise === index ? null : index);
  };
  
  // 修改计划内容
  const handleModifyPlan = (field: string, value: any) => {
    if (!modifiedPlan) return;
    
    setModifiedPlan(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        [field]: value
      };
    });
  };
  
  // 修改运动内容
  const handleModifyExercise = (index: number, field: string, value: any) => {
    if (!modifiedPlan) return;
    
    setModifiedPlan(prev => {
      if (!prev) return prev;
      
      const newExercises = [...prev.exercises];
      newExercises[index] = {
        ...newExercises[index],
        [field]: value
      };
      
      return {
        ...prev,
        exercises: newExercises
      };
    });
  };
  
  // 确认修改对话框
  const handleOpenConfirmDialog = () => {
    setConfirmDialogOpen(true);
  };
  
  // 关闭确认对话框
  const handleCloseConfirmDialog = () => {
    setConfirmDialogOpen(false);
  };
  
  // 确认并保存计划
  const handleConfirmPlan = async () => {
    if (!modifiedPlan || !modifiedPlan._id) return;
    
    setLoading(true);
    setError(null);
    
    try {
      // 计算修改内容
      const modifications = {};
      
      if (modifiedPlan !== generatedPlan) {
        Object.assign(modifications, modifiedPlan);
      }
      
      // 调用后端API确认计划
      const response = await axios.post(
        `${BASE_URL}/api/rehabilitation/plans/${modifiedPlan._id}/approve`,
        { modifications }
      );
      
      // 导航到计划详情页面
      navigate(`/rehab-plans/${modifiedPlan._id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || '确认康复计划失败');
    } finally {
      setLoading(false);
      handleCloseConfirmDialog();
    }
  };
  
  // 手动创建计划模式表单状态
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    patientName: '',
    condition: '',
    duration: '30', // Default duration in days
    status: 'active',
  });
  
  // 手动模式表单变更处理
  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | { name?: string; value: unknown }>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name as string]: value,
    }));
  };
  
  // 手动创建计划提交
  const handleManualSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // 转换值类型
    const planData = {
      ...formData,
      duration: parseInt(formData.duration, 10),
    };
    
    if (isEditMode) {
      // 更新现有计划
      dispatch(updateRehabPlan({ id: id!, planData }))
        .unwrap()
        .then(() => {
          navigate(`/rehab-plans/${id}`);
        })
        .catch(err => {
          setError(err.message || '更新康复计划失败');
        });
    } else {
      // 创建新计划
      dispatch(createRehabPlan(planData))
        .unwrap()
        .then((response) => {
          navigate(`/rehab-plans/${response._id}`);
        })
        .catch(err => {
          setError(err.message || '创建康复计划失败');
        });
    }
  };
  
  // 编辑模式下加载计划数据
  useEffect(() => {
    if (isEditMode && id) {
      dispatch(fetchRehabPlanById(id))
        .unwrap()
        .then((plan) => {
          setFormData({
            title: plan.name || '',
            description: plan.description || '',
            patientName: plan.patient_name || '',
            condition: plan.condition || '',
            duration: String(plan.duration_days || 30),
            status: plan.status || 'active',
          });
        })
        .catch(err => {
          setError(err.message || '加载康复计划失败');
        });
    }
  }, [dispatch, id, isEditMode]);
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" alignItems="center" mb={4}>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(-1)}
          sx={{ mr: 2 }}
        >
          返回
        </Button>
        <Typography variant="h4" component="h1">
          {isEditMode ? '编辑康复计划' : '创建康复计划'}
        </Typography>
      </Box>
      
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      
      <Paper sx={{ p: 4 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          sx={{ mb: 2 }}
        >
          <Tab 
            icon={<AIIcon />} 
            label="AI生成" 
            iconPosition="start"
          />
          <Tab 
            icon={<EditIcon />} 
            label="手动创建" 
            iconPosition="start"
          />
        </Tabs>
        
        <TabPanel value={tabValue} index={0}>
          {/* AI生成模式 */}
          <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
            <Step>
              <StepLabel>填写患者信息</StepLabel>
            </Step>
            <Step>
              <StepLabel>AI生成计划</StepLabel>
            </Step>
            <Step>
              <StepLabel>审核与确认</StepLabel>
            </Step>
          </Stepper>
          
          {activeStep === 0 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                请提供患者信息
              </Typography>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <TextField
                    required
                    fullWidth
                    id="patient_id"
                    name="patient_id"
                    label="患者ID"
                    value={patientInfo.patient_id}
                    onChange={handlePatientInfoChange}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    required
                    fullWidth
                    id="patient_name"
                    name="patient_name"
                    label="患者姓名"
                    value={patientInfo.patient_name}
                    onChange={handlePatientInfoChange}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    required
                    fullWidth
                    id="condition"
                    name="condition"
                    label="康复需求/诊断"
                    helperText="例如：颈椎病、腰椎间盘突出、肩周炎等"
                    value={patientInfo.condition}
                    onChange={handlePatientInfoChange}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    required
                    fullWidth
                    id="goal"
                    name="goal"
                    label="康复目标"
                    multiline
                    rows={2}
                    helperText="例如：缓解疼痛、增加关节活动度、提高生活质量等"
                    value={patientInfo.goal}
                    onChange={handlePatientInfoChange}
                  />
                </Grid>
              </Grid>
              <Box display="flex" justifyContent="flex-end" mt={3}>
                <Button
                  variant="contained"
                  onClick={handleGeneratePlan}
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={20} /> : <AIIcon />}
                >
                  生成康复计划
                </Button>
              </Box>
            </Box>
          )}
          
          {activeStep === 1 && generatedPlan && (
            <Box>
              <Typography variant="h6" gutterBottom>
                AI已生成康复计划
              </Typography>
              <Alert severity="info" sx={{ mb: 3 }}>
                请查看以下由AI生成的康复计划。您可以继续前进审核并修改，或返回修改患者信息。
              </Alert>
              
              <Card sx={{ mb: 3 }}>
                <CardContent>
                  <Typography variant="h6">{generatedPlan.name}</Typography>
                  <Typography variant="body2" color="textSecondary" paragraph>
                    {generatedPlan.description}
                  </Typography>
                  
                  <Grid container spacing={2} sx={{ mt: 1 }}>
                    <Grid item xs={12} md={4}>
                      <Typography variant="body2">
                        <strong>患者:</strong> {generatedPlan.patient_name}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="body2">
                        <strong>康复需求:</strong> {generatedPlan.condition}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="body2">
                        <strong>频率:</strong> {generatedPlan.frequency}
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <Typography variant="body2">
                        <strong>康复周期:</strong> {generatedPlan.duration_weeks} 周
                      </Typography>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
              
              <Typography variant="h6" gutterBottom>
                推荐运动 ({generatedPlan.exercises.length})
              </Typography>
              {generatedPlan.exercises.map((exercise, index) => (
                <Card key={index} sx={{ mb: 2 }}>
                  <CardContent sx={{ pb: 1 }}>
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography variant="subtitle1">
                        {exercise.name}
                      </Typography>
                      <IconButton onClick={() => handleToggleExercise(index)}>
                        {expandedExercise === index ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                      </IconButton>
                    </Box>
                    
                    <Typography variant="body2" color="textSecondary">
                      {exercise.description}
                    </Typography>
                    
                    <Box display="flex" flexWrap="wrap" mt={1}>
                      <Typography variant="body2" sx={{ mr: 2 }}>
                        <strong>部位:</strong> {exercise.body_part}
                      </Typography>
                      <Typography variant="body2" sx={{ mr: 2 }}>
                        <strong>难度:</strong> {exercise.difficulty}
                      </Typography>
                      <Typography variant="body2" sx={{ mr: 2 }}>
                        <strong>时间:</strong> {exercise.duration_minutes}分钟
                      </Typography>
                      <Typography variant="body2">
                        <strong>组数/次数:</strong> {exercise.sets}组 x {exercise.repetitions}次
                      </Typography>
                    </Box>
                    
                    <Collapse in={expandedExercise === index}>
                      <Box mt={2}>
                        <Typography variant="subtitle2" gutterBottom>
                          执行指南:
                        </Typography>
                        <List dense>
                          {exercise.instructions.map((step, i) => (
                            <ListItem key={i} sx={{ py: 0.5 }}>
                              <ListItemText primary={`${i + 1}. ${step}`} />
                            </ListItem>
                          ))}
                        </List>
                        
                        {exercise.contraindications.length > 0 && (
                          <>
                            <Typography variant="subtitle2" gutterBottom sx={{ mt: 1 }}>
                              禁忌症:
                            </Typography>
                            <List dense>
                              {exercise.contraindications.map((item, i) => (
                                <ListItem key={i} sx={{ py: 0.5 }}>
                                  <ListItemText primary={`• ${item}`} />
                                </ListItem>
                              ))}
                            </List>
                          </>
                        )}
                        
                        {exercise.benefits.length > 0 && (
                          <>
                            <Typography variant="subtitle2" gutterBottom sx={{ mt: 1 }}>
                              益处:
                            </Typography>
                            <List dense>
                              {exercise.benefits.map((item, i) => (
                                <ListItem key={i} sx={{ py: 0.5 }}>
                                  <ListItemText primary={`• ${item}`} />
                                </ListItem>
                              ))}
                            </List>
                          </>
                        )}
                      </Box>
                    </Collapse>
                  </CardContent>
                </Card>
              ))}
              
              {generatedPlan.notes && (
                <Box mt={3}>
                  <Typography variant="h6" gutterBottom>
                    注意事项
                  </Typography>
                  <Alert severity="info">
                    {generatedPlan.notes}
                  </Alert>
                </Box>
              )}
              
              <Box display="flex" justifyContent="space-between" mt={4}>
                <Button
                  onClick={handleBack}
                  disabled={loading}
                >
                  返回修改
                </Button>
                <Button
                  variant="contained"
                  onClick={handleNext}
                  disabled={loading}
                >
                  继续审核
                </Button>
              </Box>
            </Box>
          )}
          
          {activeStep === 2 && modifiedPlan && (
            <Box>
              <Typography variant="h6" gutterBottom>
                审核与修改
              </Typography>
              <Alert severity="info" sx={{ mb: 3 }}>
                请审核并修改计划内容，确认无误后保存。
              </Alert>
              
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="计划名称"
                    value={modifiedPlan.name}
                    onChange={(e) => handleModifyPlan('name', e.target.value)}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="计划描述"
                    multiline
                    rows={3}
                    value={modifiedPlan.description}
                    onChange={(e) => handleModifyPlan('description', e.target.value)}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="康复周期(周)"
                    type="number"
                    value={modifiedPlan.duration_weeks}
                    onChange={(e) => handleModifyPlan('duration_weeks', parseInt(e.target.value))}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="频率"
                    value={modifiedPlan.frequency}
                    onChange={(e) => handleModifyPlan('frequency', e.target.value)}
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="注意事项"
                    multiline
                    rows={2}
                    value={modifiedPlan.notes}
                    onChange={(e) => handleModifyPlan('notes', e.target.value)}
                  />
                </Grid>
              </Grid>
              
              <Typography variant="h6" gutterBottom sx={{ mt: 4 }}>
                运动项目
              </Typography>
              {modifiedPlan.exercises.map((exercise, index) => (
                <Card key={index} sx={{ mb: 2 }}>
                  <CardContent>
                    <Grid container spacing={2}>
                      <Grid item xs={12}>
                        <TextField
                          fullWidth
                          label="运动名称"
                          value={exercise.name}
                          onChange={(e) => handleModifyExercise(index, 'name', e.target.value)}
                        />
                      </Grid>
                      <Grid item xs={12}>
                        <TextField
                          fullWidth
                          label="描述"
                          multiline
                          rows={2}
                          value={exercise.description}
                          onChange={(e) => handleModifyExercise(index, 'description', e.target.value)}
                        />
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <TextField
                          fullWidth
                          label="身体部位"
                          value={exercise.body_part}
                          onChange={(e) => handleModifyExercise(index, 'body_part', e.target.value)}
                        />
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <FormControl fullWidth>
                          <InputLabel>难度</InputLabel>
                          <Select
                            value={exercise.difficulty}
                            label="难度"
                            onChange={(e) => handleModifyExercise(index, 'difficulty', e.target.value)}
                          >
                            <MenuItem value="简单">简单</MenuItem>
                            <MenuItem value="中等">中等</MenuItem>
                            <MenuItem value="困难">困难</MenuItem>
                          </Select>
                        </FormControl>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <TextField
                          fullWidth
                          label="持续时间(分钟)"
                          type="number"
                          value={exercise.duration_minutes}
                          onChange={(e) => handleModifyExercise(index, 'duration_minutes', parseInt(e.target.value))}
                        />
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <TextField
                          fullWidth
                          label="组数"
                          type="number"
                          value={exercise.sets}
                          onChange={(e) => handleModifyExercise(index, 'sets', parseInt(e.target.value))}
                        />
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <TextField
                          fullWidth
                          label="次数"
                          type="number"
                          value={exercise.repetitions}
                          onChange={(e) => handleModifyExercise(index, 'repetitions', parseInt(e.target.value))}
                        />
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              ))}
              
              <Box display="flex" justifyContent="space-between" mt={4}>
                <Button
                  onClick={handleBack}
                  disabled={loading}
                >
                  返回查看
                </Button>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleOpenConfirmDialog}
                  disabled={loading}
                  startIcon={<CheckIcon />}
                >
                  确认保存
                </Button>
              </Box>
              
              {/* 确认对话框 */}
              <Dialog
                open={confirmDialogOpen}
                onClose={handleCloseConfirmDialog}
              >
                <DialogTitle>确认保存</DialogTitle>
                <DialogContent>
                  <Typography>
                    您确定要保存这个康复计划吗？保存后将创建正式的康复计划，并可分配给患者。
                  </Typography>
                </DialogContent>
                <DialogActions>
                  <Button onClick={handleCloseConfirmDialog}>
                    取消
                  </Button>
                  <Button 
                    variant="contained" 
                    color="primary"
                    onClick={handleConfirmPlan}
                    disabled={loading}
                  >
                    {loading ? <CircularProgress size={24} /> : '确认保存'}
                  </Button>
                </DialogActions>
              </Dialog>
            </Box>
          )}
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          {/* 手动创建模式 */}
          <Box component="form" onSubmit={handleManualSubmit} noValidate>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <TextField
                  required
                  fullWidth
                  id="title"
                  name="title"
                  label="标题"
                  value={formData.title}
                  onChange={handleFormChange}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  id="description"
                  name="description"
                  label="描述"
                  multiline
                  rows={4}
                  value={formData.description}
                  onChange={handleFormChange}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  required
                  fullWidth
                  id="patientName"
                  name="patientName"
                  label="患者姓名"
                  value={formData.patientName}
                  onChange={handleFormChange}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  required
                  fullWidth
                  id="condition"
                  name="condition"
                  label="病症/康复需求"
                  value={formData.condition}
                  onChange={handleFormChange}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <TextField
                  required
                  fullWidth
                  id="duration"
                  name="duration"
                  label="计划持续时间（天）"
                  type="number"
                  value={formData.duration}
                  onChange={handleFormChange}
                  inputProps={{ min: 1 }}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel id="status-label">状态</InputLabel>
                  <Select
                    labelId="status-label"
                    id="status"
                    name="status"
                    value={formData.status}
                    label="状态"
                    onChange={handleFormChange}
                  >
                    <MenuItem value="active">活跃</MenuItem>
                    <MenuItem value="completed">已完成</MenuItem>
                    <MenuItem value="paused">已暂停</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} sx={{ mt: 2 }}>
                <Box display="flex" justifyContent="flex-end">
                  <Button
                    variant="contained"
                    color="primary"
                    type="submit"
                    startIcon={<SaveIcon />}
                    sx={{ mt: 2 }}
                  >
                    {isEditMode ? '保存修改' : '创建计划'}
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </TabPanel>
      </Paper>
    </Container>
  );
};

export default RehabPlanForm; 