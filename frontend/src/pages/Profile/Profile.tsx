import React, { useState } from 'react';
import { useSelector } from 'react-redux';
import {
  Alert, Avatar, Box, Button, Container, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, Divider, Grid, Paper, TextField, Typography,
} from '@mui/material';
import { CloudUpload, Edit, Key } from '@mui/icons-material';
import type { RootState } from '../../store';

const roleNames = {
  patient: '患者', doctor: '医生', health_manager: '健康管理师', admin: '管理员',
};
const missingValue = '未提供';
type AccountOperation = '编辑资料' | '修改头像' | '修改密码';

function profileText(user: object, field: string): string {
  const value: unknown = Reflect.get(user, field);
  return typeof value === 'string' && value.trim() ? value : missingValue;
}

function joinedDate(value: string): string {
  if (!value) return missingValue;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleDateString() : missingValue;
}

const Profile = () => {
  const user = useSelector((state: RootState) => state.auth.user);
  const [operation, setOperation] = useState<AccountOperation | null>(null);

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>个人资料</Typography>
      {!user ? (
        <Alert severity="warning">当前没有已验证的账号资料，请重新登录后查看。</Alert>
      ) : (
        <>
          <Alert severity="info" sx={{ mb: 3 }}>
            以下显示当前登录账号的资料。统一账号管理暂未接通，资料、头像和密码修改暂不可办理。
          </Alert>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Paper sx={{ p: 3, textAlign: 'center' }}>
                <Avatar alt={user.name} sx={{ width: 150, height: 150, mb: 2, mx: 'auto' }}>
                  {user.name?.trim().slice(0, 1)}
                </Avatar>
                <Button startIcon={<CloudUpload />} onClick={() => setOperation('修改头像')}>
                  修改头像
                </Button>
                <Typography variant="h5" gutterBottom>{profileText(user, 'name')}</Typography>
                <Typography color="text.secondary">{roleNames[user.role] ?? missingValue}</Typography>
                <Divider sx={{ my: 2 }} />
                <Box textAlign="left">
                  <Typography variant="body2" gutterBottom><strong>邮箱：</strong>{profileText(user, 'email')}</Typography>
                  <Typography variant="body2" gutterBottom><strong>电话：</strong>{profileText(user, 'phone')}</Typography>
                  <Typography variant="body2" gutterBottom><strong>加入时间：</strong>{joinedDate(user.createdAt)}</Typography>
                </Box>
                <Button variant="outlined" startIcon={<Key />} fullWidth sx={{ mt: 2 }}
                  onClick={() => setOperation('修改密码')}>修改密码</Button>
              </Paper>
            </Grid>
            <Grid item xs={12} md={8}>
              <Paper sx={{ p: 3 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                  <Typography variant="h6">个人资料</Typography>
                  <Button variant="outlined" startIcon={<Edit />} onClick={() => setOperation('编辑资料')}>
                    编辑资料
                  </Button>
                </Box>
                <Grid container spacing={2}>
                  {([
                    ['姓名', 'name'], ['邮箱', 'email'], ['电话', 'phone'],
                    ['部门', 'department'], ['个人简介', 'bio'],
                  ] as const).map(([label, field]) => (
                    <Grid item xs={12} sm={field === 'bio' ? 12 : 6} key={field}>
                      <TextField fullWidth label={label} value={profileText(user, field)}
                        InputProps={{ readOnly: true }} multiline={field === 'bio'}
                        rows={field === 'bio' ? 4 : undefined} />
                    </Grid>
                  ))}
                </Grid>
              </Paper>
            </Grid>
          </Grid>
          <Dialog open={operation !== null} onClose={() => setOperation(null)} aria-labelledby="account-operation-title">
            <DialogTitle id="account-operation-title">{operation}</DialogTitle>
            <DialogContent>
              <DialogContentText>
                资料、头像与密码将由统一账号平台管理。该入口暂未接通，当前无法办理{operation}，未提交任何修改。
              </DialogContentText>
            </DialogContent>
            <DialogActions><Button onClick={() => setOperation(null)}>知道了</Button></DialogActions>
          </Dialog>
        </>
      )}
    </Container>
  );
};

export default Profile;
