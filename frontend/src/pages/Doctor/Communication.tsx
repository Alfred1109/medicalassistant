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
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import PersonIcon from '@mui/icons-material/Person';

const Communication: React.FC = () => {
  // 模拟消息数据
  const [messages, setMessages] = React.useState([
    { id: 1, sender: 'doctor', content: '您好，最近康复训练进展如何？', time: '2023-06-01 09:30' },
    { id: 2, sender: 'patient', content: '医生您好，按照您的建议每天都在坚持做训练，感觉右腿力量有所恢复。', time: '2023-06-01 10:15' },
    { id: 3, sender: 'doctor', content: '很好，请继续保持。下周来复诊时我们再详细评估一下。', time: '2023-06-01 10:30' },
  ]);
  
  const [newMessage, setNewMessage] = React.useState('');
  
  const handleSendMessage = () => {
    if (newMessage.trim()) {
      setMessages([
        ...messages,
        {
          id: messages.length + 1,
          sender: 'doctor',
          content: newMessage,
          time: new Date().toLocaleString()
        }
      ]);
      setNewMessage('');
    }
  };
  
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        患者沟通
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={4}>
          <Paper sx={{ height: '70vh', overflow: 'auto' }}>
            <List>
              {[1, 2, 3, 4, 5].map((patient) => (
                <React.Fragment key={patient}>
                  <ListItem button>
                    <ListItemAvatar>
                      <Avatar>
                        <PersonIcon />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText 
                      primary={`患者 ${patient}`} 
                      secondary="最近一条消息..." 
                    />
                  </ListItem>
                  <Divider />
                </React.Fragment>
              ))}
            </List>
          </Paper>
        </Grid>
        
        <Grid item xs={8}>
          <Paper sx={{ height: '70vh', display: 'flex', flexDirection: 'column' }}>
            <Box sx={{ p: 2, flexGrow: 1, overflow: 'auto' }}>
              {messages.map((message) => (
                <Box 
                  key={message.id}
                  sx={{
                    display: 'flex',
                    justifyContent: message.sender === 'doctor' ? 'flex-end' : 'flex-start',
                    mb: 2
                  }}
                >
                  <Paper 
                    sx={{ 
                      p: 2, 
                      maxWidth: '70%',
                      bgcolor: message.sender === 'doctor' ? 'primary.light' : 'grey.100',
                      color: message.sender === 'doctor' ? 'white' : 'inherit'
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
      </Grid>
    </Box>
  );
};

export default Communication; 