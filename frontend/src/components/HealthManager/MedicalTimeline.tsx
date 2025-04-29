import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Chip,
  CircularProgress,
  Alert
} from '@mui/material';
import Timeline from '@mui/lab/Timeline';
import TimelineItem from '@mui/lab/TimelineItem';
import TimelineSeparator from '@mui/lab/TimelineSeparator';
import TimelineConnector from '@mui/lab/TimelineConnector';
import TimelineContent from '@mui/lab/TimelineContent';
import TimelineDot from '@mui/lab/TimelineDot';
import TimelineOppositeContent from '@mui/lab/TimelineOppositeContent';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 图标库
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import EventNoteIcon from '@mui/icons-material/EventNote';
import ScienceIcon from '@mui/icons-material/Science';
import MedicationIcon from '@mui/icons-material/Medication';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import HistoryEduIcon from '@mui/icons-material/HistoryEdu';

// 不同类型事件的颜色
const timelineItemColors = {
  health_record: 'primary',
  follow_up: 'secondary',
  vital_sign: 'success',
  lab_result: 'warning',
  medication: 'info',
  rehabilitation: 'primary',
  exercise: 'secondary',
  default: 'default'
};

// 不同类型事件的图标
const timelineItemIcons = {
  health_record: <HistoryEduIcon />,
  follow_up: <EventNoteIcon />,
  vital_sign: <MonitorHeartIcon />,
  lab_result: <ScienceIcon />,
  medication: <MedicationIcon />,
  rehabilitation: <FitnessCenterIcon />,
  exercise: <FitnessCenterIcon />,
  default: <MedicalServicesIcon />
};

interface TimelineEvent {
  id: string;
  item_type: string;
  title: string;
  description?: string;
  timestamp: string;
  metadata?: any;
  color?: string;
  icon?: string;
}

interface MedicalTimelineProps {
  events: TimelineEvent[];
  loading?: boolean;
  error?: string;
  title?: string;
  maxHeight?: string | number;
  onEventClick?: (event: TimelineEvent) => void;
}

const MedicalTimeline: React.FC<MedicalTimelineProps> = ({
  events,
  loading = false,
  error,
  title = '医疗时间线',
  maxHeight = 600,
  onEventClick
}) => {
  // 获取事件类型对应的颜色
  const getColorForEventType = (type: string): 'primary' | 'secondary' | 'success' | 'warning' | 'info' | 'error' | 'default' => {
    return (timelineItemColors[type as keyof typeof timelineItemColors] || timelineItemColors.default) as any;
  };
  
  // 获取事件类型对应的图标
  const getIconForEventType = (type: string) => {
    return timelineItemIcons[type as keyof typeof timelineItemIcons] || timelineItemIcons.default;
  };
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return format(date, 'yyyy年MM月dd日 HH:mm', { locale: zhCN });
    } catch (error) {
      return dateString;
    }
  };
  
  // 处理事件点击
  const handleEventClick = (event: TimelineEvent) => {
    if (onEventClick) {
      onEventClick(event);
    }
  };
  
  return (
    <Paper elevation={2}>
      <Box p={2}>
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
        <Divider sx={{ mb: 2 }} />
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        {loading ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={200}>
            <CircularProgress />
          </Box>
        ) : events.length === 0 ? (
          <Box display="flex" justifyContent="center" alignItems="center" height={100}>
            <Typography color="text.secondary">
              暂无时间线数据
            </Typography>
          </Box>
        ) : (
          <Box sx={{ maxHeight, overflowY: 'auto' }}>
            <Timeline position="right">
              {events.map((event, index) => (
                <TimelineItem key={event.id || index} onClick={() => handleEventClick(event)}>
                  <TimelineOppositeContent color="text.secondary">
                    {formatDate(event.timestamp)}
                  </TimelineOppositeContent>
                  <TimelineSeparator>
                    <TimelineDot color={getColorForEventType(event.item_type)} variant="outlined">
                      {getIconForEventType(event.item_type)}
                    </TimelineDot>
                    {index < events.length - 1 && <TimelineConnector />}
                  </TimelineSeparator>
                  <TimelineContent sx={{ py: '12px', px: 2 }}>
                    <Box
                      sx={{
                        p: 2,
                        border: '1px solid',
                        borderColor: 'divider',
                        borderRadius: 1,
                        '&:hover': {
                          bgcolor: 'action.hover',
                          cursor: onEventClick ? 'pointer' : 'default'
                        }
                      }}
                    >
                      <Typography variant="subtitle1" component="span">
                        {event.title}
                      </Typography>
                      <Chip
                        label={event.item_type.replace('_', ' ')}
                        color={getColorForEventType(event.item_type)}
                        size="small"
                        sx={{ ml: 1 }}
                      />
                      {event.description && (
                        <Typography variant="body2" sx={{ mt: 1 }}>
                          {event.description}
                        </Typography>
                      )}
                      {event.metadata && event.metadata.status && (
                        <Chip
                          label={event.metadata.status}
                          size="small"
                          sx={{ mt: 1 }}
                          variant="outlined"
                        />
                      )}
                    </Box>
                  </TimelineContent>
                </TimelineItem>
              ))}
            </Timeline>
          </Box>
        )}
      </Box>
    </Paper>
  );
};

export default MedicalTimeline; 