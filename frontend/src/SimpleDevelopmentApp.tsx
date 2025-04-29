import React from 'react';
import { Container, Paper, Typography, Box, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import ConstructionIcon from '@mui/icons-material/Construction';

interface DevelopmentPageProps {
  pageName: string;
  description?: string;
  returnPath?: string;
}

const SimpleDevelopmentApp: React.FC<DevelopmentPageProps> = ({
  pageName,
  description = '该页面正在开发中，请稍后再访问。',
  returnPath = '/'
}) => {
  const navigate = useNavigate();

  return (
    <Container maxWidth="md" sx={{ py: 8 }}>
      <Paper 
        elevation={3} 
        sx={{ 
          p: 5, 
          borderRadius: 2,
          textAlign: 'center',
          backgroundColor: '#f8f9fa',
        }}
      >
        <Box sx={{ mb: 4 }}>
          <ConstructionIcon sx={{ fontSize: 80, color: '#f59e0b', mb: 2 }} />
          <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 'bold' }}>
            功能开发中
          </Typography>
          <Typography variant="h6" sx={{ color: 'text.secondary', mb: 2 }}>
            {pageName}
          </Typography>
          <Typography variant="body1" color="text.secondary" paragraph>
            {description}
          </Typography>
        </Box>
        
        <Button 
          variant="contained" 
          color="primary" 
          size="large"
          onClick={() => navigate(returnPath)}
        >
          返回首页
        </Button>
      </Paper>
    </Container>
  );
};

export default SimpleDevelopmentApp; 