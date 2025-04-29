import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Paper,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import FolderIcon from '@mui/icons-material/Folder';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import EventNoteIcon from '@mui/icons-material/EventNote';
import QueryStatsIcon from '@mui/icons-material/QueryStats';
import ChatIcon from '@mui/icons-material/Chat';
import DescriptionIcon from '@mui/icons-material/Description';

const menuItems = [
  { name: '患者管理', path: '/doctor/patients', icon: <PersonIcon /> },
  { name: '健康档案', path: '/doctor/health-records', icon: <FolderIcon /> },
  { name: '随访管理', path: '/doctor/follow-ups', icon: <EventNoteIcon /> },
  { name: '数据监测', path: '/doctor/monitoring', icon: <MonitorHeartIcon /> },
  { name: '医患沟通', path: '/doctor/communications', icon: <ChatIcon /> },
  { name: '数据统计', path: '/doctor/statistics', icon: <QueryStatsIcon /> },
  { name: '知情同意', path: '/doctor/informed-consent', icon: <DescriptionIcon /> },
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
        <List component="nav" aria-label="doctor menu">
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