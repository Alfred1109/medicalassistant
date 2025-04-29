import React from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Divider,
  List,
  ListItem,
  ListItemText,
  Paper,
} from '@mui/material';

// 图标导入
import DashboardIcon from '@mui/icons-material/Dashboard';
import PersonIcon from '@mui/icons-material/Person';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import AccessibilityNewIcon from '@mui/icons-material/AccessibilityNew';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import AssessmentIcon from '@mui/icons-material/Assessment';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import SmartToyIcon from '@mui/icons-material/SmartToy';

interface LinkInfo {
  title: string;
  to: string;
}

interface LinkCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  links: LinkInfo[];
}

const LinkCard: React.FC<LinkCardProps> = ({ title, description, icon, links }) => (
  <Card variant="outlined" sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
    <CardContent sx={{ flexGrow: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        {icon}
        <Typography variant="h6" component="h2" sx={{ ml: 1 }}>
          {title}
        </Typography>
      </Box>
      <Typography color="text.secondary" gutterBottom>
        {description}
      </Typography>
      <Divider sx={{ my: 2 }} />
      <List dense>
        {links.map((link: LinkInfo, index: number) => (
          <ListItem key={index}>
            <Button 
              component={RouterLink} 
              to={link.to} 
              color="primary" 
              fullWidth
            >
              {link.title}
            </Button>
          </ListItem>
        ))}
      </List>
    </CardContent>
  </Card>
);

const IndexPage: React.FC = () => {
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Paper elevation={0} sx={{ p: 3, mb: 4, bgcolor: 'primary.main', color: 'primary.contrastText' }}>
        <Typography variant="h3" component="h1" gutterBottom>
          智能康复助手
        </Typography>
        <Typography variant="h6">
          功能导航页面，点击下方链接快速访问各个功能模块
        </Typography>
      </Paper>

      <Grid container spacing={3}>
        {/* 通用功能 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="通用功能"
            description="应用的核心功能模块"
            icon={<DashboardIcon color="primary" />}
            links={[
              { title: '主面板', to: '/app/dashboard' },
              { title: '用户档案', to: '/app/profile' },
            ]}
          />
        </Grid>

        {/* 康复计划 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="康复计划管理"
            description="康复计划的创建、查看与管理"
            icon={<AccessibilityNewIcon color="primary" />}
            links={[
              { title: '康复计划列表', to: '/app/rehab-plans' },
              { title: '新建康复计划', to: '/app/rehab-plans/new' },
            ]}
          />
        </Grid>

        {/* 康复练习 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="康复练习库"
            description="康复练习的浏览与管理"
            icon={<FitnessCenterIcon color="primary" />}
            links={[
              { title: '练习列表', to: '/app/exercises' },
              { title: '新建练习', to: '/app/exercises/new' },
            ]}
          />
        </Grid>

        {/* 医生功能 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="医生工作站"
            description="医生管理患者和康复计划的功能"
            icon={<MedicalServicesIcon color="primary" />}
            links={[
              { title: '医生主面板', to: '/app/doctor' },
              { title: '患者管理', to: '/app/doctor/patients' },
              { title: '健康记录', to: '/app/doctor/health-records' },
            ]}
          />
        </Grid>

        {/* 患者功能 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="患者应用"
            description="患者使用的健康管理功能"
            icon={<PersonIcon color="primary" />}
            links={[
              { title: '患者主面板', to: '/app/patient' },
              { title: '健康档案', to: '/app/patient/health-records' },
              { title: '每日记录', to: '/app/patient/daily-records' },
            ]}
          />
        </Grid>

        {/* 康复评估 */}
        <Grid item xs={12} md={4}>
          <LinkCard
            title="康复评估"
            description="康复评估与进度报告"
            icon={<AssessmentIcon color="primary" />}
            links={[
              { title: '康复评估报告', to: '/app/rehab-assessment' },
              { title: '康复进度评估', to: '/app/rehab-progress' },
            ]}
          />
        </Grid>

        {/* 智能助手 */}
        <Grid item xs={12} md={6}>
          <LinkCard
            title="智能助手"
            description="AI 辅助功能与智能推荐"
            icon={<SmartToyIcon color="primary" />}
            links={[
              { title: '智能助手列表', to: '/app/agents' },
              { title: '新建智能助手', to: '/app/agents/new' },
              { title: '训练推荐', to: '/app/exercise-recommendations' },
            ]}
          />
        </Grid>

        {/* 系统管理 */}
        <Grid item xs={12} md={6}>
          <LinkCard
            title="系统管理"
            description="管理员功能"
            icon={<AdminPanelSettingsIcon color="primary" />}
            links={[
              { title: '管理员主面板', to: '/app/admin' },
              { title: '医生管理', to: '/app/admin/doctors' },
              { title: '患者管理', to: '/app/admin/patients' },
            ]}
          />
        </Grid>
      </Grid>

      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Typography variant="body2" color="text.secondary">
          © {new Date().getFullYear()} 智能康复助手系统 | 所有页面均可从此处快速访问
        </Typography>
      </Box>
    </Container>
  );
};

export default IndexPage; 