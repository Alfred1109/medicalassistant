import React, { useEffect } from 'react';
import { Box, Typography, Container, Paper } from '@mui/material';
import AuditLogList from '../../components/Admin/AuditLogList';

/**
 * 审计日志页面
 * 用于系统管理员查看系统操作日志
 */
const AuditLogsPage: React.FC = () => {
  useEffect(() => {
    console.log('AuditLogsPage组件已加载');
  }, []);

  return (
    <Container maxWidth="lg" sx={{ mt: 2, mb: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          系统审计日志
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          查看系统所有操作记录，包括登录、数据修改、权限变更等活动
        </Typography>
        <Box sx={{ mt: 3 }}>
          <AuditLogList />
        </Box>
      </Paper>
    </Container>
  );
};

export default AuditLogsPage; 