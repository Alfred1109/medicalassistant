import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Divider,
} from '@mui/material';

const Statistics: React.FC = () => {
  // 模拟数据
  const stats = {
    patientCount: 45,
    treatmentsThisMonth: 128,
    averageRecoveryTime: 28,
    successRate: 78,
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        康复统计分析
      </Typography>
      
      <Grid container spacing={3}>
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                患者总数
              </Typography>
              <Typography variant="h5" color="primary">
                {stats.patientCount} 位
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                现有康复治疗中的患者总数
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                本月治疗次数
              </Typography>
              <Typography variant="h5" color="primary">
                {stats.treatmentsThisMonth} 次
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                本月进行的康复治疗总次数
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                平均康复时间
              </Typography>
              <Typography variant="h5" color="primary">
                {stats.averageRecoveryTime} 天
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                患者平均康复所需时间
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6} lg={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1">
                康复成功率
              </Typography>
              <Typography variant="h5" color="primary">
                {stats.successRate}%
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">
                康复治疗的成功比例
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              详细统计数据
            </Typography>
            <Typography variant="body1">
              此页面将显示康复治疗的详细统计数据和图表。包括治疗成功率、按疾病类型分类的患者数量、治疗时长分布等。
            </Typography>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary">
                更多图表和数据分析功能将在后续版本中添加。
              </Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Statistics; 