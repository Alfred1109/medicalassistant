import React, { useState, useEffect, useCallback, useRef } from 'react';
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
  alpha,
  Badge,
  Chip,
  TextField,
  InputAdornment,
  Paper
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
  Description as DescriptionIcon,
  Assessment as AssessmentIcon,
  InfoOutlined as InfoOutlinedIcon,
  Star as StarIcon,
  History as HistoryIcon,
  Settings as SettingsIcon,
  Accessibility as AccessibilityIcon,
  DirectionsRun as DirectionsRunIcon,
  Favorite as FavoriteIcon,
  Schedule as ScheduleIcon,
  TrendingUp as TrendingUpIcon,
  Assignment as AssignmentIcon,
  Search as SearchIcon,
  Notifications as NotificationsIcon
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { toggleSidebar } from '../../store/slices/uiSlice';

// Drawer width for desktop
const DRAWER_WIDTH = 260;

// 移动端抽屉与菜单过渡延迟时间
const DRAWER_TRANSITION_DELAY = 225;
const MENU_TRANSITION_DELAY = 100;

// 菜单项接口
interface MenuItem {
  name: string;
  path: string;
  icon: React.ReactNode;
  roles?: string[];
  children?: MenuItem[];
  badge?: string | number;
  chip?: {
    text: string;
    color: 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';
  };
}

// 性能优化：将MenuItem渲染逻辑提取为单独组件
const MenuItemComponent: React.FC<{
  item: MenuItem;
  isNested?: boolean;
  onNavigate: (path: string) => void;
}> = React.memo(({ item, isNested = false, onNavigate }) => {
  const location = useLocation();
  const theme = useTheme();
  
  const isSelected = location.pathname === item.path || 
                     (item.path !== '/app' && location.pathname.startsWith(item.path + '/'));
  
  return (
    <ListItem disablePadding>
      <ListItemButton
        selected={isSelected}
        onClick={() => onNavigate(item.path)}
        sx={{
          pl: isNested ? 4 : 2,
          minHeight: isNested ? 40 : 48,
          '&.Mui-selected': {
            backgroundColor: alpha(theme.palette.primary.main, 0.1),
            '&:hover': {
              backgroundColor: alpha(theme.palette.primary.main, 0.2),
            }
          }
        }}
      >
        <ListItemIcon sx={{ 
          color: isSelected ? 'primary.main' : 'inherit',
          minWidth: isNested ? 36 : 40 
        }}>
          {item.badge ? (
            <Badge badgeContent={item.badge} color="error">
              {item.icon}
            </Badge>
          ) : (
            item.icon
          )}
        </ListItemIcon>
        <ListItemText 
          primary={item.name} 
          primaryTypographyProps={{
            fontSize: isNested ? '0.875rem' : 'inherit',
            fontWeight: isSelected ? 500 : 400
          }}
        />
        {item.chip && (
          <Chip 
            label={item.chip.text} 
            color={item.chip.color} 
            size="small" 
            sx={{ 
              height: 20, 
              fontSize: '0.625rem',
              ml: 0.5
            }}
          />
        )}
      </ListItemButton>
    </ListItem>
  );
});

// 性能优化：将SubmenuItem渲染逻辑提取为单独组件
const SubmenuItemComponent: React.FC<{
  item: MenuItem;
  isOpen: boolean;
  onToggle: () => void;
  onNavigate: (path: string) => void;
}> = React.memo(({ item, isOpen, onToggle, onNavigate }) => {
  const location = useLocation();
  const theme = useTheme();
  
  const isActive = location.pathname.startsWith(item.path);
  
  return (
    <React.Fragment>
      <ListItem disablePadding>
        <ListItemButton
          onClick={onToggle}
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
            {item.badge ? (
              <Badge badgeContent={item.badge} color="error">
                {item.icon}
              </Badge>
            ) : (
              item.icon
            )}
          </ListItemIcon>
          <ListItemText 
            primary={item.name} 
            primaryTypographyProps={{
              fontWeight: isActive ? 500 : 400
            }}
          />
          {item.chip && (
            <Chip 
              label={item.chip.text} 
              color={item.chip.color} 
              size="small" 
              sx={{ ml: 1, height: 20, fontSize: '0.625rem' }}
            />
          )}
          {isOpen ? <ExpandLess /> : <ExpandMore />}
        </ListItemButton>
      </ListItem>
      <Collapse in={isOpen} timeout="auto" unmountOnExit>
        <List component="div" disablePadding>
          {item.children?.map(child => (
            <MenuItemComponent 
              key={child.path}
              item={child}
              isNested
              onNavigate={onNavigate}
            />
          ))}
        </List>
      </Collapse>
    </React.Fragment>
  );
});

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
  
  // 新增：记录最近访问页面历史
  const [recentPages, setRecentPages] = useState<MenuItem[]>(() => {
    const saved = localStorage.getItem('recentPages');
    return saved ? JSON.parse(saved) : [];
  });
  
  // 新增：搜索菜单功能
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  
  // 新增：记忆菜单展开状态
  useEffect(() => {
    const savedOpenMenus = localStorage.getItem('openMenus');
    if (savedOpenMenus) {
      setOpenSubmenu(JSON.parse(savedOpenMenus));
    }
  }, []);
  
  // 根据当前路径自动打开子菜单
  useEffect(() => {
    const path = location.pathname;
    let newOpenSubmenu = null;
    
    if (path.includes('/app/admin')) {
      newOpenSubmenu = 'admin';
    } else if (path.includes('/app/doctor')) {
      newOpenSubmenu = 'doctor';
    } else if (path.includes('/app/patient')) {
      newOpenSubmenu = 'patient';
    } else if (path.includes('/app/health-manager')) {
      newOpenSubmenu = 'health-manager';
    } else if (path.includes('/app/rehab')) {
      newOpenSubmenu = 'rehabilitation';
    } else if (path.includes('/app/assessment')) {
      newOpenSubmenu = 'rehabilitation';
    } else if (path.includes('/app/exercise')) {
      newOpenSubmenu = 'rehabilitation';
    } else if (path.includes('/app/progress')) {
      newOpenSubmenu = 'rehabilitation';
    } else if (path.includes('/app/agent')) {
      newOpenSubmenu = 'ai-assistant';
    } else if (path.includes('/app/rehab-guidance')) {
      newOpenSubmenu = 'ai-assistant';
    }
    
    if (newOpenSubmenu) {
      setOpenSubmenu(newOpenSubmenu);
      localStorage.setItem('openMenus', JSON.stringify(newOpenSubmenu));
    }
    
    // 更新最近访问记录
    updateRecentPages(path);
  }, [location.pathname]);
  
  // 新增：更新最近访问页面
  const updateRecentPages = (path: string) => {
    // 所有菜单项平铺
    const allMenuItems: MenuItem[] = [
      ...baseMenuItems,
      ...baseMenuItems.flatMap(item => item.children || []),
      ...filteredRoleMenuItems.flatMap(item => item.children || [])
    ];
    
    const currentPage = allMenuItems.find(item => item.path === path);
    if (currentPage) {
      const newRecentPages = [
        currentPage,
        ...recentPages.filter(page => page.path !== currentPage.path)
      ].slice(0, 5); // 只保留最近5个
      
      setRecentPages(newRecentPages);
      localStorage.setItem('recentPages', JSON.stringify(newRecentPages));
    }
  };
  
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
    const newOpenSubmenu = openSubmenu === menuId ? null : menuId;
    setOpenSubmenu(newOpenSubmenu);
    localStorage.setItem('openMenus', JSON.stringify(newOpenSubmenu));
  };
  
  // 新增：搜索菜单处理
  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  };
  
  // 搜索菜单结果
  const getSearchResults = () => {
    if (!searchQuery.trim()) return [];
    
    const query = searchQuery.toLowerCase();
    const allMenuItems: MenuItem[] = [
      ...baseMenuItems,
      ...baseMenuItems.flatMap(item => item.children || []),
      ...filteredRoleMenuItems.flatMap(item => item.children || [])
    ];
    
    return allMenuItems.filter(item => 
      item.name.toLowerCase().includes(query)
    ).slice(0, 5);
  };
  
  // 基础菜单项
  const baseMenuItems: MenuItem[] = [
    { name: '首页', path: '/app/dashboard', icon: <HomeIcon /> },
    { 
      name: '康复中心', 
      path: '/app/rehabilitation', 
      icon: <AccessibilityIcon />,
      children: [
        { name: '康复计划', path: '/app/rehab-plans', icon: <FitnessCenterIcon /> },
        { name: '康复评估', path: '/app/assessments', icon: <AssessmentIcon /> },
        { name: '训练记录', path: '/app/exercise-logs', icon: <DirectionsRunIcon /> },
        { name: '进度报告', path: '/app/progress-reports', icon: <TrendingUpIcon /> },
      ]
    },
    { 
      name: '智能助手', 
      path: '/app/ai-assistant', 
      icon: <PsychologyIcon />,
      children: [
        { name: '智能问答', path: '/app/agents', icon: <StarIcon /> },
        { name: '训练推荐', path: '/app/exercise-recommendations', icon: <FavoriteIcon /> },
        { name: '康复指导', path: '/app/rehab-guidance', icon: <InfoOutlinedIcon /> },
      ] 
    },
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
        { name: '康复方案管理', path: '/app/admin/rehab-templates', icon: <AssignmentIcon />, chip: { text: '新', color: 'success' } },
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
        { name: '康复评估', path: '/app/doctor/assessments', icon: <AssessmentIcon />, chip: { text: '新', color: 'success' } },
        { name: '康复处方', path: '/app/doctor/prescriptions', icon: <FitnessCenterIcon />, chip: { text: '新', color: 'success' } },
        { name: '知情同意', path: '/app/doctor/informed-consent', icon: <DescriptionIcon /> },
      ]
    },
    { 
      name: '患者中心', 
      path: '/app/patient', 
      icon: <PatientIcon />, 
      roles: ['patient'],
      children: [
        { name: '康复任务', path: '/app/patient/rehab-tasks', icon: <ScheduleIcon />, badge: 3 },
        { name: '健康档案', path: '/app/patient/health-records', icon: <FolderIcon /> },
        { name: '日常记录', path: '/app/patient/daily-records', icon: <EventNoteIcon /> },
        { name: '康复进度', path: '/app/patient/rehab-progress', icon: <TrendingUpIcon />, chip: { text: '新', color: 'success' } },
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
        { name: '康复计划监督', path: '/app/health-manager/rehab-monitoring', icon: <AssessmentIcon />, chip: { text: '新', color: 'success' } },
        { name: '医患沟通', path: '/app/health-manager/communications', icon: <ChatIcon /> },
        { name: '数据统计', path: '/app/health-manager/statistics', icon: <QueryStatsIcon /> },
      ]
    },
  ];
  
  // 过滤当前用户可见的角色菜单
  const filteredRoleMenuItems = roleMenuItems.filter(item => 
    !item.roles || item.roles.includes(userRole)
  );
  
  // 新增：角色个性化配置
  const roleConfig = {
    admin: {
      color: theme.palette.error.main,
      icon: <AdminIcon />,
      defaultPath: '/app/admin',
      label: '系统管理员'
    },
    doctor: {
      color: theme.palette.primary.main,
      icon: <DoctorIcon />,
      defaultPath: '/app/doctor',
      label: '医生'
    },
    patient: {
      color: theme.palette.success.main,
      icon: <PatientIcon />,
      defaultPath: '/app/patient',
      label: '患者'
    },
    health_manager: {
      color: theme.palette.warning.main,
      icon: <HealthManagerIcon />,
      defaultPath: '/app/health-manager',
      label: '健康管理师'
    }
  };
  
  // 获取当前用户角色配置
  const currentRoleConfig = userRole ? roleConfig[userRole as keyof typeof roleConfig] : null;
  
  // 使用角色默认路径
  useEffect(() => {
    // 如果用户访问的是根路径，重定向到角色默认页面
    if (location.pathname === '/app' && currentRoleConfig) {
      navigate(currentRoleConfig.defaultPath);
    }
  }, [location.pathname, currentRoleConfig, navigate]);
  
  // 新增：控制移动端抽屉开关动画
  const [drawerIsOpen, setDrawerIsOpen] = useState(false);
  
  // 优化：处理抽屉开关动画
  useEffect(() => {
    if (isMobile) {
      if (sidebarOpen) {
        setDrawerIsOpen(true);
      } else {
        // 延迟关闭抽屉，让动画有时间完成
        const timer = setTimeout(() => {
          setDrawerIsOpen(false);
        }, DRAWER_TRANSITION_DELAY);
        
        return () => clearTimeout(timer);
      }
    } else {
      setDrawerIsOpen(true);
    }
  }, [sidebarOpen, isMobile]);
  
  // 优化：当菜单项渲染数量较多时，采用懒加载
  const renderMenuItems = useCallback((items: MenuItem[]) => {
    return items.map(item => {
      if (item.children) {
        const isSubmenuOpen = openSubmenu === item.path.split('/').pop();
        
        return (
          <SubmenuItemComponent
            key={item.path}
            item={item}
            isOpen={!!isSubmenuOpen}
            onToggle={() => handleSubmenuToggle(item.path.split('/').pop() || '')}
            onNavigate={handleNavigate}
          />
        );
      }
      
      return (
        <MenuItemComponent
          key={item.path}
          item={item}
          onNavigate={handleNavigate}
        />
      );
    });
  }, [openSubmenu, handleSubmenuToggle, handleNavigate]);
  
  // 优化菜单滚动性能
  const drawerContentRef = useRef<HTMLDivElement>(null);
  
  // 优化：使用ResizeObserver监听窗口尺寸变化
  useEffect(() => {
    function updateDrawerScroll() {
      if (drawerContentRef.current) {
        const content = drawerContentRef.current;
        content.style.maxHeight = `${window.innerHeight - 200}px`;
      }
    }
    
    // 初始更新
    updateDrawerScroll();
    
    // 创建ResizeObserver
    if (typeof ResizeObserver !== 'undefined') {
      const resizeObserver = new ResizeObserver(() => {
        updateDrawerScroll();
      });
      
      if (drawerContentRef.current) {
        resizeObserver.observe(drawerContentRef.current);
      }
      
      return () => {
        resizeObserver.disconnect();
      };
    } else {
      // 降级处理：使用传统resize事件
      window.addEventListener('resize', updateDrawerScroll);
      return () => {
        window.removeEventListener('resize', updateDrawerScroll);
      };
    }
  }, [drawerContentRef]);
  
  // 抽屉内容
  const drawerContent = (
    <>
      <Box sx={{ 
        px: 2, 
        py: 3, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        borderBottom: `1px solid ${theme.palette.divider}`,
        ...(currentRoleConfig && {
          background: `linear-gradient(to right, ${alpha(currentRoleConfig.color, 0.05)}, transparent)`
        })
      }}>
        <Typography variant="h6" component="h1" sx={{ 
          fontWeight: 'bold',
          background: currentRoleConfig 
            ? `linear-gradient(45deg, ${currentRoleConfig.color} 30%, ${theme.palette.secondary.main} 90%)`
            : `linear-gradient(45deg, ${theme.palette.primary.main} 30%, ${theme.palette.secondary.main} 90%)`,
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
        }}>
          医疗康复智能助手
        </Typography>
        {isMobile && (
          <IconButton onClick={handleDrawerToggle} size="small">
            <ChevronLeftIcon />
          </IconButton>
        )}
      </Box>
      
      <Box sx={{ mb: 2, px: 2, pt: 2 }}>
        <TextField
          fullWidth
          placeholder="搜索菜单..."
          size="small"
          variant="outlined"
          value={searchQuery}
          onChange={handleSearchChange}
          onFocus={() => setIsSearching(true)}
          onBlur={() => setTimeout(() => setIsSearching(false), 200)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: 2,
            }
          }}
        />
        
        {isSearching && searchQuery && (
          <Paper 
            elevation={3} 
            sx={{ 
              position: 'absolute', 
              width: 'calc(100% - 32px)', 
              mt: 0.5, 
              zIndex: 1100,
              maxHeight: 300,
              overflow: 'auto'
            }}
          >
            <List dense>
              {getSearchResults().map(item => (
                <ListItem key={item.path} disablePadding>
                  <ListItemButton 
                    onClick={() => {
                      handleNavigate(item.path);
                      setSearchQuery('');
                    }}
                    sx={{ py: 1 }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText 
                      primary={item.name} 
                      primaryTypographyProps={{ fontSize: '0.875rem' }}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
              {getSearchResults().length === 0 && (
                <ListItem sx={{ py: 1 }}>
                  <ListItemText 
                    primary="无匹配结果" 
                    primaryTypographyProps={{ 
                      fontSize: '0.875rem',
                      fontStyle: 'italic',
                      color: 'text.secondary',
                      textAlign: 'center'
                    }}
                  />
                </ListItem>
              )}
            </List>
          </Paper>
        )}
      </Box>
      
      {/* 最近访问 */}
      {recentPages.length > 0 && (
        <Box sx={{ mb: 2 }}>
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
            最近访问
          </Typography>
          <List dense>
            {recentPages.map(page => (
              <ListItem key={page.path} disablePadding>
                <ListItemButton 
                  onClick={() => handleNavigate(page.path)}
                  selected={location.pathname === page.path}
                  sx={{ 
                    pl: 3,
                    minHeight: 42,
                    '&.Mui-selected': {
                      backgroundColor: alpha(theme.palette.primary.main, 0.1),
                    }
                  }}
                >
                  <ListItemIcon sx={{ 
                    minWidth: 36,
                    color: location.pathname === page.path ? 'primary.main' : 'inherit' 
                  }}>
                    <HistoryIcon fontSize="small" />
                  </ListItemIcon>
                  <ListItemText 
                    primary={page.name} 
                    primaryTypographyProps={{ 
                      fontSize: '0.8125rem',
                      fontWeight: location.pathname === page.path ? 'medium' : 'normal'
                    }}
                  />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
          <Divider sx={{ mx: 2, my: 1 }} />
        </Box>
      )}
      
      <Box 
        ref={drawerContentRef}
        sx={{ 
          overflowY: 'auto',
          overflowX: 'hidden',
          flexGrow: 1,
          // 采用硬件加速，优化滚动性能
          WebkitOverflowScrolling: 'touch',
          '&::-webkit-scrollbar': {
            width: 6,
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: alpha(theme.palette.text.secondary, 0.2),
            borderRadius: 3,
          }
        }}
      >
        {/* 基础菜单，使用记忆化渲染 */}
        <List component="nav" aria-label="basic menu" sx={{ mb: 1 }}>
          {renderMenuItems(baseMenuItems)}
        </List>
        
        {/* 用户角色相关菜单，使用记忆化渲染 */}
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
              {renderMenuItems(filteredRoleMenuItems)}
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
        <ListItem disablePadding>
          <ListItemButton
            onClick={() => handleNavigate('/app/settings')}
            selected={location.pathname === '/app/settings'}
            sx={{
              '&.Mui-selected': {
                backgroundColor: alpha(theme.palette.primary.main, 0.1),
                '&:hover': {
                  backgroundColor: alpha(theme.palette.primary.main, 0.2),
                }
              }
            }}
          >
            <ListItemIcon sx={{ color: location.pathname === '/app/settings' ? 'primary.main' : 'inherit' }}>
              <SettingsIcon />
            </ListItemIcon>
            <ListItemText primary="系统设置" />
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
          color: 'text.primary',
          transition: theme.transitions.create(['width', 'margin'], {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.leavingScreen,
          }),
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            aria-label="open drawer"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ 
              mr: 2,
              ...(currentRoleConfig && {
                color: currentRoleConfig.color
              })
            }}
          >
            <MenuIcon />
          </IconButton>
          
          <Box sx={{ display: { xs: 'none', sm: 'block' } }}>
            <Typography variant="h6" noWrap sx={{ 
              flexGrow: 1, 
              fontWeight: 'bold',
              background: currentRoleConfig 
                ? `linear-gradient(45deg, ${currentRoleConfig.color} 30%, ${theme.palette.secondary.main} 90%)`
                : `linear-gradient(45deg, ${theme.palette.primary.main} 30%, ${theme.palette.secondary.main} 90%)`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              医疗康复智能助手
            </Typography>
          </Box>
          
          <Box sx={{ flexGrow: 1 }} />
          
          {/* 角色指示器 */}
          {currentRoleConfig && (
            <Chip
              icon={React.cloneElement(currentRoleConfig.icon as React.ReactElement, { 
                style: { color: 'inherit' },
                fontSize: "small"
              })}
              label={currentRoleConfig.label}
              size="small"
              sx={{ 
                mr: 2, 
                bgcolor: alpha(currentRoleConfig.color, 0.1),
                color: currentRoleConfig.color,
                borderColor: alpha(currentRoleConfig.color, 0.3),
                '& .MuiChip-icon': { color: currentRoleConfig.color },
                display: { xs: 'none', sm: 'flex' }
              }}
              variant="outlined"
            />
          )}
          
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Tooltip title="通知中心">
              <IconButton
                color="inherit"
                sx={{ position: 'relative', mr: 1 }}
                onClick={() => navigate('/app/notifications')}
              >
                <Badge badgeContent={3} color="error">
                  <NotificationsIcon />
                </Badge>
              </IconButton>
            </Tooltip>
            
            <Tooltip title="个人中心">
              <IconButton
                onClick={handleMenuOpen}
                size="small"
                sx={{ 
                  ml: 1,
                  border: currentRoleConfig ? 
                    `1px solid ${alpha(currentRoleConfig.color, 0.5)}` : 
                    `1px solid ${theme.palette.divider}`,
                  p: 0.5
                }}
                aria-controls="account-menu"
                aria-haspopup="true"
              >
                <Avatar 
                  sx={{ 
                    width: 32, 
                    height: 32, 
                    bgcolor: currentRoleConfig ? 
                      alpha(currentRoleConfig.color, 0.8) : 
                      alpha(theme.palette.primary.main, 0.8)
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
                minWidth: 200,
                overflow: 'visible',
                filter: 'drop-shadow(0px 2px 8px rgba(0,0,0,0.08))',
                mt: 1.5,
                '& .MuiMenuItem-root': {
                  px: 2,
                  py: 1,
                },
              },
            }}
            TransitionProps={{
              // 为菜单添加过渡动画
              timeout: MENU_TRANSITION_DELAY
            }}
          >
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 'medium' }}>
                {user?.name || 'User'}
              </Typography>
              <Typography 
                variant="body2" 
                sx={{ 
                  color: currentRoleConfig?.color || 'text.secondary',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5
                }}
              >
                {currentRoleConfig?.icon}
                {currentRoleConfig?.label || '用户'}
              </Typography>
            </Box>
            <Divider />
            <MenuItem onClick={() => { handleMenuClose(); navigate('/app/profile'); }}>
              <ListItemIcon>
                <PersonIcon fontSize="small" />
              </ListItemIcon>
              个人资料
            </MenuItem>
            <MenuItem onClick={() => { handleMenuClose(); navigate('/app/notifications'); }}>
              <ListItemIcon>
                <Badge badgeContent={3} color="error" sx={{ '& .MuiBadge-badge': { right: -3, top: 3 } }}>
                  <NotificationsIcon fontSize="small" />
                </Badge>
              </ListItemIcon>
              通知中心
            </MenuItem>
            <MenuItem onClick={() => { handleMenuClose(); navigate('/app/settings'); }}>
              <ListItemIcon>
                <SettingsIcon fontSize="small" />
              </ListItemIcon>
              设置
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
            display: drawerIsOpen ? 'flex' : 'none', // 控制抽屉动画
            flexDirection: 'column',
            ...(currentRoleConfig && {
              borderRight: `3px solid ${alpha(currentRoleConfig.color, 0.2)}`
            })
          },
        }}
        // 为抽屉添加过渡动画
        transitionDuration={{
          enter: DRAWER_TRANSITION_DELAY,
          exit: DRAWER_TRANSITION_DELAY
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