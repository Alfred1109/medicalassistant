import React, { useEffect } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
// import SideMenu from '../../components/Admin/SideMenu'; // Removed redundant SideMenu import
// import { Grid } from '@mui/material'; // Removed unused Grid import

const AdminDashboard: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  // Keep loading state for potential future use or initial loading indicator
  const [isLoading, setIsLoading] = React.useState(false); 

  // Keep redirect logic if needed
  useEffect(() => {
    if (location.pathname === '/app/admin') {
      navigate('/app/admin/doctors');
    }
    // Optionally remove timeout logic if no longer needed
    // const timer = setTimeout(() => {
    //   setIsLoading(false);
    // }, 500);
    // return () => clearTimeout(timer);
  }, [location.pathname, navigate]);

  // Simplified return: Render Outlet directly, or loading indicator
  return (
    <Box sx={{ width: '100%', p: 3 /* Keep padding if desired */ }}>
      {isLoading ? (
        <Box display="flex" alignItems="center" justifyContent="center" height="200px">
          <CircularProgress size={40} />
          <Typography sx={{ ml: 2 }}>加载中...</Typography>
        </Box>
      ) : (
        <Outlet />
      )}
    </Box>
  );
};

export default AdminDashboard; 