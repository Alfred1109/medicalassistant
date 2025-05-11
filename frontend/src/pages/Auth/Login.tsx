import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  InputLabel,
  TextField,
  Typography,
  Alert,
  Paper,
} from '@mui/material';
import InputAdornment from '@mui/material/InputAdornment';
import OutlinedInput from '@mui/material/OutlinedInput';

import {
  Visibility,
  LockOutlined as LockIcon,
  Person as PersonIcon,
} from '@mui/icons-material';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import InfoIcon from '@mui/icons-material/Info';

import { AppDispatch, RootState } from '../../store';
import { 
  login, clearAuthError, User, 
  mockDoctorLogin, mockHealthManagerLogin, mockAdminLogin, mockPatientLogin 
} from '../../store/slices/authSlice';

// 管理员账号信息
const ADMIN_CREDENTIALS = {
  email: 'admin@example.com',
  password: 'Admin123!', // 使用后端创建时的默认密码
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

// 添加防抖函数
const debounce = (func: Function, wait: number) => {
  let timeout: ReturnType<typeof setTimeout>;
  return function executedFunction(...args: any[]) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
};

const Login: React.FC = () => {
  const navigate = useNavigate();
  const dispatch = useDispatch<AppDispatch>();
  const { loading, loginLoading, error, user, token } = useSelector((state: RootState) => state.auth);
  
  // 添加上一次用户状态的引用，用于比较
  const prevUserRef = useRef<User | null>(null);
  const prevTokenRef = useRef<string | null>(null);

  // 使用loginLoading状态，如果不存在则回退到通用loading状态
  const isLoading = loginLoading !== undefined ? loginLoading : loading;

  const [formData, setFormData] = useState({
    email: ADMIN_CREDENTIALS.email, // Default to admin email
    password: ADMIN_CREDENTIALS.password, // Default to admin password
  });
  const [showPassword, setShowPassword] = useState(false);
  // 定义FormErrors接口
  interface FormErrors {
    email?: string;
    password?: string;
    server?: string;
  }
  const [formErrors, setFormErrors] = useState({} as FormErrors);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
    
    // 清除相关字段的错误
    if (formErrors[name as keyof FormErrors]) {
      setFormErrors((prev: FormErrors) => ({ ...prev, [name]: undefined }));
    }
    
    // 清除Redux错误状态
    if (error) dispatch(clearAuthError());
  };

  // 验证表单
  const validateForm = (): boolean => {
    const errors: FormErrors = {};
    
    // 验证邮箱
    if (!formData.email) {
      errors.email = '请输入邮箱地址';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      errors.email = '请输入有效的邮箱地址';
    }
    
    // 验证密码
    if (!formData.password) {
      errors.password = '请输入密码';
    } else if (formData.password.length < 6) {
      errors.password = '密码长度至少为6个字符';
    }
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // 表单验证
    if (!validateForm()) {
      return;
    }
    
    try {
      console.log('Login.tsx: 开始登录，用户邮箱:', formData.email);
      // 尝试登录，等待完成或错误
      // .unwrap() 会在成功时返回 action.payload，失败时抛出错误
      const result = await dispatch(login(formData)).unwrap(); 
      
      // 如果登录成功 (真实登录，非模拟登录的 _handled case)
      // 实际上，跳转现在由上面的 useEffect 处理
      // 所以这里只需要知道操作已完成即可
      if (result && result._handled) {
        console.log('Login.tsx: 模拟登录流程已由thunk处理.');
      } else if (result && result.user) {
        console.log('Login.tsx: 真实登录成功，等待useEffect跳转.', result);
      } else {
        console.log('Login.tsx: 登录操作完成，但未识别明确的成功结果用于立即跳转:', result);
      }

    } catch (err: any) {
      console.error('Login.tsx: 登录 dispatch/unwrap 失败:', err);
      // 错误状态 (err) 会被 authSlice 的 rejected case 更新到 Redux store 的 error 字段
      // UI 会通过 useSelector((state) => state.auth.error) 来显示错误
      // 这里不需要再次 setFormErrors，除非是特定于此组件的、非API相关的表单错误
      // 例如，如果 err 是我们自定义的超时并且没有设置到Redux的error中，可以在这里处理
      // 但我们之前的逻辑是把超时信息也 rejectWithValue，所以它会进入 Redux error
    }
  };

  // 根据用户角色进行跳转，使用useCallback避免无限重渲染
  const redirectBasedOnRole = useCallback((role: string) => {
    let targetPath = '/app/dashboard'; // 默认路径
    
    switch (role) {
      case 'admin':
        targetPath = '/app/admin/doctors';
        break;
      case 'doctor':
        targetPath = '/app/doctor';
        break;
      case 'health_manager':
        targetPath = '/app/health-manager';
        break;
      case 'patient':
        targetPath = '/app/patient/main-dashboard';
        break;
    }
    
    // 避免重复导航到相同路径
    if (window.location.pathname !== targetPath) {
      console.log(`Login.tsx: 跳转到 ${targetPath}`);
      navigate(targetPath, { replace: true }); // 使用replace模式避免导航历史堆积
    } else {
      console.log('Login.tsx: 已在目标路径，不进行跳转');
    }
  }, [navigate]);

  // 使用防抖处理的redirect函数
  const debouncedRedirect = useCallback(
    debounce((role: string) => redirectBasedOnRole(role), 300),
    [redirectBasedOnRole]
  );

  // Effect to handle redirection after login (real or mock)
  useEffect(() => {
    // 只有当用户或令牌状态实际变化时才执行重定向
    const userChanged = user !== prevUserRef.current;
    const tokenChanged = token !== prevTokenRef.current;
    
    if (user && token && (userChanged || tokenChanged)) {
      console.log('Login.tsx: User/token state changed, attempting to redirect.', user);
      // 更新引用值
      prevUserRef.current = user;
      prevTokenRef.current = token;
      
      // 使用防抖函数来避免短时间内多次导航
      debouncedRedirect(user.role);
    }
  }, [user, token, debouncedRedirect]);

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

  // 模拟登录处理函数
  const handleMockLogin = async (type: 'admin' | 'doctor' | 'health_manager' | 'patient') => {
    try {
      // 清除之前的错误
      if (error) dispatch(clearAuthError());
      
      // 根据类型调用不同的模拟登录函数
      switch (type) {
        case 'admin':
          await dispatch(mockAdminLogin()).unwrap();
          break;
        case 'doctor':
          await dispatch(mockDoctorLogin()).unwrap();
          break;
        case 'health_manager':
          await dispatch(mockHealthManagerLogin()).unwrap();
          break;
        case 'patient':
          await dispatch(mockPatientLogin()).unwrap();
          break;
      }
      
      console.log(`Login.tsx: 模拟${type}登录成功`);
    } catch (err) {
      console.error(`Login.tsx: 模拟${type}登录失败:`, err);
    }
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

      {/* 快速登录按钮组 */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" gutterBottom>
          快速登录:
        </Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          <Button 
            variant="contained" 
            color="primary" 
            size="small"
            onClick={() => handleMockLogin('admin')}
            disabled={isLoading}
          >
            管理员登录
          </Button>
          <Button 
            variant="contained" 
            color="secondary" 
            size="small"
            onClick={() => handleMockLogin('doctor')}
            disabled={isLoading}
          >
            医生登录
          </Button>
          <Button 
            variant="contained" 
            color="warning" 
            size="small"
            onClick={() => handleMockLogin('health_manager')}
            disabled={isLoading}
          >
            健康管理师登录
          </Button>
          <Button 
            variant="contained" 
            color="success" 
            size="small"
            onClick={() => handleMockLogin('patient')}
            disabled={isLoading}
          >
            患者登录
          </Button>
        </Box>
      </Box>

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
            error={!!formErrors.email}
            helperText={formErrors.email}
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
          <FormControl variant="outlined" fullWidth required error={!!formErrors.password}>
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
            {formErrors.password && (
              <Typography variant="caption" color="error" sx={{ mt: 0.5, ml: 2 }}>
                {formErrors.password}
              </Typography>
            )}
          </FormControl>
        </Grid>
      </Grid>

      <Box mt={3}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {formErrors.server && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {formErrors.server}
          </Alert>
        )}
        <Button
          type="submit"
          fullWidth
          variant="contained"
          size="large"
          disabled={isLoading}
          sx={{ mb: 2 }}
          onClick={handleSubmit}
        >
          {isLoading ? (
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <CircularProgress size={24} sx={{ mr: 1, color: 'grey.400' }} />
              <span>登录中...</span>
            </Box>
          ) : (
            '登录'
          )}
        </Button>
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
    </Box>
  );
};

export default Login; 