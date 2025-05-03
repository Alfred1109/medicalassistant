import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { styled, useTheme, Theme } from '@mui/material/styles';
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  Typography,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  CssBaseline,
  useMediaQuery,
  Avatar,
  Badge,
  Menu,
  MenuItem,
  InputBase,
  Chip,
  Tooltip,
  Breadcrumbs,
  Link,
  Paper,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  Menu as MenuIcon,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
  Search as SearchIcon,
  Notifications as NotificationsIcon,
  Settings as SettingsIcon,
  Dashboard as DashboardIcon,
  People as PeopleIcon,
  LocalHospital as LocalHospitalIcon,
  CalendarMonth as CalendarMonthIcon,
  Healing as HealingIcon,
  Psychology as PsychologyIcon,
  AccountCircle as AccountCircleIcon,
  Language as LanguageIcon,
  Logout as LogoutIcon,
  ViewQuilt as ViewQuiltIcon,
  Warning as CrisisAlertIcon,
  NavigateNext as NavigateNextIcon,
} from '@mui/icons-material';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch, RootState } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { useNavigate, useLocation } from 'react-router-dom';

const drawerWidth = 260;

const openedMixin = (theme: Theme) => ({
  width: drawerWidth,
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.enteringScreen,
  }),
  overflowX: 'hidden',
});

const closedMixin = (theme: Theme) => ({
  transition: theme.transitions.create('width', {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  overflowX: 'hidden',
  width: `calc(${theme.spacing(7)} + 1px)`,
  [theme.breakpoints.up('sm')]: {
    width: `calc(${theme.spacing(8)} + 1px)`,
  },
});

const DrawerHeader = styled('div')(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'flex-end',
  padding: theme.spacing(0, 1),
  // necessary for content to be below app bar
  ...theme.mixins.toolbar,
}));

const AppBarStyled = styled(AppBar, {
  shouldForwardProp: (prop) => prop !== 'open',
})<{
  open?: boolean;
}>(({ theme, open }) => ({
  zIndex: theme.zIndex.drawer + 1,
  background: 'white',
  color: theme.palette.text.primary,
  boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.08)',
  transition: theme.transitions.create(['width', 'margin'], {
    easing: theme.transitions.easing.sharp,
    duration: theme.transitions.duration.leavingScreen,
  }),
  ...(open && {
    marginLeft: drawerWidth,
    width: `calc(100% - ${drawerWidth}px)`,
    transition: theme.transitions.create(['width', 'margin'], {
      easing: theme.transitions.easing.sharp,
      duration: theme.transitions.duration.enteringScreen,
    }),
  }),
}));

const DrawerStyled = styled(Drawer, { shouldForwardProp: (prop) => prop !== 'open' })(
  ({ theme, open }) => ({
    width: drawerWidth,
    flexShrink: 0,
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
    ...(open && {
      ...openedMixin(theme),
      '& .MuiDrawer-paper': openedMixin(theme),
    }),
    ...(!open && {
      ...closedMixin(theme),
      '& .MuiDrawer-paper': closedMixin(theme),
    }),
  }),
);

const SearchWrapper = styled('div')(({ theme }) => ({
  position: 'relative',
  borderRadius: theme.shape.borderRadius,
  backgroundColor: alpha(theme.palette.primary.main, 0.08),
  '&:hover': {
    backgroundColor: alpha(theme.palette.primary.main, 0.12),
  },
  marginRight: theme.spacing(2),
  marginLeft: 0,
  width: '100%',
  [theme.breakpoints.up('sm')]: {
    marginLeft: theme.spacing(3),
    width: 'auto',
  },
}));

const SearchIconWrapper = styled('div')(({ theme }) => ({
  padding: theme.spacing(0, 2),
  height: '100%',
  position: 'absolute',
  pointerEvents: 'none',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.palette.primary.main,
}));

const StyledInputBase = styled(InputBase)(({ theme }) => ({
  color: theme.palette.text.primary,
  '& .MuiInputBase-input': {
    padding: theme.spacing(1, 1, 1, 0),
    // vertical padding + font size from searchIcon
    paddingLeft: `calc(1em + ${theme.spacing(4)})`,
    transition: theme.transitions.create('width'),
    width: '100%',
    [theme.breakpoints.up('md')]: {
      width: '20ch',
    },
  },
}));

const ContentWrapper = styled(Box)(({ theme }) => ({
  flexGrow: 1,
  padding: theme.spacing(3),
  overflow: 'auto',
  backgroundColor: theme.palette.background.default,
  minHeight: '100vh',
}));

interface MenuItem {
  title: string;
  path: string;
  icon: React.ReactNode;
  children?: MenuItem[];
}

// 定义菜单数据
const getMenuItems = (role: string): MenuItem[] => {
  const commonItems = [
    {
      title: '仪表盘',
      path: '/app/dashboard',
      icon: <DashboardIcon />
    },
    {
      title: '用户档案',
      path: '/app/profile',
      icon: <AccountCircleIcon />
    }
  ];

  const roleSpecificItems: Record<string, MenuItem[]> = {
    doctor: [
      {
        title: '患者管理',
        path: '/app/doctor/patients',
        icon: <PeopleIcon />
      },
      {
        title: '健康档案',
        path: '/app/doctor/health-records',
        icon: <ViewQuiltIcon />
      },
      {
        title: '随访管理',
        path: '/app/doctor/follow-up',
        icon: <CalendarMonthIcon />
      },
      {
        title: '数据监测',
        path: '/app/doctor/data-monitoring',
        icon: <CrisisAlertIcon />
      },
      {
        title: '康复计划',
        path: '/app/rehab-plans',
        icon: <HealingIcon />
      },
      {
        title: '智能助手',
        path: '/app/agents',
        icon: <PsychologyIcon />
      },
    ],
    healthManager: [
      {
        title: '患者管理',
        path: '/app/health-manager/patients',
        icon: <PeopleIcon />
      },
      {
        title: '健康数据时间线',
        path: '/app/health-manager/health-timeline',
        icon: <ViewQuiltIcon />
      },
      {
        title: '健康指标阈值',
        path: '/app/health-manager/health-threshold',
        icon: <CrisisAlertIcon />
      },
      {
        title: '随访管理',
        path: '/app/health-manager/follow-up',
        icon: <CalendarMonthIcon />
      },
      {
        title: '康复计划',
        path: '/app/rehab-plans',
        icon: <HealingIcon />
      },
    ],
    patient: [
      {
        title: '健康档案',
        path: '/app/patient/health-records',
        icon: <ViewQuiltIcon />
      },
      {
        title: '日常记录',
        path: '/app/patient/daily-records',
        icon: <CalendarMonthIcon />
      },
      {
        title: '设备绑定',
        path: '/app/patient/device-binding',
        icon: <LocalHospitalIcon />
      },
      {
        title: '康复计划',
        path: '/app/patient/rehab-plans',
        icon: <HealingIcon />
      },
      {
        title: '智能咨询',
        path: '/app/patient/ai-consultation',
        icon: <PsychologyIcon />
      },
    ],
    admin: [
      {
        title: '医生管理',
        path: '/app/admin/doctors',
        icon: <LocalHospitalIcon />
      },
      {
        title: '患者管理',
        path: '/app/admin/patients',
        icon: <PeopleIcon />
      },
      {
        title: '健管师管理',
        path: '/app/admin/health-managers',
        icon: <PeopleIcon />
      },
      {
        title: '机构管理',
        path: '/app/admin/organizations',
        icon: <ViewQuiltIcon />
      },
      {
        title: '系统设置',
        path: '/app/admin/settings',
        icon: <SettingsIcon />
      },
    ],
  };

  return [...commonItems, ...(roleSpecificItems[role] || [])];
};

// 获取面包屑路径映射
const getBreadcrumbTitle = (path: string): string => {
  const pathMap: Record<string, string> = {
    'app': '主页',
    'dashboard': '仪表盘',
    'profile': '用户档案',
    'doctor': '医生',
    'health-manager': '健康管理师',
    'patient': '患者',
    'admin': '管理员',
    'patients': '患者管理',
    'health-records': '健康档案',
    'follow-up': '随访管理',
    'data-monitoring': '数据监测',
    'rehab-plans': '康复计划',
    'agents': '智能助手',
    'health-timeline': '健康数据时间线',
    'health-threshold': '健康指标阈值',
    'daily-records': '日常记录',
    'device-binding': '设备绑定',
    'ai-consultation': '智能咨询',
    'doctors': '医生管理',
    'health-managers': '健管师管理',
    'organizations': '机构管理',
    'settings': '系统设置',
  };

  return pathMap[path] || path;
};

// 生成面包屑组件
const generateBreadcrumbs = (pathname: string) => {
  // 分割并过滤路径
  const pathnames = pathname.split('/').filter((x) => x);
  
  return (
    <Breadcrumbs 
      separator={<NavigateNextIcon fontSize="small" />}
      aria-label="breadcrumb"
      sx={{ mt: 1, mb: 2 }}
    >
      <Link
        color="inherit"
        href="/app/dashboard"
        underline="hover"
        sx={{ display: 'flex', alignItems: 'center' }}
      >
        <DashboardIcon sx={{ mr: 0.5 }} fontSize="inherit" />
        主页
      </Link>
      {pathnames.map((value, index) => {
        // 构建当前路径段的完整URL
        const isLast = index === pathnames.length - 1;
        const to = `/${pathnames.slice(0, index + 1).join('/')}`;
        
        return isLast ? (
          <Typography
            key={to}
            color="text.primary"
            sx={{ display: 'flex', alignItems: 'center' }}
          >
            {getBreadcrumbTitle(value)}
          </Typography>
        ) : (
          <Link
            color="inherit"
            href={to}
            key={to}
            underline="hover"
            sx={{ display: 'flex', alignItems: 'center' }}
          >
            {getBreadcrumbTitle(value)}
          </Link>
        );
      })}
    </Breadcrumbs>
  );
};

interface DashboardLayoutProps {
  children?: React.ReactNode;
}

const DashboardLayout: React.FC<DashboardLayoutProps> = ({ children }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(!isMobile);
  const { user } = useSelector((state: RootState) => state.auth);
  
  // 用户菜单
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [notificationAnchorEl, setNotificationAnchorEl] = useState<null | HTMLElement>(null);
  
  // 根据用户角色获取菜单项
  const menuItems = getMenuItems(user?.role || 'patient');
  
  const handleDrawerOpen = () => {
    setOpen(true);
  };

  const handleDrawerClose = () => {
    setOpen(false);
  };

  const handleUserMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleUserMenuClose = () => {
    setAnchorEl(null);
  };

  const handleNotificationMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setNotificationAnchorEl(event.currentTarget);
  };

  const handleNotificationMenuClose = () => {
    setNotificationAnchorEl(null);
  };

  const handleLogout = () => {
    handleUserMenuClose();
    dispatch(logout());
    navigate('/auth/login');
  };

  const handleProfileClick = () => {
    handleUserMenuClose();
    navigate('/app/profile');
  };

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBarStyled position="fixed" open={open}>
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            onClick={handleDrawerOpen}
            edge="start"
            sx={{
              marginRight: 2,
              ...(open && { display: 'none' }),
            }}
          >
            <MenuIcon />
          </IconButton>
          
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <img src="/health.png" alt="Logo" style={{ height: 32, marginRight: theme.spacing(1) }} />
            <Typography variant="h6" noWrap component="div" sx={{ display: { xs: 'none', sm: 'block' } }}>
              医疗康复助手
            </Typography>
          </Box>
          
          <SearchWrapper>
            <SearchIconWrapper>
              <SearchIcon />
            </SearchIconWrapper>
            <StyledInputBase
              placeholder="搜索..."
              inputProps={{ 'aria-label': 'search' }}
            />
          </SearchWrapper>
          
          <Box sx={{ flexGrow: 1 }} />
          
          {/* 用户角色标识 */}
          <Chip
            label={user?.role === 'doctor' ? '医生' : 
                  user?.role === 'healthManager' ? '健康管理师' : 
                  user?.role === 'patient' ? '患者' : 
                  user?.role === 'admin' ? '管理员' : '未知角色'}
            color={user?.role === 'doctor' ? 'primary' : 
                  user?.role === 'healthManager' ? 'secondary' : 
                  user?.role === 'patient' ? 'info' : 
                  user?.role === 'admin' ? 'warning' : 'default'}
            size="small"
            sx={{ mr: 2 }}
          />
          
          {/* 通知图标 */}
          <Box sx={{ display: { xs: 'none', md: 'flex' } }}>
            <Tooltip title="通知">
              <IconButton
                size="large"
                aria-label="show 17 new notifications"
                color="inherit"
                onClick={handleNotificationMenuOpen}
              >
                <Badge badgeContent={17} color="error">
                  <NotificationsIcon />
                </Badge>
              </IconButton>
            </Tooltip>
            
            {/* 设置图标 */}
            <Tooltip title="设置">
              <IconButton
                size="large"
                edge="end"
                aria-label="settings"
                color="inherit"
              >
                <SettingsIcon />
              </IconButton>
            </Tooltip>
            
            {/* 语言切换 */}
            <Tooltip title="切换语言">
              <IconButton
                size="large"
                edge="end"
                aria-label="language"
                color="inherit"
              >
                <LanguageIcon />
              </IconButton>
            </Tooltip>
            
            {/* 用户头像和菜单 */}
            <Tooltip title="账户设置">
              <IconButton
                size="large"
                edge="end"
                aria-label="account of current user"
                aria-controls="menu-appbar"
                aria-haspopup="true"
                onClick={handleUserMenuOpen}
                color="inherit"
              >
                <Avatar
                  alt={user?.name || 'User'}
                  src={user?.avatar || ''}
                  sx={{ width: 32, height: 32 }}
                />
              </IconButton>
            </Tooltip>
          </Box>
        </Toolbar>
      </AppBarStyled>
      
      {/* 用户菜单 */}
      <Menu
        id="menu-appbar"
        anchorEl={anchorEl}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        keepMounted
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        open={Boolean(anchorEl)}
        onClose={handleUserMenuClose}
      >
        <MenuItem onClick={handleProfileClick}>
          <ListItemIcon>
            <AccountCircleIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>个人资料</ListItemText>
        </MenuItem>
        <MenuItem onClick={handleLogout}>
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>退出登录</ListItemText>
        </MenuItem>
      </Menu>
      
      {/* 通知菜单 */}
      <Menu
        id="notification-menu"
        anchorEl={notificationAnchorEl}
        anchorOrigin={{
          vertical: 'bottom',
          horizontal: 'right',
        }}
        keepMounted
        transformOrigin={{
          vertical: 'top',
          horizontal: 'right',
        }}
        open={Boolean(notificationAnchorEl)}
        onClose={handleNotificationMenuClose}
      >
        <MenuItem onClick={handleNotificationMenuClose}>
          <Typography variant="body2" color="text.secondary">
            您有3个新的随访提醒
          </Typography>
        </MenuItem>
        <MenuItem onClick={handleNotificationMenuClose}>
          <Typography variant="body2" color="text.secondary">
            患者李明提交了新的健康记录
          </Typography>
        </MenuItem>
        <MenuItem onClick={handleNotificationMenuClose}>
          <Typography variant="body2" color="text.secondary">
            系统更新：新增康复计划模板
          </Typography>
        </MenuItem>
        <Divider />
        <MenuItem onClick={handleNotificationMenuClose}>
          <Typography variant="body2" color="primary">
            查看所有通知
          </Typography>
        </MenuItem>
      </Menu>
      
      <DrawerStyled variant="permanent" open={open}>
        <DrawerHeader>
          <IconButton onClick={handleDrawerClose}>
            {theme.direction === 'rtl' ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </DrawerHeader>
        <Divider />
        
        {/* 菜单列表 */}
        <List>
          {menuItems.map((item) => (
            <ListItem key={item.path} disablePadding sx={{ display: 'block' }}>
              <ListItemButton
                sx={{
                  minHeight: 48,
                  justifyContent: open ? 'initial' : 'center',
                  px: 2.5,
                  ...(location.pathname === item.path && {
                    backgroundColor: alpha(theme.palette.primary.main, 0.08),
                    borderRight: `3px solid ${theme.palette.primary.main}`,
                  }),
                }}
                selected={location.pathname === item.path}
                onClick={() => navigate(item.path)}
              >
                <ListItemIcon
                  sx={{
                    minWidth: 0,
                    mr: open ? 3 : 'auto',
                    justifyContent: 'center',
                    color: location.pathname === item.path ? theme.palette.primary.main : 'inherit',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                <ListItemText 
                  primary={item.title} 
                  sx={{ 
                    opacity: open ? 1 : 0,
                    color: location.pathname === item.path ? theme.palette.primary.main : 'inherit',
                  }} 
                />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </DrawerStyled>
      
      {/* 内容区域 */}
      <ContentWrapper>
        <DrawerHeader />
        
        {/* 面包屑导航 */}
        {generateBreadcrumbs(location.pathname)}
        
        {/* 页面内容 */}
        {children || <Outlet />}
      </ContentWrapper>
    </Box>
  );
};

export default DashboardLayout; 