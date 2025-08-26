import React from 'react';
import { Box, CircularProgress, Typography } from '@mui/material';

const LoadingFallback: React.FC = () => {
  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      height="100%"
      minHeight="300px"
    >
      <CircularProgress size={40} />
      <Typography variant="body1" color="text.secondary" sx={{ mt: 2 }}>
        正在加载...
      </Typography>
    </Box>
  );
};

export default LoadingFallback; 