import * as React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Breadcrumbs from '@mui/material/Breadcrumbs';
import Link from '@mui/material/Link';
import { Link as RouterLink, useParams } from 'react-router-dom';
import HomeIcon from '@mui/icons-material/Home';
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart';
import TuneIcon from '@mui/icons-material/Tune';

// 导入健康阈值管理组件
import HealthThresholdManagement from '../../components/HealthManager/HealthThresholdManagement';

// 健康数据阈值管理页面
const HealthThresholdPage = () => {
  const { patientId } = useParams<{ patientId?: string }>();

  return (
    <Box>
      {/* 面包屑导航 */}
      <Breadcrumbs aria-label="breadcrumb" sx={{ mb: 2 }}>
        <Link
          component={RouterLink}
          to="/health-manager/dashboard"
          underline="hover"
          sx={{ display: 'flex', alignItems: 'center' }}
        >
          <HomeIcon sx={{ mr: 0.5 }} fontSize="inherit" />
          首页
        </Link>
        <Link
          component={RouterLink}
          to="/health-manager/monitoring"
          underline="hover"
          sx={{ display: 'flex', alignItems: 'center' }}
        >
          <MonitorHeartIcon sx={{ mr: 0.5 }} fontSize="inherit" />
          健康监测
        </Link>
        <Typography
          sx={{ display: 'flex', alignItems: 'center' }}
          color="text.primary"
        >
          <TuneIcon sx={{ mr: 0.5 }} fontSize="inherit" />
          健康数据阈值管理
          {patientId && ` - 患者ID:${patientId}`}
        </Typography>
      </Breadcrumbs>

      <Paper elevation={3} sx={{ p: 3 }}>
        <Typography variant="h5" gutterBottom>
          健康数据阈值管理
          {patientId && ` - 患者专属阈值`}
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          在此页面，您可以管理健康数据的正常、警告和危险阈值范围。
          {patientId
            ? '当前设置将仅应用于指定患者，优先级高于通用阈值。'
            : '当前设置为通用阈值，适用于所有未设置专属阈值的患者。'}
        </Typography>
        <Divider sx={{ mb: 3 }} />

        {/* 健康数据阈值管理组件 */}
        <HealthThresholdManagement patientId={patientId} />
      </Paper>
    </Box>
  );
};

export default HealthThresholdPage; 