import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  List,
  ListItem,
  Paper,
} from '@mui/material';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import PersonIcon from '@mui/icons-material/Person';
import FolderIcon from '@mui/icons-material/Folder';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import EventNoteIcon from '@mui/icons-material/EventNote';
import QueryStatsIcon from '@mui/icons-material/QueryStats';
import ChatIcon from '@mui/icons-material/Chat';
import DescriptionIcon from '@mui/icons-material/Description';

const menuItems = [
  { name: '患者管理', path: '/app/doctor/patients', icon: <PersonIcon /> },
  { name: '健康档案', path: '/app/doctor/health-records', icon: <FolderIcon /> },
  { name: '随访管理', path: '/app/doctor/follow-ups', icon: <EventNoteIcon /> },
  { name: '数据监测', path: '/app/doctor/monitoring', icon: <MonitorHeartIcon /> },
  { name: '医患沟通', path: '/app/doctor/communications', icon: <ChatIcon /> },
  { name: '数据统计', path: '/app/doctor/statistics', icon: <QueryStatsIcon /> },
  { name: '知情同意', path: '/app/doctor/informed-consent', icon: <DescriptionIcon /> },
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