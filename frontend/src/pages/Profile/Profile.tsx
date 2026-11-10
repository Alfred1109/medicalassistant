import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  Alert, Avatar, Box, Button, Container, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, Grid, Paper, TextField, Typography,
} from '@mui/material';
import { CloudUpload, Edit, Key } from '@mui/icons-material';
import type { AppDispatch, RootState } from '../../store';
import { replaceUser, updateUserProfile } from '../../store/slices/authSlice';
import httpClient from '../../services/httpClient';

const roleNames: Record<string, string> = {
  patient: '患者', doctor: '医生', health_manager: '健康管理师', admin: '管理员',
};

const Profile = () => {
  const dispatch = useDispatch<AppDispatch>();
  const user = useSelector((state: RootState) => state.auth.user);
  const [editing, setEditing] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [bio, setBio] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [avatarUrl, setAvatarUrl] = useState('');

  useEffect(() => {
    httpClient.get('/users/me').then(({ data }) => dispatch(replaceUser(data))).catch(() => undefined);
  }, [dispatch]);

  useEffect(() => {
    if (!user) return;
    setName(user.name || '');
    setPhone(user.phone || '');
    setBio(user.bio || '');
    if (!user.has_avatar) return;
    let address = '';
    httpClient.get('/users/me/avatar', { responseType: 'blob' }).then(({ data }) => {
      address = URL.createObjectURL(data);
      setAvatarUrl(address);
    }).catch(() => undefined);
    return () => { if (address) URL.revokeObjectURL(address); };
  }, [user]);

  const saveProfile = async () => {
    setError('');
    const result = await dispatch(updateUserProfile({ name: name.trim(), phone: phone.trim(), bio: bio.trim() }));
    if (updateUserProfile.fulfilled.match(result)) {
      setEditing(false);
      setMessage('资料已保存。邮箱和角色仍由账号来源管理。');
    } else {
      setError('资料没有保存。');
    }
  };

  const savePassword = async () => {
    setError('');
    try {
      await httpClient.post('/users/me/password', { current_password: currentPassword, new_password: newPassword });
      setPasswordOpen(false);
      setCurrentPassword('');
      setNewPassword('');
      setMessage('本地密码已更新。');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || '密码没有修改。统一登录账号的密码仍在问卷系统里。');
    }
  };

  const uploadAvatar = async (file?: File) => {
    if (!file) return;
    const form = new FormData();
    form.set('file', file);
    try {
      await httpClient.post('/users/me/avatar', form);
      const { data } = await httpClient.get('/users/me/avatar', { responseType: 'blob' });
      setAvatarUrl(URL.createObjectURL(data));
      setMessage('头像已保存。');
    } catch {
      setError('头像没有保存。请使用 512KB 以内的 JPG 或 PNG。');
    }
  };

  if (!user) {
    return <Container maxWidth="lg" sx={{ mt: 4 }}><Alert severity="warning">当前没有已验证的账号资料，请重新登录后查看。</Alert></Container>;
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>个人资料</Typography>
      {message && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setMessage('')}>{message}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}
      <Alert severity="info" sx={{ mb: 3 }}>
        姓名、电话、简介和头像保存在本系统。邮箱不能在这里改。{user.local_password ? '这个账号有本地密码，可以在这里修改。' : '统一登录账号的密码在问卷系统里修改。'}
      </Alert>
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 3, textAlign: 'center' }}>
            <Avatar src={avatarUrl} alt={user.name} sx={{ width: 150, height: 150, mb: 2, mx: 'auto' }}>{user.name?.trim().slice(0, 1)}</Avatar>
            <Button component="label" startIcon={<CloudUpload />}>修改头像
              <input hidden accept="image/jpeg,image/png" type="file" onChange={event => uploadAvatar(event.target.files?.[0])} />
            </Button>
            <Typography variant="h5" gutterBottom>{user.name}</Typography>
            <Typography color="text.secondary">{roleNames[user.role] || user.role}</Typography>
            <Divider sx={{ my: 2 }} />
            <Typography variant="body2" gutterBottom><strong>邮箱：</strong>{user.email}</Typography>
            <Button variant="outlined" startIcon={<Key />} fullWidth sx={{ mt: 2 }} onClick={() => setPasswordOpen(true)}>修改密码</Button>
          </Paper>
        </Grid>
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 3 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
              <Typography variant="h6">个人资料</Typography>
              <Button variant="outlined" startIcon={<Edit />} onClick={() => setEditing(true)}>编辑资料</Button>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}><TextField fullWidth label="姓名" value={user.name} InputProps={{ readOnly: true }} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth label="邮箱" value={user.email} InputProps={{ readOnly: true }} /></Grid>
              <Grid item xs={12} sm={6}><TextField fullWidth label="电话" value={user.phone || '未提供'} InputProps={{ readOnly: true }} /></Grid>
              <Grid item xs={12}><TextField fullWidth label="个人简介" value={user.bio || '未提供'} InputProps={{ readOnly: true }} multiline rows={4} /></Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
      <Dialog open={editing} onClose={() => setEditing(false)} fullWidth>
        <DialogTitle>编辑资料</DialogTitle>
        <DialogContent>
          <TextField fullWidth margin="normal" label="姓名" value={name} onChange={event => setName(event.target.value)} />
          <TextField fullWidth margin="normal" label="电话" value={phone} onChange={event => setPhone(event.target.value)} />
          <TextField fullWidth margin="normal" label="个人简介" value={bio} onChange={event => setBio(event.target.value)} multiline rows={4} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(false)}>取消</Button>
          <Button variant="contained" disabled={!name.trim()} onClick={saveProfile}>保存</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={passwordOpen} onClose={() => setPasswordOpen(false)} fullWidth>
        <DialogTitle>修改密码</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mt: 1 }}>只修改本系统保存的本地密码。问卷系统账号请到问卷系统修改。</Alert>
          <TextField fullWidth margin="normal" type="password" label="当前密码" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} />
          <TextField fullWidth margin="normal" type="password" label="新密码" value={newPassword} onChange={event => setNewPassword(event.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPasswordOpen(false)}>取消</Button>
          <Button variant="contained" disabled={currentPassword.length < 1 || newPassword.length < 8} onClick={savePassword}>保存</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Profile;
