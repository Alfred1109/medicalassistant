import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import PersonIcon from '@mui/icons-material/Person';
import FolderIcon from '@mui/icons-material/Folder';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import EventNoteIcon from '@mui/icons-material/EventNote';
import QueryStatsIcon from '@mui/icons-material/QueryStats';
import ChatIcon from '@mui/icons-material/Chat';
import TimelineIcon from '@mui/icons-material/Timeline';
import TuneIcon from '@mui/icons-material/Tune';

const menuItems = [
  { name: '患者管理', path: '/app/health-manager/patients', icon: <PersonIcon /> },
  { name: '健康档案', path: '/app/health-manager/health-records', icon: <FolderIcon /> },
  { name: '健康数据时间线', path: '/app/health-manager/health-data-timeline', icon: <TimelineIcon /> },
  { name: '健康数据阈值', path: '/app/health-manager/thresholds', icon: <TuneIcon /> },
  { name: '随访管理', path: '/app/health-manager/follow-ups', icon: <EventNoteIcon /> },
  { name: '数据监测', path: '/app/health-manager/monitoring', icon: <MonitorHeartIcon /> },
  { name: '医患沟通', path: '/app/health-manager/communications', icon: <ChatIcon /> },
  { name: '数据统计', path: '/app/health-manager/statistics', icon: <QueryStatsIcon /> },
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
        <List component="nav" aria-label="health manager menu">
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