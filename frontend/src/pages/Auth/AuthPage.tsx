import React from 'react';
import { Outlet } from 'react-router-dom';
import { Container, Box, Paper, Typography, useTheme } from '@mui/material';
import { FitnessCenter as FitnessCenterIcon } from '@mui/icons-material';

const AuthPage: React.FC = () => {
  const theme = useTheme();

  return (
    <Container component="main" maxWidth="xs" sx={{ py: 8 }}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Box 
          sx={{ 
            mb: 3, 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center' 
          }}
        >
          <FitnessCenterIcon 
            sx={{ 
              fontSize: 40, 
              color: 'primary.main',
              mb: 1,
            }} 
          />
          <Typography component="h1" variant="h4" fontWeight="bold">
            RehabAssist
          </Typography>
          <Typography variant="subtitle1" color="text.secondary" gutterBottom>
            Medical Rehabilitation Assistant
          </Typography>
        </Box>
        
        <Paper 
          elevation={3} 
          sx={{ 
            p: 4, 
            width: '100%', 
            borderRadius: 2,
            border: `1px solid ${theme.palette.divider}`,
          }}
        >
          <Outlet />
        </Paper>
        
        <Typography variant="body2" color="text.secondary" sx={{ mt: 4 }}>
          © {new Date().getFullYear()} RehabAssist - All rights reserved
        </Typography>
      </Box>
    </Container>
  );
};

export default AuthPage; 