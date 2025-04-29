import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box, Container, Grid, Typography } from '@mui/material';
import PatientSideMenu from '../../components/Patient/SideMenu';

const PatientDashboard: React.FC = () => {
  return (
    <Container maxWidth={false} sx={{ mt: 2 }}>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Typography variant="h4" component="h1" gutterBottom>
            患者健康管理
          </Typography>
        </Grid>
        
        <Grid item xs={12} md={3} lg={2}>
          <PatientSideMenu />
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

export default PatientDashboard; 