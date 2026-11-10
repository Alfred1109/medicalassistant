import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import apiClient from '../../services/api';

interface AccountCreateDialogProps {
  open: boolean;
  title: string;
  path: string;
  role: 'doctor' | 'patient' | 'health_manager';
  onClose: () => void;
  onCreated: () => void;
}

const AccountCreateDialog: React.FC<AccountCreateDialogProps> = ({ open, title, path, role, onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const submit = async () => {
    setError('');
    try {
      await apiClient.post(path, { name: name.trim(), email: email.trim(), password, role });
      setName(''); setEmail(''); setPassword('');
      onCreated();
      onClose();
    } catch {
      setError('没有保存。请确认邮箱尚未使用，并且密码不为空。');
    }
  };

  return <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
    <DialogTitle>{title}</DialogTitle>
    <DialogContent>
      <Alert severity="info" sx={{ mb: 2 }}>账号会保存到本地。统一登录模式下，还需要在接入申请里关联问卷系统账号后才能登录。</Alert>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TextField fullWidth margin="dense" label="姓名" value={name} onChange={event => setName(event.target.value)} />
      <TextField fullWidth margin="dense" label="邮箱" value={email} onChange={event => setEmail(event.target.value)} />
      <TextField fullWidth margin="dense" label="初始密码" type="password" value={password} onChange={event => setPassword(event.target.value)} />
    </DialogContent>
    <DialogActions>
      <Button onClick={onClose}>取消</Button>
      <Button variant="contained" onClick={submit}>保存</Button>
    </DialogActions>
  </Dialog>;
};

export default AccountCreateDialog;
