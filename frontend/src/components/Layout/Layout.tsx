import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  IconButton,
  Divider,
  Avatar,
  Menu,
  MenuItem,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  FitnessCenter as FitnessCenterIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  Logout as LogoutIcon,
  ChevronLeft as ChevronLeftIcon,
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { toggleSidebar } from '../../store/slices/uiSlice';

// Drawer width for desktop
const DRAWER_WIDTH = 240;

const Layout: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  const { user } = useSelector((state: RootState) => state.auth);
  const { sidebarOpen } = useSelector((state: RootState) => state.ui);
  
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  
  const handleDrawerToggle = () => {
    dispatch(toggleSidebar());
  };
  
  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };
  
  const handleMenuClose = () => {
    setAnchorEl(null);
  };
  
  const handleLogout = () => {
    handleMenuClose();
    dispatch(logout());
    navigate('/auth');
  };
  
  const handleNavigate = (path: string) => {
    navigate(path);
    if (isMobile) {
      dispatch(toggleSidebar());
    }
  };
  
  const drawerContent = (
    <>
      <Box sx={{ px: 2, py: 3, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="h6" component="h1" sx={{ fontWeight: 'bold' }}>
          康复助手
        </Typography>
        {isMobile && (
          <IconButton onClick={handleDrawerToggle}>
            <ChevronLeftIcon />
          </IconButton>
        )}
      </Box>
      <Divider />
      <List>
        <ListItem 
          button 
          selected={location.pathname === '/dashboard' || location.pathname === '/'} 
          onClick={() => handleNavigate('/dashboard')}
        >
          <ListItemIcon>
            <DashboardIcon color={location.pathname === '/dashboard' || location.pathname === '/' ? 'primary' : 'inherit'} />
          </ListItemIcon>
          <ListItemText primary="仪表盘" />
        </ListItem>
        
        <ListItem 
          button 
          selected={location.pathname.includes('/rehab-plans')} 
          onClick={() => handleNavigate('/rehab-plans')}
        >
          <ListItemIcon>
            <FitnessCenterIcon color={location.pathname.includes('/rehab-plans') ? 'primary' : 'inherit'} />
          </ListItemIcon>
          <ListItemText primary="康复计划" />
        </ListItem>
        
        <ListItem 
          button 
          selected={location.pathname.includes('/agents')} 
          onClick={() => handleNavigate('/agents')}
        >
          <ListItemIcon>
            <PsychologyIcon color={location.pathname.includes('/agents') ? 'primary' : 'inherit'} />
          </ListItemIcon>
          <ListItemText primary="智能助手" />
        </ListItem>
      </List>
      <Divider />
      <List>
        <ListItem 
          button 
          selected={location.pathname === '/profile'} 
          onClick={() => handleNavigate('/profile')}
        >
          <ListItemIcon>
            <PersonIcon color={location.pathname === '/profile' ? 'primary' : 'inherit'} />
          </ListItemIcon>
          <ListItemText primary="我的资料" />
        </ListItem>
      </List>
    </>
  );
  
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar 
        position="fixed" 
        sx={{ 
          zIndex: (theme) => theme.zIndex.drawer + 1,
          boxShadow: '0 2px 10px rgba(0, 0, 0, 0.1)'
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2 }}
          >
            <MenuIcon />
          </IconButton>
          
          <Typography variant="h6" noWrap sx={{ flexGrow: 1 }}>
            医疗康复智能助手
          </Typography>
          
          <IconButton
            onClick={handleMenuOpen}
            size="small"
            sx={{ ml: 2 }}
            aria-controls="account-menu"
            aria-haspopup="true"
          >
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
              {user?.name?.charAt(0).toUpperCase() || <PersonIcon />}
            </Avatar>
          </IconButton>
          
          <Menu
            id="account-menu"
            anchorEl={anchorEl}
            keepMounted
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
            transformOrigin={{ horizontal: 'right', vertical: 'top' }}
            anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          >
            <MenuItem onClick={() => { handleMenuClose(); navigate('/profile'); }}>
              <ListItemIcon>
                <PersonIcon fontSize="small" />
              </ListItemIcon>
              个人资料
            </MenuItem>
            <Divider />
            <MenuItem onClick={handleLogout}>
              <ListItemIcon>
                <LogoutIcon fontSize="small" />
              </ListItemIcon>
              退出登录
            </MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      
      <Drawer
        variant={isMobile ? 'temporary' : 'persistent'}
        open={sidebarOpen}
        onClose={isMobile ? handleDrawerToggle : undefined}
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
          },
        }}
      >
        {drawerContent}
      </Drawer>
      
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          pt: 8,
          width: { md: `calc(100% - ${sidebarOpen ? DRAWER_WIDTH : 0}px)` },
          transition: theme.transitions.create(['width', 'margin'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
          }),
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
};

export default Layout; 