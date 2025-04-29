import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box, Container, Grid, Typography } from '@mui/material';
import AdminSideMenu from '../../components/Admin/SideMenu';

const AdminDashboard: React.FC = () => {
  return (
    <Container maxWidth={false} sx={{ mt: 2 }}>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <Typography variant="h4" component="h1" gutterBottom>
            系统管理后台
          </Typography>
        </Grid>
        
        <Grid item xs={12} md={3} lg={2}>
          <AdminSideMenu />
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

export default AdminDashboard; 