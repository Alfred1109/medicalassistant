import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box, Container, Grid, Typography } from '@mui/material';
import SideMenu from '../../components/Doctor/SideMenu';

const DoctorDashboard: React.FC = () => {
  return (
    <Container maxWidth={false} sx={{ mt: 2 }}>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Typography variant="h4" component="h1" gutterBottom>
            医生工作站
          </Typography>
        </Grid>
        
        <Grid item xs={12} md={3} lg={2}>
          <SideMenu />
        </Grid>
        
        <Grid item xs={12} md={9} lg={10}>
          <Box sx={{ bgcolor: 'background.paper', p: 2, borderRadius: 1 }}>
            <Outlet />
          </Box>
        </Grid>
      </Grid>
    </Container>
  );
};

export default DoctorDashboard; 