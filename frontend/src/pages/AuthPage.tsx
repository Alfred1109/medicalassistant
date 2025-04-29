import React, { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, Navigate } from 'react-router-dom';
import {
  Container,
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Divider,
  Tab,
  Tabs,
  Alert,
  CircularProgress,
  Avatar,
  Link,
  Grid,
  FormControl,
  InputLabel,
  OutlinedInput,
  InputAdornment,
  IconButton,
} from '@mui/material';
import {
  LockOutlined as LockOutlinedIcon,
  PersonAddOutlined as PersonAddOutlinedIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Person as PersonIcon,
  Email as EmailIcon,
  Lock as LockIcon
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../store';
import { login, register, clearAuthError, mockDoctorLogin, mockHealthManagerLogin, mockAdminLogin } from '../store/slices/authSlice';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel = (props: TabPanelProps) => {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`auth-tabpanel-${index}`}
      aria-labelledby={`auth-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
};

const AuthPage: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { user, loading, error, token } = useSelector((state: RootState) => state.auth);
  const [tabValue, setTabValue] = useState(0);
  
  // Login form state
  const [loginFormData, setLoginFormData] = useState({
    email: '',
    password: '',
  });
  
  // Register form state
  const [registerFormData, setRegisterFormData] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'patient',
  });
  
  // Form validation errors
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // If user is already logged in, redirect to dashboard
  if (user && token) {
    return <Navigate to="/" replace />;
  }

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    dispatch(clearAuthError());
    setValidationErrors({});
  };

  const handleLoginInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setLoginFormData({
      ...loginFormData,
      [name]: value,
    });
  };

  const handleRegisterInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setRegisterFormData({
      ...registerFormData,
      [name]: value,
    });
  };

  const validateLoginForm = () => {
    const errors: Record<string, string> = {};
    
    if (!loginFormData.email) {
      errors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(loginFormData.email)) {
      errors.email = 'Email is invalid';
    }
    
    if (!loginFormData.password) {
      errors.password = 'Password is required';
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateRegisterForm = () => {
    const errors: Record<string, string> = {};
    
    if (!registerFormData.name) {
      errors.name = 'Name is required';
    }
    
    if (!registerFormData.email) {
      errors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(registerFormData.email)) {
      errors.email = 'Email is invalid';
    }
    
    if (!registerFormData.password) {
      errors.password = 'Password is required';
    } else if (registerFormData.password.length < 6) {
      errors.password = 'Password must be at least 6 characters';
    }
    
    if (!registerFormData.confirmPassword) {
      errors.confirmPassword = 'Please confirm your password';
    } else if (registerFormData.password !== registerFormData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match';
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateLoginForm()) {
      return;
    }
    
    try {
      await dispatch(login(loginFormData)).unwrap();
      navigate('/dashboard');
    } catch (error) {
      // Error is handled in the slice and displayed to the user
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateRegisterForm()) {
      return;
    }
    
    try {
      await dispatch(register(registerFormData)).unwrap();
      navigate('/dashboard');
    } catch (error) {
      // Error is handled in the slice and displayed to the user
    }
  };

  const handleMockLogin = (role: 'doctor' | 'health_manager' | 'admin') => {
    if (role === 'doctor') {
      dispatch(mockDoctorLogin());
    } else if (role === 'health_manager') {
      dispatch(mockHealthManagerLogin());
    } else if (role === 'admin') {
      dispatch(mockAdminLogin());
    }
  };

  return (
    <Container maxWidth="sm">
      <Box
        sx={{
          mt: 8,
          mb: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Typography
          variant="h4"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 'bold', color: 'primary.main', mb: 4 }}
        >
          Medical Rehabilitation Assistant
        </Typography>
        
        <Paper
          elevation={3}
          sx={{
            width: '100%',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            variant="fullWidth"
            indicatorColor="primary"
            textColor="primary"
            aria-label="auth tabs"
          >
            <Tab 
              icon={<LockOutlinedIcon />}
              label="Login" 
              id="auth-tab-0"
              aria-controls="auth-tabpanel-0"
            />
            <Tab 
              icon={<PersonAddOutlinedIcon />}
              label="Register" 
              id="auth-tab-1"
              aria-controls="auth-tabpanel-1"
            />
          </Tabs>
          
          {error && (
            <Alert severity="error" sx={{ m: 2 }}>
              {error}
            </Alert>
          )}
          
          <Box sx={{ p: 3 }}>
            <TabPanel value={tabValue} index={0}>
              <Box
                component="form"
                onSubmit={handleLoginSubmit}
                noValidate
              >
                <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <Avatar sx={{ m: 1, bgcolor: 'primary.main' }}>
                    <LockOutlinedIcon />
                  </Avatar>
                  <Typography component="h1" variant="h5">
                    Sign in
                  </Typography>
                </Box>
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="email"
                  label="Email Address"
                  name="email"
                  autoComplete="email"
                  autoFocus
                  value={loginFormData.email}
                  onChange={handleLoginInputChange}
                  error={!!validationErrors.email}
                  helperText={validationErrors.email}
                />
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="password"
                  label="Password"
                  type="password"
                  id="password"
                  autoComplete="current-password"
                  value={loginFormData.password}
                  onChange={handleLoginInputChange}
                  error={!!validationErrors.password}
                  helperText={validationErrors.password}
                />
                
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  sx={{ mt: 3, mb: 2, py: 1.5 }}
                  disabled={loading}
                >
                  {loading ? <CircularProgress size={24} /> : 'Sign In'}
                </Button>
                
                <Box sx={{ mt: 2, textAlign: 'center' }}>
                  <Link href="#" variant="body2" onClick={() => alert('Password reset functionality coming soon')}>
                    Forgot password?
                  </Link>
                </Box>
              </Box>
            </TabPanel>
            
            <TabPanel value={tabValue} index={1}>
              <Box
                component="form"
                onSubmit={handleRegisterSubmit}
                noValidate
              >
                <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <Avatar sx={{ m: 1, bgcolor: 'secondary.main' }}>
                    <PersonAddOutlinedIcon />
                  </Avatar>
                  <Typography component="h1" variant="h5">
                    Create an Account
                  </Typography>
                </Box>
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="name"
                  label="Full Name"
                  name="name"
                  autoComplete="name"
                  autoFocus
                  value={registerFormData.name}
                  onChange={handleRegisterInputChange}
                  error={!!validationErrors.name}
                  helperText={validationErrors.name}
                />
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  id="register-email"
                  label="Email Address"
                  name="email"
                  autoComplete="email"
                  value={registerFormData.email}
                  onChange={handleRegisterInputChange}
                  error={!!validationErrors.email}
                  helperText={validationErrors.email}
                />
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="password"
                  label="Password"
                  type="password"
                  id="register-password"
                  autoComplete="new-password"
                  value={registerFormData.password}
                  onChange={handleRegisterInputChange}
                  error={!!validationErrors.password}
                  helperText={validationErrors.password}
                />
                
                <TextField
                  margin="normal"
                  required
                  fullWidth
                  name="confirmPassword"
                  label="Confirm Password"
                  type="password"
                  id="confirm-password"
                  value={registerFormData.confirmPassword}
                  onChange={handleRegisterInputChange}
                  error={!!validationErrors.confirmPassword}
                  helperText={validationErrors.confirmPassword}
                />
                
                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  color="secondary"
                  sx={{ mt: 3, mb: 2, py: 1.5 }}
                  disabled={loading}
                >
                  {loading ? <CircularProgress size={24} /> : 'Register'}
                </Button>
              </Box>
            </TabPanel>
          </Box>
        </Paper>
        
        <Box mt={5}>
          <Typography variant="body2" color="text.secondary" align="center">
            By signing in or creating an account, you agree to our Terms of Service and Privacy Policy.
          </Typography>
        </Box>

        <Divider sx={{ my: 3 }}>测试用登录</Divider>
        
        <Grid container spacing={2}>
          <Grid item xs={4}>
            <Button 
              fullWidth variant="outlined" 
              onClick={() => handleMockLogin('doctor')}
            >
              医生登录
            </Button>
          </Grid>
          <Grid item xs={4}>
            <Button 
              fullWidth variant="outlined" 
              onClick={() => handleMockLogin('health_manager')}
            >
              健康管理师
            </Button>
          </Grid>
          <Grid item xs={4}>
            <Button 
              fullWidth variant="outlined" 
              onClick={() => handleMockLogin('admin')}
            >
              管理员
            </Button>
          </Grid>
        </Grid>
      </Box>
    </Container>
  );
};

export default AuthPage; 