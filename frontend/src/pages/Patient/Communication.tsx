import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  TextField,
  Button,
  Divider,
  Card,
  CardContent,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';

const Communication: React.FC = () => {
  // 模拟消息数据
  const [messages, setMessages] = React.useState([
    { id: 1, sender: 'doctor', content: '张先生您好，根据您的康复进度，我建议您增加每天的训练时间。', time: '2023-06-01 09:30' },
    { id: 2, sender: 'patient', content: '好的，医生。我最近感觉右腿力量有所恢复，是否可以尝试新的训练项目？', time: '2023-06-01 10:15' },
    { id: 3, sender: 'doctor', content: '是的，您可以尝试增加轻度的阻力训练。下周复诊时我们再详细评估。', time: '2023-06-01 10:30' },
  ]);
  
  const [newMessage, setNewMessage] = React.useState('');
  
  const handleSendMessage = () => {
    if (newMessage.trim()) {
      setMessages([
        ...messages,
        {
          id: messages.length + 1,
          sender: 'patient',
          content: newMessage,
          time: new Date().toLocaleString()
        }
      ]);
      setNewMessage('');
    }
  };
  
  // 模拟医生数据
  const doctor = {
    name: '王医生',
    title: '主任医师',
    department: '康复科',
    avatar: '',
    lastActive: '今天 10:30'
  };
  
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        医生沟通
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Paper sx={{ height: '70vh', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
              <Typography variant="h6">
                与 {doctor.name} 的对话
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {doctor.title} - {doctor.department}
              </Typography>
            </Box>
            
            <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto' }}>
              {messages.map((message) => (
                <Box 
                  key={message.id}
                  sx={{
                    display: 'flex',
                    justifyContent: message.sender === 'patient' ? 'flex-end' : 'flex-start',
                    mb: 2
                  }}
                >
                  <Paper 
                    sx={{ 
                      p: 2, 
                      maxWidth: '70%',
                      bgcolor: message.sender === 'patient' ? 'primary.light' : 'grey.100',
                      color: message.sender === 'patient' ? 'white' : 'inherit'
                    }}
                  >
                    <Typography variant="body1">{message.content}</Typography>
                    <Typography variant="caption" display="block" sx={{ mt: 1, opacity: 0.7 }}>
                      {message.time}
                    </Typography>
                  </Paper>
                </Box>
              ))}
            </Box>
            
            <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider', display: 'flex' }}>
              <TextField
                fullWidth
                placeholder="输入消息..."
                variant="outlined"
                value={newMessage}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewMessage(e.target.value)}
                onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleSendMessage()}
              />
              <Button 
                variant="contained" 
                endIcon={<SendIcon />}
                sx={{ ml: 1 }}
                onClick={handleSendMessage}
              >
                发送
              </Button>
            </Box>
          </Paper>
        </Grid>
        
        <Grid item xs={12} md={4}>
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <Avatar sx={{ bgcolor: 'primary.main', mr: 2 }}>
                  <LocalHospitalIcon />
                </Avatar>
                <Box>
                  <Typography variant="h6">{doctor.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {doctor.title} · {doctor.department}
                  </Typography>
                </Box>
              </Box>
              <Divider sx={{ mb: 2 }} />
              <Typography variant="body2" gutterBottom>
                最后活动: {doctor.lastActive}
              </Typography>
              <Typography variant="body2">
                联系方式: 工作日 8:00-17:00
              </Typography>
            </CardContent>
          </Card>
          
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              常见问题
            </Typography>
            <List>
              <ListItem button>
                <ListItemText primary="如何正确完成我的康复训练？" />
              </ListItem>
              <Divider />
              <ListItem button>
                <ListItemText primary="什么时候需要联系医生？" />
              </ListItem>
              <Divider />
              <ListItem button>
                <ListItemText primary="如何调整我的康复计划？" />
              </ListItem>
              <Divider />
              <ListItem button>
                <ListItemText primary="如何上传我的训练数据？" />
              </ListItem>
            </List>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Communication; 