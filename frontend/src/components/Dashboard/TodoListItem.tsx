import React from 'react';
import { 
  ListItem, 
  ListItemText, 
  ListItemIcon, 
  IconButton, 
  Typography, 
  Box
} from '@mui/material';
import Checkbox from '@mui/material/Checkbox';
import { 
  Delete as DeleteIcon, 
  Edit as EditIcon 
} from '@mui/icons-material';
import { Priority } from '../../constants/enums';
import { STATUS_COLORS } from '../../constants/colors';
import { StatusChip } from '../common';

// 优先级对应的MUI颜色
const PRIORITY_COLORS: Record<Priority, 'error' | 'warning' | 'info'> = {
  [Priority.HIGH]: 'error',
  [Priority.MEDIUM]: 'warning',
  [Priority.LOW]: 'info'
};

export interface Todo {
  id: string;
  title: string;
  description?: string;
  dueDate?: string;
  completed: boolean;
  priority: Priority;
}

interface TodoListItemProps {
  todo: Todo;
  onToggleComplete: (id: string) => void;
  onEdit?: (id: string) => void;
  onDelete?: (id: string) => void;
}

const TodoListItem: React.FC<TodoListItemProps> = ({
  todo,
  onToggleComplete,
  onEdit,
  onDelete
}) => {
  const { id, title, description, dueDate, completed, priority } = todo;
  
  // 获取优先级颜色
  const getPriorityColor = (): 'error' | 'warning' | 'info' => {
    return PRIORITY_COLORS[priority] || 'info';
  };
  
  // 格式化日期显示
  const formatDate = (dateString?: string) => {
    if (!dateString) return null;
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN');
  };

  return (
    <ListItem
      secondaryAction={
        <Box>
          {onEdit && (
            <IconButton edge="end" aria-label="编辑" onClick={() => onEdit(id)}>
              <EditIcon />
            </IconButton>
          )}
          {onDelete && (
            <IconButton edge="end" aria-label="删除" onClick={() => onDelete(id)}>
              <DeleteIcon />
            </IconButton>
          )}
        </Box>
      }
    >
      <ListItemIcon>
        <Checkbox
          edge="start"
          checked={completed}
          onChange={() => onToggleComplete(id)}
          disableRipple
        />
      </ListItemIcon>
      <ListItemText
        primary={
          <Box display="flex" alignItems="center">
            <Typography 
              variant="body1" 
              sx={{ 
                textDecoration: completed ? 'line-through' : 'none',
                opacity: completed ? 0.7 : 1,
                mr: 1
              }}
            >
              {title}
            </Typography>
            <StatusChip 
              label={priority} 
              small 
              color={getPriorityColor()} 
            />
          </Box>
        }
        secondary={
          <Box>
            {description && (
              <Typography variant="body2" color="text.secondary">
                {description}
              </Typography>
            )}
            {dueDate && (
              <Typography variant="caption" color="text.secondary">
                截止日期: {formatDate(dueDate)}
              </Typography>
            )}
          </Box>
        }
      />
    </ListItem>
  );
};

export default TodoListItem; 