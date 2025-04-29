import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import FolderIcon from '@mui/icons-material/Folder';
import EventNoteIcon from '@mui/icons-material/EventNote';
import DevicesIcon from '@mui/icons-material/Devices';
import ChatIcon from '@mui/icons-material/Chat';
import QueryStatsIcon from '@mui/icons-material/QueryStats';

const menuItems = [
  { name: '健康档案', path: '/app/patient/health-records', icon: <FolderIcon /> },
  { name: '日常记录', path: '/app/patient/daily-records', icon: <EventNoteIcon /> },
  { name: '设备绑定', path: '/app/patient/devices', icon: <DevicesIcon /> },
  { name: '医患沟通', path: '/app/patient/communications', icon: <ChatIcon /> },
  { name: '数据统计', path: '/app/patient/statistics', icon: <QueryStatsIcon /> },
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
        <List component="nav" aria-label="patient menu">
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