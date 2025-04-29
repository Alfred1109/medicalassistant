import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import PeopleIcon from '@mui/icons-material/People';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import BusinessIcon from '@mui/icons-material/Business';
import LabelIcon from '@mui/icons-material/Label';
import DevicesIcon from '@mui/icons-material/Devices';
import InsightsIcon from '@mui/icons-material/Insights';

const menuItems = [
  { name: '医生管理', path: '/admin/doctors', icon: <LocalHospitalIcon /> },
  { name: '患者管理', path: '/admin/patients', icon: <PeopleIcon /> },
  { name: '健管师管理', path: '/admin/health-managers', icon: <HealthAndSafetyIcon /> },
  { name: '组织机构', path: '/admin/organizations', icon: <BusinessIcon /> },
  { name: '标签管理', path: '/admin/tags', icon: <LabelIcon /> },
  { name: '设备查看', path: '/admin/devices', icon: <DevicesIcon /> },
  { name: '数据可视化', path: '/admin/visualization', icon: <InsightsIcon /> },
];

const SideMenu: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  const handleMenuClick = (path: string) => {
    navigate(path);
  };
  
  return (
    <Paper elevation={1} sx={{ height: '100%' }}>
      <Box sx={{ width: '100%', bgcolor: 'background.paper' }}>
        <List component="nav" aria-label="admin menu">
          {menuItems.map((item) => (
            <ListItem key={item.path} disablePadding>
              <ListItemButton
                selected={location.pathname.startsWith(item.path)}
                onClick={() => handleMenuClick(item.path)}
              >
                <ListItemIcon>{item.icon}</ListItemIcon>
                <ListItemText primary={item.name} />
              </ListItemButton>
            </ListItem>
          ))}
        </List>
      </Box>
    </Paper>
  );
};

export default SideMenu; 