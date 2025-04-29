import React, { useState, useEffect } from 'react';
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
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Divider,
  Avatar,
  Menu,
  MenuItem,
  useMediaQuery,
  useTheme,
  Collapse,
  Tooltip,
  alpha
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  FitnessCenter as FitnessCenterIcon,
  Psychology as PsychologyIcon,
  Person as PersonIcon,
  Logout as LogoutIcon,
  ChevronLeft as ChevronLeftIcon,
  ExpandLess,
  ExpandMore,
  AdminPanelSettings as AdminIcon,
  LocalHospital as DoctorIcon,
  HealthAndSafety as HealthManagerIcon,
  PersonOutline as PatientIcon,
  Home as HomeIcon,
  Business as BusinessIcon,
  Folder as FolderIcon,
  MonitorHeart as MonitorHeartIcon,
  EventNote as EventNoteIcon,
  QueryStats as QueryStatsIcon,
  Chat as ChatIcon,
  Timeline as TimelineIcon,
  Tune as TuneIcon,
  Label as LabelIcon,
  Devices as DevicesIcon,
  Insights as InsightsIcon,
  Description as DescriptionIcon
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { toggleSidebar } from '../../store/slices/uiSlice';

// Drawer width for desktop
const DRAWER_WIDTH = 260;

// 菜单项接口
interface MenuItem {
  name: string;
  path: string;
  icon: React.ReactNode;
  roles?: string[];
  children?: MenuItem[];
}

const Layout: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  const { user } = useSelector((state: RootState) => state.auth);
  const { sidebarOpen } = useSelector((state: RootState) => state.ui);
  
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [openSubmenu, setOpenSubmenu] = useState<string | null>(null);
  const userRole = localStorage.getItem('userRole') || '';
  
  // 根据当前路径自动打开子菜单
  useEffect(() => {
    const path = location.pathname;
    if (path.includes('/app/admin')) {
      setOpenSubmenu('admin');
    } else if (path.includes('/app/doctor')) {
      setOpenSubmenu('doctor');
    } else if (path.includes('/app/patient')) {
      setOpenSubmenu('patient');
    } else if (path.includes('/app/health-manager')) {
      setOpenSubmenu('health-manager');
    }
  }, [location.pathname]);
  
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
  
  const handleSubmenuToggle = (menuId: string) => {
    setOpenSubmenu(openSubmenu === menuId ? null : menuId);
  };
  
  // 基础菜单项
  const baseMenuItems: MenuItem[] = [
    { name: '首页', path: '/app/dashboard', icon: <HomeIcon /> },
    { name: '康复计划', path: '/app/rehab-plans', icon: <FitnessCenterIcon /> },
    { name: '智能助手', path: '/app/agents', icon: <PsychologyIcon /> },
  ];
  
  // 角色模块菜单
  const roleMenuItems: MenuItem[] = [
    { 
      name: '管理员', 
      path: '/app/admin', 
      icon: <AdminIcon />, 
      roles: ['admin'],
      children: [
        { name: '医生管理', path: '/app/admin/doctors', icon: <DoctorIcon /> },
        { name: '患者管理', path: '/app/admin/patients', icon: <PatientIcon /> },
        { name: '健管师管理', path: '/app/admin/health-managers', icon: <HealthManagerIcon /> },
        { name: '组织机构', path: '/app/admin/organizations', icon: <BusinessIcon /> },
        { name: '标签管理', path: '/app/admin/tags', icon: <LabelIcon /> },
        { name: '设备查看', path: '/app/admin/devices', icon: <DevicesIcon /> },
        { name: '数据可视化', path: '/app/admin/visualization', icon: <InsightsIcon /> },
      ]
    },
    { 
      name: '医生工作站', 
      path: '/app/doctor', 
      icon: <DoctorIcon />, 
      roles: ['doctor'],
      children: [
        { name: '患者管理', path: '/app/doctor/patients', icon: <PatientIcon /> },
        { name: '健康档案', path: '/app/doctor/health-records', icon: <FolderIcon /> },
        { name: '随访管理', path: '/app/doctor/follow-ups', icon: <EventNoteIcon /> },
        { name: '数据监测', path: '/app/doctor/monitoring', icon: <MonitorHeartIcon /> },
        { name: '医患沟通', path: '/app/doctor/communications', icon: <ChatIcon /> },
        { name: '数据统计', path: '/app/doctor/statistics', icon: <QueryStatsIcon /> },
        { name: '知情同意', path: '/app/doctor/informed-consent', icon: <DescriptionIcon /> },
      ]
    },
    { 
      name: '患者中心', 
      path: '/app/patient', 
      icon: <PatientIcon />, 
      roles: ['patient'],
      children: [
        { name: '健康档案', path: '/app/patient/health-records', icon: <FolderIcon /> },
        { name: '日常记录', path: '/app/patient/daily-records', icon: <EventNoteIcon /> },
        { name: '设备绑定', path: '/app/patient/devices', icon: <DevicesIcon /> },
        { name: '医患沟通', path: '/app/patient/communications', icon: <ChatIcon /> },
        { name: '数据统计', path: '/app/patient/statistics', icon: <QueryStatsIcon /> },
      ]
    },
    { 
      name: '健康管理师', 
      path: '/app/health-manager', 
      icon: <HealthManagerIcon />, 
      roles: ['health_manager'],
      children: [
        { name: '患者管理', path: '/app/health-manager/patients', icon: <PatientIcon /> },
        { name: '健康档案', path: '/app/health-manager/health-records', icon: <FolderIcon /> },
        { name: '健康数据时间线', path: '/app/health-manager/health-data-timeline', icon: <TimelineIcon /> },
        { name: '健康数据阈值', path: '/app/health-manager/thresholds', icon: <TuneIcon /> },
        { name: '随访管理', path: '/app/health-manager/follow-ups', icon: <EventNoteIcon /> },
        { name: '数据监测', path: '/app/health-manager/monitoring', icon: <MonitorHeartIcon /> },
        { name: '医患沟通', path: '/app/health-manager/communications', icon: <ChatIcon /> },
        { name: '数据统计', path: '/app/health-manager/statistics', icon: <QueryStatsIcon /> },
      ]
    },
  ];
  
  // 过滤当前用户可见的角色菜单
  const filteredRoleMenuItems = roleMenuItems.filter(item => 
    !item.roles || item.roles.includes(userRole)
  );
  
  const renderMenuItem = (item: MenuItem) => {
    const isSelected = location.pathname === item.path || location.pathname.startsWith(item.path + '/');
    
    if (item.children) {
      const isSubmenuOpen = openSubmenu === item.path.split('/').pop();
      const isActive = location.pathname.startsWith(item.path);
      
      return (
        <React.Fragment key={item.path}>
          <ListItem disablePadding>
            <ListItemButton
              onClick={() => handleSubmenuToggle(item.path.split('/').pop() || '')}
              selected={isActive}
              sx={{
                pl: 2,
                '&.Mui-selected': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.1),
                  '&:hover': {
                    backgroundColor: alpha(theme.palette.primary.main, 0.2),
                  }
                }
              }}
            >
              <ListItemIcon sx={{ color: isActive ? 'primary.main' : 'inherit' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText primary={item.name} />
              {isSubmenuOpen ? <ExpandLess /> : <ExpandMore />}
            </ListItemButton>
          </ListItem>
          <Collapse in={isSubmenuOpen} timeout="auto" unmountOnExit>
            <List component="div" disablePadding>
              {item.children.map(child => (
                <ListItem key={child.path} disablePadding>
                  <ListItemButton
                    sx={{ 
                      pl: 4,
                      '&.Mui-selected': {
                        backgroundColor: alpha(theme.palette.primary.main, 0.1),
                        '&:hover': {
                          backgroundColor: alpha(theme.palette.primary.main, 0.2),
                        }
                      }
                    }}
                    selected={location.pathname === child.path || location.pathname.startsWith(child.path + '/')}
                    onClick={() => handleNavigate(child.path)}
                  >
                    <ListItemIcon sx={{ 
                      color: (location.pathname === child.path || location.pathname.startsWith(child.path + '/')) 
                        ? 'primary.main' 
                        : 'inherit' 
                    }}>
                      {child.icon}
                    </ListItemIcon>
                    <ListItemText primary={child.name} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </Collapse>
        </React.Fragment>
      );
    }
    
    return (
      <ListItem key={item.path} disablePadding>
        <ListItemButton
          selected={isSelected}
          onClick={() => handleNavigate(item.path)}
          sx={{
            pl: 2,
            '&.Mui-selected': {
              backgroundColor: alpha(theme.palette.primary.main, 0.1),
              '&:hover': {
                backgroundColor: alpha(theme.palette.primary.main, 0.2),
              }
            }
          }}
        >
          <ListItemIcon sx={{ color: isSelected ? 'primary.main' : 'inherit' }}>
            {item.icon}
          </ListItemIcon>
          <ListItemText primary={item.name} />
        </ListItemButton>
      </ListItem>
    );
  };
  
  const drawerContent = (
    <>
      <Box sx={{ 
        px: 2, 
        py: 3, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        borderBottom: `1px solid ${theme.palette.divider}`
      }}>
        <Typography variant="h6" component="h1" sx={{ 
          fontWeight: 'bold',
          background: `linear-gradient(45deg, ${theme.palette.primary.main} 30%, ${theme.palette.secondary.main} 90%)`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}>
          医疗康复智能助手
        </Typography>
        {isMobile && (
          <IconButton onClick={handleDrawerToggle}>
            <ChevronLeftIcon />
          </IconButton>
        )}
      </Box>
      
      <Box sx={{ overflowY: 'auto', flexGrow: 1, pt: 2 }}>
        {/* 基础菜单 */}
        <List component="nav" aria-label="basic menu" sx={{ mb: 1 }}>
          {baseMenuItems.map(renderMenuItem)}
        </List>
        
        {/* 用户角色相关菜单 */}
        {filteredRoleMenuItems.length > 0 && (
          <>
            <Divider sx={{ mx: 2, my: 1 }} />
            <Typography 
              variant="caption" 
              sx={{ 
                px: 3, 
                py: 1, 
                display: 'block', 
                color: 'text.secondary',
                fontWeight: 'medium',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}
            >
              角色功能
            </Typography>
            <List component="nav" aria-label="role menu">
              {filteredRoleMenuItems.map(renderMenuItem)}
            </List>
          </>
        )}
      </Box>
      
      <Divider sx={{ mt: 'auto' }} />
      <List sx={{ py: 0 }}>
        <ListItem disablePadding>
          <ListItemButton
            selected={location.pathname === '/app/profile'}
            onClick={() => handleNavigate('/app/profile')}
            sx={{
              '&.Mui-selected': {
                backgroundColor: alpha(theme.palette.primary.main, 0.1),
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.2),
                }
              }
            }}
          >
            <ListItemIcon sx={{ color: location.pathname === '/app/profile' ? 'primary.main' : 'inherit' }}>
              <PersonIcon />
            </ListItemIcon>
            <ListItemText primary="个人资料" />
          </ListItemButton>
        </ListItem>
      </List>
    </>
  );
  
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: '#f9fafc' }}>
      <AppBar 
        position="fixed" 
        elevation={0}
        sx={{ 
          zIndex: (theme) => theme.zIndex.drawer + 1,
          borderBottom: `1px solid ${theme.palette.divider}`,
          backgroundColor: 'white',
          color: 'text.primary'
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
          
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <Typography variant="h6" noWrap sx={{ 
              flexGrow: 1, 
              fontWeight: 'bold',
              background: `linear-gradient(45deg, ${theme.palette.primary.main} 30%, ${theme.palette.secondary.main} 90%)`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              医疗康复智能助手
            </Typography>
          </Box>
          
          <Box sx={{ flexGrow: 1 }} />
          
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Tooltip title="个人中心">
              <IconButton
                onClick={handleMenuOpen}
                size="small"
                sx={{ 
                  ml: 2,
                  border: `1px solid ${theme.palette.divider}`,
                  p: 0.5
                }}
                aria-controls="account-menu"
                aria-haspopup="true"
              >
                <Avatar 
                  sx={{ 
                    width: 32, 
                    height: 32, 
                    bgcolor: alpha(theme.palette.primary.main, 0.8)
                  }}
                >
                  {user?.name?.charAt(0).toUpperCase() || <PersonIcon />}
                </Avatar>
              </IconButton>
            </Tooltip>
          </Box>
          
          <Menu
            id="account-menu"
            anchorEl={anchorEl}
            keepMounted
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
            transformOrigin={{ horizontal: 'right', vertical: 'top' }}
            anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
            PaperProps={{
              elevation: 2,
              sx: {
                minWidth: 180,
                overflow: 'visible',
                filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.08))',
                mt: 1.5,
                '& .MuiMenuItem-root': {
                  px: 2,
                  py: 1,
                },
              },
            }}
          >
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 'medium' }}>
                {user?.name || 'User'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {userRole === 'admin' && '系统管理员'}
                {userRole === 'doctor' && '医生'}
                {userRole === 'patient' && '患者'}
                {userRole === 'health_manager' && '健康管理师'}
              </Typography>
            </Box>
            <Divider />
            <MenuItem onClick={() => { handleMenuClose(); navigate('/app/profile'); }}>
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
        variant={isMobile ? 'temporary' : 'permanent'}
        open={isMobile ? sidebarOpen : true}
        onClose={isMobile ? handleDrawerToggle : undefined}
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: DRAWER_WIDTH,
            boxSizing: 'border-box',
            border: 'none',
            boxShadow: isMobile ? '0px 4px 20px rgba(0,0,0,0.05)' : 'none',
            bgcolor: 'white',
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        {drawerContent}
      </Drawer>
      
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2, md: 3 },
          pt: { xs: 9, md: 10 },
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          maxWidth: '100%',
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