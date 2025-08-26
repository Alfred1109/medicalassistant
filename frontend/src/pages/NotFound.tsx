import React from 'react';
import { Link } from 'react-router-dom';
import {
  Box,
  Button,
  Container,
  Paper,
  Typography,
  useTheme,
} from '@mui/material';
import { Home as HomeIcon } from '@mui/icons-material';

const NotFound: React.FC = () => {
  const theme = useTheme();

  return (
    <Container maxWidth="md" sx={{ mt: 8, mb: 8 }}>
      <Paper 
        elevation={3} 
        sx={{ 
          p: 5, 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center',
          textAlign: 'center'
        }}
      >
        <Typography 
          variant="h1" 
          color="primary" 
          sx={{ 
            fontSize: { xs: '6rem', md: '10rem' },
            fontWeight: 'bold',
            mb: 2
          }}
        >
          404
        </Typography>
        
        <Typography 
          variant="h4" 
          gutterBottom
          sx={{ mb: 3 }}
        >
          页面未找到
        </Typography>
        
        <Typography 
          variant="body1" 
          color="textSecondary"
          sx={{ mb: 4, maxWidth: '80%' }}
        >
          您访问的页面可能已被移除、名称已更改或暂时不可用。
        </Typography>
        
        <Box sx={{ mt: 2 }}>
          <Button
            variant="contained"
            color="primary"
            size="large"
            component={Link}
            to="/"
            startIcon={<HomeIcon />}
          >
            返回主页
          </Button>
        </Box>
      </Paper>
    </Container>
  );
};

export default NotFound; 