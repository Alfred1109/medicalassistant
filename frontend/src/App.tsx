import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useRoutes } from 'react-router';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from './store';
import { checkAuthStatus } from './store/slices/authSlice';
import { closeSnackbar } from './store/slices/uiSlice';
import { Box, Snackbar, Alert, CircularProgress, Typography, Paper, Container } from '@mui/material';

// 导入路由配置
import routes from './routes';

// 核心页面导入
import IndexPage from './pages/IndexPage';
import Layout from './components/Layout/Layout';
import NotFound from './pages/NotFound';

// Auth Pages
import AuthPage from './pages/Auth/AuthPage';
import Login from './pages/Auth/Login';
import Register from './pages/Auth/Register';

// App Pages
import Dashboard from './pages/Dashboard/Dashboard';
import RehabPlans from './pages/RehabPlan/RehabPlans';
import RehabPlanDetail from './pages/RehabPlan/RehabPlanDetail';
import RehabPlanForm from './pages/RehabPlan/RehabPlanForm';
import Agents from './pages/Agent/Agents';
import AgentDetail from './pages/Agent/AgentDetail';
import AgentForm from './pages/Agent/AgentForm';
import Profile from './pages/Profile/Profile';

// 康复练习库页面
import Exercises from './pages/Exercise/Exercises';
import ExerciseDetail from './pages/Exercise/ExerciseDetail';
import ExerciseForm from './pages/Exercise/ExerciseForm';

// 新增角色页面
import DoctorDashboard from './pages/Doctor/DoctorDashboard';
import PatientManagement from './pages/Doctor/PatientManagement';
import HealthRecords from './pages/Doctor/HealthRecords';
import FollowUpManagement from './pages/Doctor/FollowUpManagement';
import DataMonitoring from './pages/Doctor/DataMonitoring';
import Communication from './pages/Doctor/Communication';
import Statistics from './pages/Doctor/Statistics';
import InformedConsent from './pages/Doctor/InformedConsent';

import HealthManagerDashboard from './pages/HealthManager/HealthManagerDashboard';
import HealthDataTimelinePage from './pages/HealthManager/HealthDataTimelinePage';
import HealthThresholdPage from './pages/HealthManager/HealthThresholdPage';

import PatientDashboard from './pages/Patient/PatientDashboard';
import PatientHealthRecords from './pages/Patient/HealthRecords';
import DailyRecords from './pages/Patient/DailyRecords';
import DeviceBinding from './pages/Patient/DeviceBinding';
import PatientCommunication from './pages/Patient/Communication';
import PatientStatistics from './pages/Patient/Statistics';

// 知情同意文档相关页面
import ConsentDocumentList from './pages/Patient/ConsentDocumentList';
import ConsentDocumentView from './pages/Patient/ConsentDocumentView';
import ConsentTemplateList from './pages/Patient/ConsentTemplateList';

import AdminDashboard from './pages/Admin/AdminDashboard';
import DoctorManagement from './pages/Admin/DoctorManagement';
import AdminPatientManagement from './pages/Admin/PatientManagement';
import HealthManagerManagement from './pages/Admin/HealthManagerManagement';
import OrganizationManagement from './pages/Admin/OrganizationManagement';
import TagManagement from './pages/Admin/TagManagement';
import DeviceManagement from './pages/Admin/DeviceManagement';
import DataVisualization from './pages/Admin/DataVisualization';

// 导入组件
import FeatureUnderDevelopment from './components/common/FeatureUnderDevelopment';

// 通用的"正在开发中"组件
const UnderDevelopment = ({ pageName }: { pageName: string }) => (
  <FeatureUnderDevelopment
    featureName={pageName}
    description={`${pageName} 页面正在开发中，敬请期待！`}
    returnPath="/app/dashboard"
    returnButtonText="返回仪表盘"
  />
);

// 使用路由配置的组件
const AppRoutes = () => {
  const routeElements = useRoutes(routes);
  return routeElements;
};

const App: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { checking } = useSelector((state: RootState) => state.auth);
  const { snackbar } = useSelector((state: RootState) => state.ui);

  React.useEffect(() => {
    dispatch(checkAuthStatus());
  }, [dispatch]);

  if (checking) {
    return (
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  return (
    <BrowserRouter>
      <AppRoutes />
      <Snackbar
        open={snackbar.open}
        autoHideDuration={snackbar.duration || 6000}
        onClose={() => dispatch(closeSnackbar())}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={() => dispatch(closeSnackbar())} 
          severity={snackbar.severity || 'info'}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </BrowserRouter>
  );
};

export default App; 