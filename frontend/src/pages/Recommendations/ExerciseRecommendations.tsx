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
  Chip,
} from '@mui/material';
import RecommendIcon from '@mui/icons-material/Recommend';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';

interface Exercise {
  id: number;
  name: string;
  category: string;
  description: string;
  difficulty: string;
  duration: string;
  tags: string[];
}

const ExerciseRecommendations: React.FC = () => {
  // 模拟推荐练习数据
  const recommendedExercises: Exercise[] = [
    {
      id: 1,
      name: '肩关节活动度训练',
      category: '上肢训练',
      description: '针对肩周炎患者的肩关节活动度恢复训练',
      difficulty: '中等',
      duration: '15分钟',
      tags: ['肩关节', '活动度', '中期恢复'],
    },
    {
      id: 2,
      name: '下肢力量恢复',
      category: '下肢训练',
      description: '适合髋关节和膝关节术后患者的下肢力量恢复训练',
      difficulty: '低强度',
      duration: '20分钟',
      tags: ['下肢', '力量', '初期恢复'],
    },
    {
      id: 3,
      name: '平衡能力训练',
      category: '平衡训练',
      description: '适合中风后患者的平衡能力训练，有助于改善行走稳定性',
      difficulty: '高强度',
      duration: '15分钟',
      tags: ['平衡', '稳定性', '晚期恢复'],
    },
    {
      id: 4,
      name: '手指灵活度训练',
      category: '上肢训练',
      description: '适合手部关节炎或手术后患者的手指灵活度训练',
      difficulty: '低强度',
      duration: '10分钟',
      tags: ['手部', '灵活度', '精细动作'],
    },
  ];

  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <RecommendIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            训练推荐
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          基于您的康复计划和健康状况，系统为您推荐的个性化训练项目
        </Typography>
      </Paper>

      <Grid container spacing={3}>
        {/* 推荐训练列表 */}
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom sx={{ pl: 1 }}>
            推荐训练列表
          </Typography>
          
          {recommendedExercises.map((exercise) => (
            <Card key={exercise.id} sx={{ mb: 2 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <FitnessCenterIcon color="primary" sx={{ mr: 1 }} />
                      <Typography variant="h6">{exercise.name}</Typography>
                    </Box>
                    
                    <Typography variant="body2" color="text.secondary" paragraph>
                      {exercise.description}
                    </Typography>
                    
                    <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                      <Typography variant="body2">
                        <strong>难度:</strong> {exercise.difficulty}
                      </Typography>
                      <Typography variant="body2">
                        <strong>时长:</strong> {exercise.duration}
                      </Typography>
                      <Typography variant="body2">
                        <strong>类别:</strong> {exercise.category}
                      </Typography>
                    </Box>
                    
                    <Box sx={{ mb: 1 }}>
                      {exercise.tags.map((tag, index) => (
                        <Chip 
                          key={index} 
                          label={tag} 
                          size="small" 
                          color="primary" 
                          variant="outlined" 
                          sx={{ mr: 0.5 }} 
                        />
                      ))}
                    </Box>
                  </Box>
                  
                  <Box>
                    <Button variant="contained" color="primary">
                      开始训练
                    </Button>
                    <Button variant="outlined" sx={{ mt: 1, display: 'block' }}>
                      查看详情
                    </Button>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          ))}
        </Grid>
        
        {/* 训练推荐历史 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>历史推荐</Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="颈椎康复训练" 
                    secondary="推荐时间: 2023-06-01" 
                  />
                  <Button variant="outlined" size="small">查看</Button>
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="腰椎稳定性训练" 
                    secondary="推荐时间: 2023-05-15" 
                  />
                  <Button variant="outlined" size="small">查看</Button>
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>
        
        {/* 训练效果反馈 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>训练效果反馈</Typography>
              <Typography variant="body2" paragraph>
                完成训练后请对训练效果进行评价，系统将根据您的反馈优化推荐
              </Typography>
              <Button variant="contained" color="primary">
                提交训练反馈
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default ExerciseRecommendations; 