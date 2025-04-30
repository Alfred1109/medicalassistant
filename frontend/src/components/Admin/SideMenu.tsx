import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Divider,
  Typography,
  Paper
} from '@mui/material';
import {
  PeopleAlt as PeopleIcon,
  Person as PersonIcon,
  HealthAndSafety as HealthIcon,
  Business as BusinessIcon,
  Label as TagIcon,
  Devices as DevicesIcon,
  Insights as InsightsIcon,
  History as HistoryIcon
} from '@mui/icons-material';

// 导航菜单项
const menuItems = [
  { 
    id: 'doctors', 
    label: '医生管理', 
    icon: <PeopleIcon />, 
    path: '/app/admin/doctors' 
  },
  { 
    id: 'patients', 
    label: '患者管理', 
    icon: <PersonIcon />, 
    path: '/app/admin/patients' 
  },
  { 
    id: 'health-managers', 
    label: '健康管理师', 
    icon: <HealthIcon />, 
    path: '/app/admin/health-managers' 
  },
  { 
    id: 'organizations', 
    label: '机构管理', 
    icon: <BusinessIcon />, 
    path: '/app/admin/organizations' 
  },
  { 
    id: 'tags', 
    label: '标签管理', 
    icon: <TagIcon />, 
    path: '/app/admin/tags' 
  },
  { 
    id: 'devices', 
    label: '设备管理', 
    icon: <DevicesIcon />, 
    path: '/app/admin/devices' 
  },
  { 
    id: 'visualization', 
    label: '数据可视化', 
    icon: <InsightsIcon />, 
    path: '/app/admin/visualization' 
  },
  { 
    id: 'audit-logs', 
    label: '审计日志', 
    icon: <HistoryIcon />, 
    path: '/app/admin/audit-logs' 
  }
];

const SideMenu: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        height: '100%',
        borderRadius: 0,
      }}
    >
      <Box p={2}>
        <Typography variant="subtitle1" fontWeight="medium" color="text.secondary">
          系统管理
        </Typography>
      </Box>
      <Divider />
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.id} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => navigate(item.path)}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: 'rgba(25, 118, 210, 0.08)',
                }
              }}
            >
              <ListItemIcon>
                {item.icon}
              </ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </Paper>
  );
};

export default SideMenu; 