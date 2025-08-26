import React from 'react';
import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  Box,
  Button,
  Container,
  Grid,
  Paper,
  Typography,
  TextField,
  Avatar,
  Divider,
  CircularProgress,
  Snackbar,
  Alert,
  IconButton,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import {
  Save as SaveIcon,
  Edit as EditIcon,
  Key as KeyIcon,
  CloudUpload as CloudUploadIcon,
} from '@mui/icons-material';

// 导入store类型
import { RootState } from '../../store';

// 模拟用户数据 - 实际应用中应该从store或API获取
const mockUserData = {
  id: 'user-123',
  name: '张三',
  email: 'zhangsan@example.com',
  phone: '138****1234',
  avatar: '',
  createdAt: '2023-01-01T00:00:00Z',
  role: '医生',
  department: '康复科',
  bio: '拥有10年康复医学经验，专注于脑卒中后康复治疗。',
};

const Profile = () => {
  const dispatch = useDispatch();
  // const { user, loading, error } = useSelector((state: RootState) => state.auth);
  
  // 使用模拟数据替代store数据，实际应用中应该使用上面注释的代码
  const [user, setUser] = useState(mockUserData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // 编辑状态
  const [isEditing, setIsEditing] = useState(false);
  // 表单数据
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    phone: '',
    department: '',
    bio: '',
  });
  // 修改密码相关状态
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [passwordData, setPasswordData] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [passwordError, setPasswordError] = useState<string | null>(null);
  
  // 通知消息
  const [notification, setNotification] = useState({
    open: false,
    message: '',
    type: 'success' as 'success' | 'error' | 'info' | 'warning',
  });
  
  // 初始化表单数据
  useEffect(() => {
    if (user) {
      setFormData({
        name: user.name || '',
        email: user.email || '',
        phone: user.phone || '',
        department: user.department || '',
        bio: user.bio || '',
      });
    }
  }, [user]);
  
  // 处理表单字段变化
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };
  
  // 处理修改密码表单变化
  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setPasswordData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };
  
  // 处理表单提交
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    // 模拟API请求
    setTimeout(() => {
      // 在实际应用中，这里应该调用dispatch更新用户信息
      // dispatch(updateUserProfile(formData))
      
      setUser((prev) => ({
        ...prev,
        ...formData,
      }));
      
      setIsEditing(false);
      setLoading(false);
      setNotification({
        open: true,
        message: '个人资料已更新',
        type: 'success',
      });
    }, 1000);
  };
  
  // 处理密码修改
  const handlePasswordSubmit = () => {
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      setPasswordError('两次输入的新密码不匹配');
      return;
    }
    
    if (passwordData.newPassword.length < 8) {
      setPasswordError('新密码长度必须至少为8个字符');
      return;
    }
    
    setLoading(true);
    
    // 模拟API请求
    setTimeout(() => {
      // 在实际应用中，这里应该调用dispatch更新密码
      // dispatch(updatePassword(passwordData))
      
      setPasswordDialogOpen(false);
      setPasswordData({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
      setPasswordError(null);
      setLoading(false);
      setNotification({
        open: true,
        message: '密码已成功更新',
        type: 'success',
      });
    }, 1000);
  };
  
  // 处理头像上传
  const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // 检查文件类型
    if (!file.type.match('image.*')) {
      setNotification({
        open: true,
        message: '请选择图片文件',
        type: 'error',
      });
      return;
    }
    
    // 在实际应用中，这里应该调用API上传图片
    // 这里仅做演示，将图片转为DataURL显示
    const reader = new FileReader();
    reader.onload = (e) => {
      if (e.target?.result) {
        setUser((prev) => ({
          ...prev,
          avatar: e.target?.result as string,
        }));
        
        setNotification({
          open: true,
          message: '头像已更新',
          type: 'success',
        });
      }
    };
    reader.readAsDataURL(file);
  };
  
  // 关闭通知
  const handleCloseNotification = () => {
    setNotification((prev) => ({
      ...prev,
      open: false,
    }));
  };
  
  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        个人资料
      </Typography>
      
      {loading && !user ? (
        <Box display="flex" justifyContent="center" my={4}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={3}>
          {/* 左侧：头像和基本信息 */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <Box position="relative" display="inline-block">
                <Avatar
                  src={user?.avatar}
                  alt={user?.name}
                  sx={{ width: 150, height: 150, mb: 2, mx: 'auto' }}
                />
                <input
                  type="file"
                  accept="image/*"
                  id="avatar-upload"
                  style={{ display: 'none' }}
                  onChange={handleAvatarUpload}
                />
                <label htmlFor="avatar-upload">
                  <IconButton
                    component="span"
                    sx={{
                      position: 'absolute',
                      bottom: 10,
                      right: 10,
                      bgcolor: 'primary.main',
                      color: 'white',
                      '&:hover': {
                        bgcolor: 'primary.dark',
                      },
                    }}
                  >
                    <CloudUploadIcon />
                  </IconButton>
                </label>
              </Box>
              
              <Typography variant="h5" gutterBottom>
                {user?.name}
              </Typography>
              
              <Typography color="textSecondary" gutterBottom>
                {user?.role} · {user?.department}
              </Typography>
              
              <Divider sx={{ my: 2 }} />
              
              <Box textAlign="left">
                <Typography variant="body2" gutterBottom>
                  <strong>邮箱：</strong> {user?.email}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>电话：</strong> {user?.phone}
                </Typography>
                <Typography variant="body2" gutterBottom>
                  <strong>加入时间：</strong>{' '}
                  {new Date(user?.createdAt).toLocaleDateString()}
                </Typography>
              </Box>
              
              <Button
                variant="outlined"
                color="primary"
                startIcon={<KeyIcon />}
                fullWidth
                sx={{ mt: 2 }}
                onClick={() => setPasswordDialogOpen(true)}
              >
                修改密码
              </Button>
            </Paper>
          </Grid>
          
          {/* 右侧：个人资料编辑表单 */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3 }}>
              <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                mb={3}
              >
                <Typography variant="h6">个人资料</Typography>
                {!isEditing ? (
                  <Button
                    variant="outlined"
                    startIcon={<EditIcon />}
                    onClick={() => setIsEditing(true)}
                  >
                    编辑资料
                  </Button>
                ) : (
                  <Button
                    variant="outlined"
                    color="error"
                    onClick={() => {
                      setIsEditing(false);
                      // 重置表单数据
                      if (user) {
                        setFormData({
                          name: user.name || '',
                          email: user.email || '',
                          phone: user.phone || '',
                          department: user.department || '',
                          bio: user.bio || '',
                        });
                      }
                    }}
                  >
                    取消
                  </Button>
                )}
              </Box>
              
              {error && (
                <Alert severity="error" sx={{ mb: 3 }}>
                  {error}
                </Alert>
              )}
              
              <Box component="form" onSubmit={handleSubmit}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="姓名"
                      name="name"
                      value={formData.name}
                      onChange={handleChange}
                      disabled={!isEditing || loading}
                      required
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="邮箱"
                      name="email"
                      type="email"
                      value={formData.email}
                      onChange={handleChange}
                      disabled={!isEditing || loading}
                      required
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="电话"
                      name="phone"
                      value={formData.phone}
                      onChange={handleChange}
                      disabled={!isEditing || loading}
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <TextField
                      fullWidth
                      label="部门"
                      name="department"
                      value={formData.department}
                      onChange={handleChange}
                      disabled={!isEditing || loading}
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="个人简介"
                      name="bio"
                      multiline
                      rows={4}
                      value={formData.bio}
                      onChange={handleChange}
                      disabled={!isEditing || loading}
                    />
                  </Grid>
                  
                  {isEditing && (
                    <Grid item xs={12}>
                      <Button
                        type="submit"
                        variant="contained"
                        color="primary"
                        startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />}
                        disabled={loading}
                        sx={{ mt: 2 }}
                      >
                        {loading ? '保存中...' : '保存修改'}
                      </Button>
                    </Grid>
                  )}
                </Grid>
              </Box>
            </Paper>
          </Grid>
        </Grid>
      )}
      
      {/* 修改密码对话框 */}
      <Dialog
        open={passwordDialogOpen}
        onClose={() => !loading && setPasswordDialogOpen(false)}
      >
        <DialogTitle>修改密码</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            请输入您的当前密码和新密码。新密码必须至少包含8个字符。
          </DialogContentText>
          
          {passwordError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {passwordError}
            </Alert>
          )}
          
          <TextField
            fullWidth
            margin="dense"
            label="当前密码"
            name="currentPassword"
            type="password"
            value={passwordData.currentPassword}
            onChange={handlePasswordChange}
            disabled={loading}
            required
            autoFocus
          />
          
          <TextField
            fullWidth
            margin="dense"
            label="新密码"
            name="newPassword"
            type="password"
            value={passwordData.newPassword}
            onChange={handlePasswordChange}
            disabled={loading}
            required
          />
          
          <TextField
            fullWidth
            margin="dense"
            label="确认新密码"
            name="confirmPassword"
            type="password"
            value={passwordData.confirmPassword}
            onChange={handlePasswordChange}
            disabled={loading}
            required
          />
        </DialogContent>
        
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={() => setPasswordDialogOpen(false)}
            disabled={loading}
          >
            取消
          </Button>
          <Button
            onClick={handlePasswordSubmit}
            variant="contained"
            color="primary"
            disabled={
              loading ||
              !passwordData.currentPassword ||
              !passwordData.newPassword ||
              !passwordData.confirmPassword
            }
            startIcon={loading ? <CircularProgress size={20} color="inherit" /> : null}
          >
            {loading ? '提交中...' : '修改密码'}
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 通知消息 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
      >
        <Alert
          onClose={handleCloseNotification}
          severity={notification.type}
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Profile; 