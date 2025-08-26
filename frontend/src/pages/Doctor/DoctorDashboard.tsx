import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';

const DoctorDashboard: React.FC = () => {
  return (
    <Box sx={{ width: '100%' }}>
      <Outlet />
    </Box>
  );
};

export default DoctorDashboard; 