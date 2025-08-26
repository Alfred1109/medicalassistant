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
} from '@mui/material';
import AssessmentIcon from '@mui/icons-material/Assessment';

const RehabAssessment: React.FC = () => {
  return (
    <Container maxWidth="lg">
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AssessmentIcon color="primary" sx={{ mr: 2, fontSize: 32 }} />
          <Typography variant="h5" component="h1">
            康复评估报告
          </Typography>
        </Box>
        <Typography variant="body1" color="text.secondary" paragraph>
          查看患者康复评估报告和评估结果
        </Typography>
      </Paper>

      <Grid container spacing={3}>
        {/* 最近的评估 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>最近评估</Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="肩关节活动度评估" 
                    secondary="2023-06-15 | 医生: 张医生" 
                  />
                  <Button variant="outlined" size="small">查看</Button>
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="下肢康复进度评估" 
                    secondary="2023-06-10 | 医生: 李医生" 
                  />
                  <Button variant="outlined" size="small">查看</Button>
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="日常活动能力评估" 
                    secondary="2023-06-01 | 医生: 王医生" 
                  />
                  <Button variant="outlined" size="small">查看</Button>
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* 评估指标 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>评估指标概览</Typography>
              <Typography variant="body1" paragraph>
                以下是您的康复评估关键指标:
              </Typography>
              <List>
                <ListItem>
                  <ListItemText 
                    primary="关节活动度" 
                    secondary="较上次评估提升 15%" 
                  />
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="肌肉力量" 
                    secondary="较上次评估提升 8%" 
                  />
                </ListItem>
                <Divider />
                <ListItem>
                  <ListItemText 
                    primary="日常活动能力" 
                    secondary="较上次评估提升 20%" 
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* 评估历史 */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>评估历史记录</Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                您可以查看所有历史评估报告和详细数据
              </Typography>
              <Button variant="contained" color="primary">
                查看所有评估历史
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default RehabAssessment; 