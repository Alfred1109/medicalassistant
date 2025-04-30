import React, { useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Box, Grid, CircularProgress, Typography } from '@mui/material';
import SideMenu from '../../components/Admin/SideMenu';

const AdminDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = React.useState(true);

  // 确保当访问/app/admin时自动重定向到doctors路由
  useEffect(() => {
    if (location.pathname === '/app/admin') {
      navigate('/app/admin/doctors');
    }
    
    // 模拟数据加载
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 500);
    
    return () => clearTimeout(timer);
  }, [location.pathname, navigate]);

  return (
    <Box sx={{ width: '100%', display: 'flex', height: 'calc(100vh - 64px)' }}>
      <Grid container>
        <Grid item xs={12} md={2} sx={{ borderRight: '1px solid #eee' }}>
          <SideMenu />
        </Grid>
        <Grid item xs={12} md={10}>
          <Box sx={{ p: 3, height: '100%', overflow: 'auto' }}>
            {isLoading ? (
              <Box display="flex" alignItems="center" justifyContent="center" height="200px">
                <CircularProgress size={40} />
                <Typography sx={{ ml: 2 }}>加载中...</Typography>
              </Box>
            ) : (
              <Outlet />
            )}
          </Box>
        </Grid>
      </Grid>
    </Box>
  );
};

export default AdminDashboard; 