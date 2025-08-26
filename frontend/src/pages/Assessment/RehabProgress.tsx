import React from 'react';
import {
  Box,
  Typography,
  Container,
  Paper,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Divider,
  Button,
  LinearProgress,
} from '@mui/material';
import TimelineIcon from '@mui/icons-material/Timeline';

const RehabProgress: React.FC = () => {
  // Mock progress data
  const progressData = [
    { id: 1, name: '上肢康复进度', progress: 75, startDate: '2023-05-01', endDate: '2023-07-30' },
    { id: 2, name: '下肢康复进度', progress: 60, startDate: '2023-05-15', endDate: '2023-08-15' },
    { id: 3, name: '日常活动能力', progress: 85, startDate: '2023-04-20', endDate: '2023-07-20' },
  ];

  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <TimelineIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            康复进度评估
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          查看您的康复训练进度和评估结果
        </Typography>
      </Paper>

      <Grid container spacing={3}>
        {/* 当前训练进度 */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>当前训练进度</Typography>
              
              {progressData.map((item) => (
                <Box key={item.id} sx={{ mb: 3 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body1">{item.name}</Typography>
                    <Typography variant="body2" color="primary">{item.progress}%</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={item.progress} 
                    sx={{ height: 10, borderRadius: 5 }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    计划周期: {item.startDate} 至 {item.endDate}
                  </Typography>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grid>

        {/* 最近进度评估 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>最近进度评估</Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="肩关节活动度进步评估" 
                    secondary="2023-06-15 | 进步显著" 
                  />
                  <Button variant="outlined" size="small">详情</Button>
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="下肢力量康复进度" 
                    secondary="2023-06-10 | 稳步提升" 
                  />
                  <Button variant="outlined" size="small">详情</Button>
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="平衡能力提升评估" 
                    secondary="2023-06-01 | 需要加强" 
                  />
                  <Button variant="outlined" size="small">详情</Button>
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* 康复目标 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>康复目标</Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="恢复正常行走能力" 
                    secondary="目标达成率: 75%" 
                  />
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="提升手部精细动作" 
                    secondary="目标达成率: 60%" 
                  />
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="增强核心肌群力量" 
                    secondary="目标达成率: 85%" 
                  />
                </ListItem>
              </List>
              <Box sx={{ mt: 2 }}>
                <Button variant="contained" color="primary">
                  查看完整目标计划
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default RehabProgress; 