import React, { useEffect, useState } from 'react';
import { Box, Typography, Grid, Paper, Button, Divider, useTheme, useMediaQuery } from '@mui/material';
import DashboardLayout from '../../components/Layout/DashboardLayout';
import DashboardStatistics from '../../components/Dashboard/DashboardStatistics';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { Refresh as RefreshIcon, Favorite as FavoriteIcon } from '@mui/icons-material';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

const Dashboard: React.FC = () => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [currentDate, setCurrentDate] = useState<string>('');
  const [greeting, setGreeting] = useState<string>('');
  const { user } = useSelector((state: RootState) => state.auth);
  
  // 获取当前日期和问候语
  useEffect(() => {
    // 格式化日期，使用中文locale
    const now = new Date();
    setCurrentDate(format(now, 'yyyy年MM月dd日 EEEE', { locale: zhCN }));
    
    // 根据时间设置问候语
    const hour = now.getHours();
    if (hour >= 5 && hour < 12) {
      setGreeting('早上好');
    } else if (hour >= 12 && hour < 18) {
      setGreeting('下午好');
    } else {
      setGreeting('晚上好');
    }
  }, []);
  
  // 用户角色标题映射
  const roleTitle = {
    doctor: '医生',
    patient: '患者',
    healthManager: '健康管理师',
    admin: '系统管理员'
  };
  
  // 健康小贴士数据
  const healthTips = [
    '规律运动对康复有显著帮助，每天30分钟适度运动是基础。',
    '均衡饮食对身体恢复至关重要，增加蛋白质和蔬果摄入。',
    '充足的睡眠有助于身体自我修复，建议每晚7-8小时。',
    '保持积极乐观的心态可以加速康复进程，减轻焦虑和压力。',
    '听从医嘱按时服药和复诊，确保治疗计划有效执行。'
  ];
  
  // 随机选择一条健康小贴士
  const randomTip = healthTips[Math.floor(Math.random() * healthTips.length)];
  
  return (
    <DashboardLayout>
      <Box>
        {/* 顶部欢迎区域 */}
        <Paper 
          elevation={0} 
          sx={{ 
            p: 3, 
            mb: 3, 
            borderRadius: 2,
            background: `linear-gradient(135deg, ${theme.palette.primary.light} 0%, ${theme.palette.primary.main} 100%)`,
            color: 'white'
          }}
        >
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={8}>
              <Typography variant="h4" fontWeight="bold" gutterBottom>
                {greeting}，{user?.name || '用户'}！
              </Typography>
              <Typography variant="body1">
                今天是 {currentDate}
              </Typography>
              <Typography variant="body1" sx={{ mt: 1, maxWidth: '80%' }}>
                欢迎回到医疗康复助手系统。{user?.role && `作为${roleTitle[user.role as keyof typeof roleTitle]}，`}您可以在这里管理健康数据、查看康复进展和制定康复计划。
              </Typography>
            </Grid>
            <Grid item xs={12} md={4} sx={{ textAlign: { xs: 'left', md: 'right' } }}>
              <Button 
                variant="contained" 
                sx={{ 
                  bgcolor: 'white', 
                  color: theme.palette.primary.main,
                  '&:hover': {
                    bgcolor: 'rgba(255, 255, 255, 0.9)',
                  },
                  boxShadow: theme.shadows[2],
                  fontWeight: 'bold',
                  mb: { xs: 1, md: 0 },
                  mr: { xs: 1, md: 0 }
                }}
              >
                快速创建
              </Button>
              <Button
                variant="outlined"
                sx={{ 
                  color: 'white', 
                  borderColor: 'white',
                  '&:hover': {
                    borderColor: 'white',
                    bgcolor: 'rgba(255, 255, 255, 0.1)',
                  },
                  ml: { xs: 0, md: 1 }
                }}
                startIcon={<RefreshIcon />}
              >
                刷新数据
              </Button>
            </Grid>
          </Grid>
        </Paper>
        
        {/* 健康小贴士区域 */}
        <Paper 
          elevation={0}
          sx={{ 
            p: 2, 
            mb: 3, 
            borderRadius: 2,
            bgcolor: theme.palette.info.light,
            color: theme.palette.info.contrastText,
            display: 'flex',
            alignItems: 'center'
          }}
        >
          <FavoriteIcon sx={{ mr: 1 }} />
          <Typography variant="body1">
            <strong>每日健康贴士：</strong> {randomTip}
          </Typography>
        </Paper>
        
        {/* 仪表盘统计区域 */}
        <DashboardStatistics userRole={user?.role || 'patient'} />
      </Box>
    </DashboardLayout>
  );
};

export default Dashboard; 