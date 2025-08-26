import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  IconButton,
  CircularProgress,
  Divider,
  Button,
  CardHeader,
  Avatar,
  Chip,
  useTheme,
} from '@mui/material';
import {
  MoreVert as MoreVertIcon,
  People as PeopleIcon,
  LocalHospital as LocalHospitalIcon,
  TrendingUp as TrendingUpIcon,
  Schedule as ScheduleIcon,
  Done as DoneIcon,
  Assignment as AssignmentIcon,
  Event as EventIcon,
  ArrowUpward as ArrowUpwardIcon,
  ArrowDownward as ArrowDownwardIcon,
  Warning as CrisisAlertIcon,
} from '@mui/icons-material';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

// 注册Chart.js组件
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend
);

// 类型定义
interface StatCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
    label: string;
  };
  color?: string;
  onClick?: () => void;
}

// 统计卡片组件
const StatCard: React.FC<StatCardProps> = ({ title, value, icon, trend, color, onClick }) => {
  const theme = useTheme();
  
  return (
    <Card 
      sx={{ 
        height: '100%',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'transform 0.3s',
        '&:hover': onClick ? { transform: 'translateY(-4px)' } : {},
      }}
      onClick={onClick}
    >
      <CardContent sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              {title}
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 'bold' }}>
              {value}
            </Typography>
            
            {trend && (
              <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
                {trend.isPositive ? (
                  <ArrowUpwardIcon sx={{ color: theme.palette.success.main, fontSize: '1rem' }} />
                ) : (
                  <ArrowDownwardIcon sx={{ color: theme.palette.error.main, fontSize: '1rem' }} />
                )}
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: trend.isPositive ? theme.palette.success.main : theme.palette.error.main,
                    ml: 0.5,
                  }}
                >
                  {trend.value}% {trend.label}
                </Typography>
              </Box>
            )}
          </Box>
          
          <Avatar 
            sx={{ 
              backgroundColor: color || theme.palette.primary.main,
              width: 56,
              height: 56,
            }}
          >
            {icon}
          </Avatar>
        </Box>
      </CardContent>
    </Card>
  );
};

// 仪表盘统计组件
const DashboardStatistics: React.FC<{ userRole: 'doctor' | 'patient' | 'healthManager' | 'admin' }> = ({ userRole }) => {
  const theme = useTheme();
  
  // 折线图数据 - 患者进展
  const lineChartData = {
    labels: ['1月', '2月', '3月', '4月', '5月', '6月', '7月'],
    datasets: [
      {
        label: '康复进展',
        data: [65, 72, 78, 75, 82, 87, 92],
        fill: false,
        backgroundColor: theme.palette.primary.main,
        borderColor: theme.palette.primary.main,
        tension: 0.4,
      },
      {
        label: '平均水平',
        data: [60, 65, 70, 72, 75, 78, 80],
        fill: false,
        backgroundColor: theme.palette.grey[400],
        borderColor: theme.palette.grey[400],
        borderDash: [5, 5],
        tension: 0.4,
      },
    ],
  };
  
  // 柱状图数据 - 每周活动
  const barChartData = {
    labels: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
    datasets: [
      {
        label: '已完成活动',
        data: [3, 5, 4, 6, 5, 3, 2],
        backgroundColor: theme.palette.primary.main,
      },
      {
        label: '未完成活动',
        data: [1, 0, 2, 1, 1, 0, 1],
        backgroundColor: theme.palette.error.light,
      },
    ],
  };
  
  // 环形图数据 - 康复计划完成度
  const doughnutChartData = {
    labels: ['已完成', '进行中', '未开始'],
    datasets: [
      {
        data: [65, 25, 10],
        backgroundColor: [
          theme.palette.success.main,
          theme.palette.info.main,
          theme.palette.grey[300],
        ],
        borderWidth: 0,
      },
    ],
  };
  
  // 图表配置
  const lineOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: false,
      },
    },
    scales: {
      y: {
        min: 0,
        max: 100,
        ticks: {
          stepSize: 20,
        },
      },
    },
  };
  
  const barOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'top' as const,
      },
      title: {
        display: false,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
      },
    },
  };
  
  const doughnutOptions = {
    responsive: true,
    plugins: {
      legend: {
        position: 'right' as const,
      },
      title: {
        display: false,
      },
    },
    cutout: '70%',
  };
  
  // 根据用户角色获取相应的统计数据
  const getRoleBasedStats = () => {
    switch (userRole) {
      case 'doctor':
        return (
          <>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="活跃患者"
                  value="128"
                  icon={<PeopleIcon />}
                  trend={{ value: 12, isPositive: true, label: "较上月" }}
                  color={theme.palette.primary.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="已安排随访"
                  value="42"
                  icon={<ScheduleIcon />}
                  trend={{ value: 8, isPositive: true, label: "较上周" }}
                  color={theme.palette.info.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="康复计划"
                  value="85"
                  icon={<AssignmentIcon />}
                  trend={{ value: 5, isPositive: true, label: "新增" }}
                  color={theme.palette.success.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="待审阅记录"
                  value="17"
                  icon={<LocalHospitalIcon />}
                  trend={{ value: 3, isPositive: false, label: "增加" }}
                  color={theme.palette.warning.main}
                />
              </Grid>
            </Grid>

            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader 
                    title="患者康复进展趋势" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Line data={lineChartData} options={lineOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="康复计划完成度" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100% - 72px)' }}>
                    <Doughnut data={doughnutChartData} options={doughnutOptions} />
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader 
                    title="每周活动统计" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Bar data={barChartData} options={barOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="近期随访" 
                    action={
                      <Button size="small" color="primary">查看全部</Button>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Avatar sx={{ mr: 2, bgcolor: theme.palette.primary.main }}>张</Avatar>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">张三</Typography>
                        <Typography variant="body2" color="text.secondary">腰椎间盘突出症</Typography>
                      </Box>
                      <Chip 
                        size="small" 
                        icon={<EventIcon fontSize="small" />} 
                        label="今天 14:30" 
                        color="primary" 
                        variant="outlined"
                      />
                    </Box>
                    <Divider sx={{ my: 2 }} />
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Avatar sx={{ mr: 2, bgcolor: theme.palette.secondary.main }}>李</Avatar>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">李四</Typography>
                        <Typography variant="body2" color="text.secondary">膝关节炎</Typography>
                      </Box>
                      <Chip 
                        size="small" 
                        icon={<EventIcon fontSize="small" />} 
                        label="明天 10:00" 
                        color="info" 
                        variant="outlined"
                      />
                    </Box>
                    <Divider sx={{ my: 2 }} />
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Avatar sx={{ mr: 2, bgcolor: theme.palette.success.main }}>王</Avatar>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">王五</Typography>
                        <Typography variant="body2" color="text.secondary">肩周炎</Typography>
                      </Box>
                      <Chip 
                        size="small" 
                        icon={<EventIcon fontSize="small" />} 
                        label="后天 15:30" 
                        color="success" 
                        variant="outlined"
                      />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </>
        );
        
      case 'patient':
        return (
          <>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="康复计划进度"
                  value="78%"
                  icon={<TrendingUpIcon />}
                  trend={{ value: 5, isPositive: true, label: "过去一周" }}
                  color={theme.palette.primary.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="今日活动"
                  value="3/5"
                  icon={<AssignmentIcon />}
                  color={theme.palette.info.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="已完成练习"
                  value="42"
                  icon={<DoneIcon />}
                  trend={{ value: 12, isPositive: true, label: "较上个月" }}
                  color={theme.palette.success.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="未来随访"
                  value="2"
                  icon={<EventIcon />}
                  trend={{ value: 1, isPositive: true, label: "本周新增" }}
                  color={theme.palette.warning.main}
                />
              </Grid>
            </Grid>

            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader 
                    title="我的康复进展" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Line data={lineChartData} options={lineOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="康复计划完成度" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100% - 72px)' }}>
                    <Doughnut data={doughnutChartData} options={doughnutOptions} />
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader 
                    title="每周活动统计" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Bar data={barChartData} options={barOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="今日活动" 
                    action={
                      <Button size="small" color="primary">查看全部</Button>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Box 
                        sx={{ 
                          mr: 2,
                          width: 40, 
                          height: 40, 
                          borderRadius: '50%', 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center',
                          bgcolor: theme.palette.primary.main,
                          color: 'white'
                        }}
                      >
                        <DoneIcon />
                      </Box>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">腰部伸展练习</Typography>
                        <Typography variant="body2" color="text.secondary">10:30 - 已完成</Typography>
                      </Box>
                      <Chip label="已完成" color="success" size="small" />
                    </Box>
                    <Divider sx={{ my: 2 }} />
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Box 
                        sx={{ 
                          mr: 2,
                          width: 40, 
                          height: 40, 
                          borderRadius: '50%', 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center',
                          bgcolor: theme.palette.primary.main,
                          color: 'white'
                        }}
                      >
                        <DoneIcon />
                      </Box>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">腿部力量训练</Typography>
                        <Typography variant="body2" color="text.secondary">14:00 - 已完成</Typography>
                      </Box>
                      <Chip label="已完成" color="success" size="small" />
                    </Box>
                    <Divider sx={{ my: 2 }} />
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Box 
                        sx={{ 
                          mr: 2,
                          width: 40, 
                          height: 40, 
                          borderRadius: '50%', 
                          display: 'flex', 
                          alignItems: 'center', 
                          justifyContent: 'center',
                          bgcolor: theme.palette.grey[300],
                          color: theme.palette.text.secondary
                        }}
                      >
                        <ScheduleIcon />
                      </Box>
                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="subtitle1">放松冥想</Typography>
                        <Typography variant="body2" color="text.secondary">19:00 - 未开始</Typography>
                      </Box>
                      <Chip label="待完成" color="default" size="small" />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </>
        );
        
      case 'healthManager':
        return (
          <>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="管理患者"
                  value="64"
                  icon={<PeopleIcon />}
                  trend={{ value: 8, isPositive: true, label: "较上月" }}
                  color={theme.palette.primary.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="已安排随访"
                  value="28"
                  icon={<ScheduleIcon />}
                  trend={{ value: 5, isPositive: true, label: "较上周" }}
                  color={theme.palette.info.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="异常健康数据"
                  value="7"
                  icon={<CrisisAlertIcon/>}
                  trend={{ value: 2, isPositive: false, label: "增加" }}
                  color={theme.palette.error.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="需审核报告"
                  value="12"
                  icon={<AssignmentIcon />}
                  trend={{ value: 4, isPositive: false, label: "增加" }}
                  color={theme.palette.warning.main}
                />
              </Grid>
            </Grid>

            {/* 图表和内容部分与医生类似，根据健康管理师的需求调整 */}
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader 
                    title="患者健康指标趋势" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Line data={lineChartData} options={lineOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="计划完成率分布" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100% - 72px)' }}>
                    <Doughnut data={doughnutChartData} options={doughnutOptions} />
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </>
        );
        
      case 'admin':
        return (
          <>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="活跃用户"
                  value="342"
                  icon={<PeopleIcon />}
                  trend={{ value: 15, isPositive: true, label: "较上月" }}
                  color={theme.palette.primary.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="医生数量"
                  value="28"
                  icon={<LocalHospitalIcon />}
                  trend={{ value: 3, isPositive: true, label: "新增" }}
                  color={theme.palette.info.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="康复计划"
                  value="156"
                  icon={<AssignmentIcon />}
                  trend={{ value: 23, isPositive: true, label: "较上月" }}
                  color={theme.palette.success.main}
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  title="系统事件"
                  value="8"
                  icon={<CrisisAlertIcon />}
                  trend={{ value: 2, isPositive: false, label: "增加" }}
                  color={theme.palette.warning.main}
                />
              </Grid>
            </Grid>
            
            {/* 管理员特定的图表和统计数据 */}
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader 
                    title="系统使用趋势" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent>
                    <Line data={lineChartData} options={lineOptions} />
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardHeader 
                    title="用户角色分布" 
                    action={
                      <IconButton>
                        <MoreVertIcon />
                      </IconButton>
                    }
                  />
                  <Divider />
                  <CardContent sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100% - 72px)' }}>
                    <Doughnut 
                      data={{
                        labels: ['医生', '患者', '健康管理师', '管理员'],
                        datasets: [
                          {
                            data: [28, 245, 64, 5],
                            backgroundColor: [
                              theme.palette.primary.main,
                              theme.palette.info.main,
                              theme.palette.success.main,
                              theme.palette.warning.main,
                            ],
                            borderWidth: 0,
                          },
                        ],
                      }} 
                      options={doughnutOptions} 
                    />
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </>
        );
        
      default:
        return null;
    }
  };
  
  return (
    <Box sx={{ mt: 2 }}>
      {getRoleBasedStats()}
    </Box>
  );
};

export default DashboardStatistics; 