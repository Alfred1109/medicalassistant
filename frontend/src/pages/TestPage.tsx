import React from 'react';
import { Box, Typography, Container, Paper } from '@mui/material';

/**
 * 测试页面
 * 仅用于验证路由系统是否正常工作
 */
const TestPage: React.FC = () => {
  return (
    <Container maxWidth="lg" sx={{ mt: 2, mb: 4 }}>
      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          测试页面
        </Typography>
        <Typography variant="body1" paragraph>
          如果您能看到此页面，说明路由系统工作正常！
        </Typography>
        <Box sx={{ mt: 3 }}>
          当前时间: {new Date().toLocaleString()}
        </Box>
      </Paper>
    </Container>
  );
};

export default TestPage; 