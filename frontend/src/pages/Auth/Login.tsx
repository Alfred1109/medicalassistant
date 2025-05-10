import React, { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link, useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  OutlinedInput,
  TextField,
  Typography,
  Alert,
  Paper,
  Tooltip,
} from '@mui/material';
import {
  Visibility,
  VisibilityOff,
  LockOutlined as LockIcon,
  Person as PersonIcon,
  Info as InfoIcon,
} from '@mui/icons-material';

import { AppDispatch, RootState } from '../../store';
import { login, clearAuthError, mockAdminLogin, mockDoctorLogin, mockHealthManagerLogin, mockPatientLogin } from '../../store/slices/authSlice';

// 管理员账号信息
const ADMIN_CREDENTIALS = {
  email: 'admin@example.com',
  password: 'Admin123!',
};

// 医生账号信息
const DOCTOR_CREDENTIALS = {
  email: 'doctor@example.com',
  password: 'Doctor123!',
};

// 健康管理师账号信息
const HEALTH_MANAGER_CREDENTIALS = {
  email: 'liujk@example.com',
  password: 'Manager123!',
};

// 患者账号信息
const PATIENT_CREDENTIALS = {
  email: 'zhangsan@example.com',
  password: 'Patient123!',
};

const Login: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { loading, error } = useSelector((state: RootState) => state.auth);

  const [formData, setFormData] = useState({
    email: ADMIN_CREDENTIALS.email, // Default to admin email
    password: ADMIN_CREDENTIALS.password, // Default to admin password
  });
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
    if (error) dispatch(clearAuthError());
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      console.log('开始登录，用户邮箱:', formData.email);
      
      // 在开发环境下，当使用默认管理员账号时，可以选择绕过实际登录
      if (process.env.NODE_ENV === 'development' && 
          formData.email === ADMIN_CREDENTIALS.email && 
          formData.password === ADMIN_CREDENTIALS.password) {
        console.log('开发环境使用默认管理员账号，使用模拟登录');
        dispatch(mockAdminLogin());
        navigate('/app/admin');
        return;
      }
      
      const result = await dispatch(login(formData)).unwrap();
      console.log('登录成功，用户信息:', result);
      // 根据用户角色跳转到相应的页面
      redirectBasedOnRole(result.user.role);
    } catch (err: any) {
      console.error('登录失败，错误:', err);
      console.error('详细错误堆栈:', new Error().stack);
      
      // 显示更详细的错误信息
      if (err?.response?.status === 0) {
        dispatch({ 
          type: 'auth/loginFailed', 
          payload: '无法连接到服务器，请检查网络连接' 
        });
      }
      
      // 如果在开发环境中登录失败，使用模拟登录
      if (process.env.NODE_ENV === 'development') {
        console.log('开发环境下使用模拟登录');
        // 根据尝试登录的用户名选择不同的模拟登录
        if (formData.email.includes('doctor')) {
          dispatch(mockDoctorLogin());
          navigate('/app/doctor');
        } else if (formData.email.includes('health')) {
          dispatch(mockHealthManagerLogin());
          navigate('/app/health-manager');
        } else if (formData.email.includes('patient')) {
          dispatch(mockPatientLogin());
          navigate('/app/patient/main-dashboard');
        } else {
          dispatch(mockAdminLogin());
          navigate('/app/admin');
        }
      }
    }
  };

  // 根据用户角色进行跳转
  const redirectBasedOnRole = (role: string) => {
    switch (role) {
      case 'admin':
        navigate('/app/admin');
        break;
      case 'doctor':
        navigate('/app/doctor');
        break;
      case 'health_manager':
        navigate('/app/health-manager');
        break;
      case 'patient':
        navigate('/app/patient/main-dashboard');
        break;
      default:
        // 默认跳转到通用仪表板
        navigate('/app/dashboard');
    }
  };

  const handleClickShowPassword = () => {
    setShowPassword(!showPassword);
  };

  // 填充管理员账号
  const fillAdminCredentials = () => {
    setFormData(ADMIN_CREDENTIALS);
    if (error) dispatch(clearAuthError());
  };

  // 填充医生账号
  const fillDoctorCredentials = () => {
    setFormData(DOCTOR_CREDENTIALS);
    if (error) dispatch(clearAuthError());
  };

  // 填充健康管理师账号
  const fillHealthManagerCredentials = () => {
    setFormData(HEALTH_MANAGER_CREDENTIALS);
    if (error) dispatch(clearAuthError());
  };

  // 填充患者账号
  const fillPatientCredentials = () => {
    setFormData(PATIENT_CREDENTIALS);
    if (error) dispatch(clearAuthError());
  };

  // 添加自动登录功能
  useEffect(() => {
    // 检查URL参数中是否有autologin=admin
    const urlParams = new URLSearchParams(window.location.search);
    const autoLogin = urlParams.get('autologin');
    
    if (autoLogin === 'admin') {
      setFormData(ADMIN_CREDENTIALS);
      // 延迟500ms自动提交，确保表单状态已更新
      setTimeout(() => {
        dispatch(login(ADMIN_CREDENTIALS)).unwrap()
          .then(result => {
            redirectBasedOnRole(result.user.role);
          })
          .catch(err => {
            console.error('自动登录失败:', err);
            // 失败后使用模拟登录
            dispatch(mockAdminLogin());
            navigate('/app/admin');
          });
      }, 500);
    }
  }, []);

  // 添加一个应急方案，直接使用模拟登录
  const handleMockLogin = () => {
    dispatch(mockAdminLogin());
    navigate('/app/admin');
  };

  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      <Box sx={{ mb: 3, textAlign: 'center' }}>
        <Typography component="h1" variant="h5" fontWeight="medium" gutterBottom>
          登录
        </Typography>
        <Typography variant="body2" color="text.secondary">
          欢迎回来！请输入您的登录信息
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* 账号提示 */}
      <Paper 
        variant="outlined" 
        sx={{ 
          p: 2, 
          mb: 3, 
          backgroundColor: '#f5f8ff',
          borderColor: '#c2d6ff'
        }}
      >
        <Box display="flex" flexDirection="column" gap={1}>
          <Box display="flex" alignItems="center">
            <InfoIcon color="primary" sx={{ mr: 1 }} />
            <Typography variant="body2" fontWeight="medium" color="primary.main">
              演示账号
            </Typography>
          </Box>
          
          <Box sx={{ mt: 1 }}>
            <Typography variant="subtitle2" color="text.primary">
              管理员账号:
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
              邮箱: {ADMIN_CREDENTIALS.email} <br />
              密码: {ADMIN_CREDENTIALS.password}
            </Typography>
            <Button 
              size="small" 
              variant="outlined" 
              color="primary"
              sx={{ mt: 1 }}
              onClick={fillAdminCredentials}
            >
              使用此账号
            </Button>
          </Box>
          
          <Divider sx={{ my: 1 }} />
          
          <Box>
            <Typography variant="subtitle2" color="text.primary">
              医生账号:
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
              邮箱: {DOCTOR_CREDENTIALS.email} <br />
              密码: {DOCTOR_CREDENTIALS.password}
            </Typography>
            <Button 
              size="small" 
              variant="outlined" 
              color="secondary"
              sx={{ mt: 1 }}
              onClick={fillDoctorCredentials}
            >
              使用此账号
            </Button>
          </Box>

          <Divider sx={{ my: 1 }} />

          <Box>
            <Typography variant="subtitle2" color="text.primary">
              健康管理师账号:
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
              邮箱: {HEALTH_MANAGER_CREDENTIALS.email} <br />
              密码: {HEALTH_MANAGER_CREDENTIALS.password}
            </Typography>
            <Button 
              size="small" 
              variant="outlined" 
              color="warning"
              sx={{ mt: 1 }}
              onClick={fillHealthManagerCredentials}
            >
              使用此账号
            </Button>
          </Box>

          <Divider sx={{ my: 1 }} />

          <Box>
            <Typography variant="subtitle2" color="text.primary">
              患者账号:
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'break-all' }}>
              邮箱: {PATIENT_CREDENTIALS.email} <br />
              密码: {PATIENT_CREDENTIALS.password}
            </Typography>
            <Button 
              size="small" 
              variant="outlined" 
              color="success"
              sx={{ mt: 1 }}
              onClick={fillPatientCredentials}
            >
              使用此账号
            </Button>
          </Box>
        </Box>
      </Paper>

      <Grid container spacing={2}>
        <Grid item xs={12}>
          <TextField
            required
            fullWidth
            id="email"
            label="邮箱地址"
            name="email"
            autoComplete="email"
            autoFocus
            value={formData.email}
            onChange={handleChange}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <PersonIcon fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </Grid>
        <Grid item xs={12}>
          <FormControl variant="outlined" fullWidth required>
            <InputLabel htmlFor="password">密码</InputLabel>
            <OutlinedInput
              id="password"
              name="password"
              type={showPassword ? 'text' : 'password'}
              value={formData.password}
              onChange={handleChange}
              autoComplete="current-password"
              startAdornment={
                <InputAdornment position="start">
                  <LockIcon fontSize="small" />
                </InputAdornment>
              }
              endAdornment={
                <InputAdornment position="end">
                  <IconButton
                    aria-label="toggle password visibility"
                    onClick={handleClickShowPassword}
                    edge="end"
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              }
              label="密码"
            />
          </FormControl>
        </Grid>
      </Grid>

      <Box mt={3}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <Button
          fullWidth
          variant="contained"
          color="primary"
          type="submit"
          disabled={loading}
          startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <LockIcon />}
        >
          {loading ? '登录中...' : '登录'}
        </Button>

        {process.env.NODE_ENV === 'development' && (
          <Button
            fullWidth
            variant="outlined"
            color="secondary"
            onClick={handleMockLogin}
            sx={{ mt: 1 }}
          >
            开发环境应急登录
          </Button>
        )}
      </Box>

      <Divider sx={{ my: 2 }}>
        <Typography variant="body2" color="text.secondary">
          或者
        </Typography>
      </Divider>

      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="body2">
          还没有账号？{' '}
          <Link to="/auth/register" style={{ color: '#1976d2', fontWeight: 500 }}>
            注册
          </Link>
        </Typography>
      </Box>

      {/* 在开发环境或特定条件下显示紧急登录按钮 */}
      {(process.env.NODE_ENV === 'development' || window.location.hostname === 'localhost') && (
        <Box mt={3} p={2} sx={{ border: '1px dashed #ff9800', borderRadius: 1, bgcolor: '#fff8e1' }}>
          <Typography variant="subtitle2" color="warning.main" gutterBottom>
            开发环境紧急登录
          </Typography>
          <Grid container spacing={1}>
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="outlined"
                color="warning"
                size="small"
                onClick={() => {
                  dispatch(mockAdminLogin());
                  navigate('/app/admin');
                }}
              >
                管理员登录
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="outlined"
                color="warning"
                size="small"
                onClick={() => {
                  dispatch(mockDoctorLogin());
                  navigate('/app/doctor');
                }}
              >
                医生登录
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="outlined"
                color="warning"
                size="small"
                onClick={() => {
                  dispatch(mockHealthManagerLogin());
                  navigate('/app/health-manager');
                }}
              >
                健康管理师登录
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="outlined"
                color="warning"
                size="small"
                onClick={() => {
                  dispatch(mockPatientLogin());
                  navigate('/app/patient/main-dashboard');
                }}
              >
                患者登录
              </Button>
            </Grid>
          </Grid>
        </Box>
      )}
    </Box>
  );
};

export default Login; 