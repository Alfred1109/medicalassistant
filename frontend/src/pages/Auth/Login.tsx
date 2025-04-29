import React, { useState } from 'react';
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
  PersonOutlined as PersonIcon,
  Info as InfoIcon,
} from '@mui/icons-material';

import { AppDispatch, RootState } from '../../store';
import { login, clearAuthError, mockAdminLogin, mockDoctorLogin, mockHealthManagerLogin, mockPatientLogin } from '../../store/slices/authSlice';

// 默认用户信息
const DEFAULT_CREDENTIALS = {
  email: 'demo@example.com',
  password: 'password123',
};

const Login: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { loading, error } = useSelector((state: RootState) => state.auth);

  const [formData, setFormData] = useState(DEFAULT_CREDENTIALS);
  const [showPassword, setShowPassword] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
    if (error) dispatch(clearAuthError());
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await dispatch(login(formData)).unwrap();
      // 根据用户角色跳转到相应的页面
      redirectBasedOnRole(result.user.role);
    } catch (err) {
      // Error is handled by the reducer
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
        navigate('/app/patient');
        break;
      default:
        // 默认跳转到通用仪表板
        navigate('/app/dashboard');
    }
  };

  const handleClickShowPassword = () => {
    setShowPassword(!showPassword);
  };

  // 填充默认账号
  const fillDefaultCredentials = () => {
    setFormData(DEFAULT_CREDENTIALS);
  };

  const handleMockAdminLogin = () => {
    dispatch(mockAdminLogin());
    navigate('/app/admin');
  };
  
  const handleMockDoctorLogin = () => {
    dispatch(mockDoctorLogin());
    navigate('/app/doctor');
  };
  
  const handleMockHealthManagerLogin = () => {
    dispatch(mockHealthManagerLogin());
    navigate('/app/health-manager');
  };

  const handleMockPatientLogin = () => {
    dispatch(mockPatientLogin());
    navigate('/app/patient');
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

      {/* 默认账号提示 */}
      <Paper 
        variant="outlined" 
        sx={{ 
          p: 2, 
          mb: 3, 
          backgroundColor: '#f5f8ff',
          borderColor: '#c2d6ff'
        }}
      >
        <Box display="flex" alignItems="center">
          <InfoIcon color="primary" sx={{ mr: 1 }} />
          <Box>
            <Typography variant="body2" fontWeight="medium" color="primary.main">
              测试账号信息
            </Typography>
            <Typography variant="body2" color="text.secondary">
              邮箱: {DEFAULT_CREDENTIALS.email} <br />
              密码: {DEFAULT_CREDENTIALS.password}
            </Typography>
          </Box>
          <Button 
            size="small" 
            variant="outlined" 
            sx={{ ml: 'auto' }}
            onClick={fillDefaultCredentials}
          >
            自动填充
          </Button>
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

      <Button
        type="submit"
        fullWidth
        variant="contained"
        disabled={loading}
        sx={{ mt: 3, mb: 2, py: 1.2 }}
      >
        {loading ? <CircularProgress size={24} /> : '登录'}
      </Button>

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

      <Box mt={3}>
        <Divider>
          <Typography variant="body2" color="text.secondary">
            快速模拟登录
          </Typography>
        </Divider>
        <Box mt={2} display="flex" flexDirection="column" gap={1}>
          <Button 
            variant="outlined" 
            color="primary" 
            fullWidth
            onClick={handleMockAdminLogin}
          >
            以管理员身份登录
          </Button>
          <Button 
            variant="outlined" 
            color="secondary" 
            fullWidth
            onClick={handleMockDoctorLogin}
          >
            以医生身份登录
          </Button>
          <Button 
            variant="outlined" 
            color="info" 
            fullWidth
            onClick={handleMockHealthManagerLogin}
          >
            以健康管理师身份登录
          </Button>
          <Button 
            variant="outlined" 
            color="success" 
            fullWidth
            onClick={handleMockPatientLogin}
          >
            以患者身份登录
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default Login; 