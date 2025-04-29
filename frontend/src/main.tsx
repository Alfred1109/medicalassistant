import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Provider } from 'react-redux';
import { CssBaseline, CircularProgress, Box } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import store from './store';

// 导入备用页面组件
import {
  FallbackIndexPage,
  FallbackAuthPage,
  FallbackDashboard,
  FallbackRehabPlans,
  FallbackRehabPlanDetail,
  FallbackRehabPlanForm,
  FallbackExercises,
  FallbackExerciseDetail,
  FallbackExerciseForm,
  FallbackAgents,
  FallbackAgentDetail,
  FallbackAgentForm,
  FallbackDoctorDashboard,
  FallbackPatientDashboard,
  FallbackHealthManagerDashboard,
  FallbackAdminDashboard,
  FallbackRehabAssessment,
  FallbackRehabProgress,
  FallbackExerciseRecommendations,
  FallbackProfile,
  FallbackNotFoundPage
} from './fallbackPages';

// 导入实际页面
import IndexPage from './pages/IndexPage';

// 导入布局组件
const Layout = React.lazy(() => import('./components/Layout/Layout'));

// 懒加载页面组件
// 认证页面
const AuthPage = React.lazy(() => import('./pages/Auth/AuthPage'));
const Login = React.lazy(() => import('./pages/Auth/Login'));
const Register = React.lazy(() => import('./pages/Auth/Register'));

// 主要页面
const Dashboard = React.lazy(() => import('./pages/Dashboard/Dashboard'));
const Profile = React.lazy(() => import('./pages/Profile/Profile'));

// 康复计划
const RehabPlans = React.lazy(() => import('./pages/RehabPlan/RehabPlans'));
const RehabPlanDetail = React.lazy(() => import('./pages/RehabPlan/RehabPlanDetail'));
const RehabPlanForm = React.lazy(() => import('./pages/RehabPlan/RehabPlanForm'));

// 康复练习
const Exercises = React.lazy(() => import('./pages/Exercise/Exercises'));
const ExerciseDetail = React.lazy(() => import('./pages/Exercise/ExerciseDetail'));
const ExerciseForm = React.lazy(() => import('./pages/Exercise/ExerciseForm'));

// 智能助手
const Agents = React.lazy(() => import('./pages/Agent/Agents'));
const AgentDetail = React.lazy(() => import('./pages/Agent/AgentDetail'));
const AgentForm = React.lazy(() => import('./pages/Agent/AgentForm'));

// 康复评估
const RehabAssessment = React.lazy(() => import('./pages/Assessment/RehabAssessment'));
const RehabProgress = React.lazy(() => import('./pages/Assessment/RehabProgress'));
const ExerciseRecommendations = React.lazy(() => import('./pages/Recommendations/ExerciseRecommendations'));

// 医生页面
const DoctorDashboard = React.lazy(() => import('./pages/Doctor/DoctorDashboard'));
const PatientManagement = React.lazy(() => import('./pages/Doctor/PatientManagement'));
const HealthRecords = React.lazy(() => import('./pages/Doctor/HealthRecords'));
const FollowUpManagement = React.lazy(() => import('./pages/Doctor/FollowUpManagement'));
const DataMonitoring = React.lazy(() => import('./pages/Doctor/DataMonitoring'));
const Communication = React.lazy(() => import('./pages/Doctor/Communication'));
const Statistics = React.lazy(() => import('./pages/Doctor/Statistics'));
const InformedConsent = React.lazy(() => import('./pages/Doctor/InformedConsent'));

// 患者页面
const PatientDashboard = React.lazy(() => import('./pages/Patient/PatientDashboard'));
const PatientHealthRecords = React.lazy(() => import('./pages/Patient/HealthRecords'));
const DailyRecords = React.lazy(() => import('./pages/Patient/DailyRecords'));
const DeviceBinding = React.lazy(() => import('./pages/Patient/DeviceBinding'));
const PatientCommunication = React.lazy(() => import('./pages/Patient/Communication'));
const PatientStatistics = React.lazy(() => import('./pages/Patient/Statistics'));
const ConsentDocumentList = React.lazy(() => import('./pages/Patient/ConsentDocumentList'));
const ConsentDocumentView = React.lazy(() => import('./pages/Patient/ConsentDocumentView'));
const ConsentTemplateList = React.lazy(() => import('./pages/Patient/ConsentTemplateList'));

// 健康管理师页面
const HealthManagerDashboard = React.lazy(() => import('./pages/HealthManager/HealthManagerDashboard'));
const HealthDataTimelinePage = React.lazy(() => import('./pages/HealthManager/HealthDataTimelinePage'));
const HealthThresholdPage = React.lazy(() => import('./pages/HealthManager/HealthThresholdPage'));

// 管理员页面
const AdminDashboard = React.lazy(() => import('./pages/Admin/AdminDashboard'));
const DoctorManagement = React.lazy(() => import('./pages/Admin/DoctorManagement'));
const AdminPatientManagement = React.lazy(() => import('./pages/Admin/PatientManagement'));
const HealthManagerManagement = React.lazy(() => import('./pages/Admin/HealthManagerManagement'));
const OrganizationManagement = React.lazy(() => import('./pages/Admin/OrganizationManagement'));
const TagManagement = React.lazy(() => import('./pages/Admin/TagManagement'));
const DeviceManagement = React.lazy(() => import('./pages/Admin/DeviceManagement'));
const DataVisualization = React.lazy(() => import('./pages/Admin/DataVisualization'));

// 404页面
const NotFound = React.lazy(() => import('./pages/NotFound'));

// 定义主题
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#f50057',
    },
    background: {
      default: '#f8f9fa',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          borderRadius: 8,
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 12,
        },
      },
    },
  },
});

// 基本错误处理
const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('未找到根元素，无法渲染应用');
}

// 加载中组件
const LoadingFallback = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
    <CircularProgress />
  </Box>
);

// 错误边界组件
class ErrorBoundary extends React.Component<
  { children: React.ReactNode, fallback: React.ReactNode },
  { hasError: boolean, error: Error | null }
> {
  constructor(props: { children: React.ReactNode, fallback: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('页面渲染错误:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      console.log('使用备用页面:', this.state.error?.message);
      return this.props.fallback;
    }

    return this.props.children;
  }
}

// 安全组件加载方式
const SafeComponent = (
  Component: React.ComponentType,
  FallbackComponent: React.ComponentType
) => {
  return (
    <ErrorBoundary fallback={<FallbackComponent />}>
      <React.Suspense fallback={<LoadingFallback />}>
        <Component />
      </React.Suspense>
    </ErrorBoundary>
  );
};

// 受保护的路由组件
const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  // 检查用户是否已认证
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (!isAuthenticated) {
    // 如果未认证，重定向到登录页面
    return <Navigate to="/auth/login" replace />;
  }
  
  return <>{children}</>;
};

// 角色路由守卫组件
const RoleRoute = ({ children, allowedRoles }: { children: React.ReactNode, allowedRoles: string[] }) => {
  const userRole = localStorage.getItem('userRole');
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (!isAuthenticated) {
    return <Navigate to="/auth/login" replace />;
  }
  
  if (!userRole || !allowedRoles.includes(userRole)) {
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// 应用组件
const App = () => (
  <Provider store={store}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <ErrorBoundary fallback={<FallbackIndexPage />}>
          <Routes>
            {/* 首页重定向到登录页面 */}
            <Route path="/" element={<Navigate to="/auth/login" replace />} />
            
            {/* 认证路由 */}
            <Route path="/auth" element={SafeComponent(AuthPage, FallbackAuthPage)}>
              <Route index element={<Navigate to="/auth/login" replace />} />
              <Route path="login" element={SafeComponent(Login, FallbackAuthPage)} />
              <Route path="register" element={SafeComponent(Register, FallbackAuthPage)} />
            </Route>
            
            {/* 应用主路由 - 受保护 */}
            <Route path="/app" element={
              <ProtectedRoute>
                <React.Suspense fallback={<LoadingFallback />}>
                  <Layout />
                </React.Suspense>
              </ProtectedRoute>
            }>
              {/* 主面板 */}
              <Route path="dashboard" element={SafeComponent(Dashboard, FallbackDashboard)} />
              
              {/* 康复计划 */}
              <Route path="rehab-plans" element={SafeComponent(RehabPlans, FallbackRehabPlans)} />
              <Route path="rehab-plans/:id" element={SafeComponent(RehabPlanDetail, FallbackRehabPlanDetail)} />
              <Route path="rehab-plans/new" element={SafeComponent(RehabPlanForm, FallbackRehabPlanForm)} />
              <Route path="rehab-plans/edit/:id" element={SafeComponent(RehabPlanForm, FallbackRehabPlanForm)} />
              
              {/* 康复练习 */}
              <Route path="exercises" element={SafeComponent(Exercises, FallbackExercises)} />
              <Route path="exercises/:id" element={SafeComponent(ExerciseDetail, FallbackExerciseDetail)} />
              <Route path="exercises/new" element={SafeComponent(ExerciseForm, FallbackExerciseForm)} />
              <Route path="exercises/edit/:id" element={SafeComponent(ExerciseForm, FallbackExerciseForm)} />
              
              {/* 智能助手 */}
              <Route path="agents" element={SafeComponent(Agents, FallbackAgents)} />
              <Route path="agents/:id" element={SafeComponent(AgentDetail, FallbackAgentDetail)} />
              <Route path="agents/new" element={SafeComponent(AgentForm, FallbackAgentForm)} />
              <Route path="agents/edit/:id" element={SafeComponent(AgentForm, FallbackAgentForm)} />
              
              {/* 康复评估 */}
              <Route path="rehab-assessment" element={SafeComponent(RehabAssessment, FallbackRehabAssessment)} />
              <Route path="rehab-progress" element={SafeComponent(RehabProgress, FallbackRehabProgress)} />
              
              {/* 训练推荐 */}
              <Route path="exercise-recommendations" element={SafeComponent(ExerciseRecommendations, FallbackExerciseRecommendations)} />
              
              {/* 用户档案 */}
              <Route path="profile" element={SafeComponent(Profile, FallbackProfile)} />
              
              {/* 医生专属路由 */}
              <Route path="doctor" element={SafeComponent(DoctorDashboard, FallbackDoctorDashboard)}>
                <Route index element={<Navigate to="/app/doctor/patients" replace />} />
                <Route path="patients" element={SafeComponent(PatientManagement, FallbackDoctorDashboard)} />
                <Route path="health-records/:patientId?" element={SafeComponent(HealthRecords, FallbackDoctorDashboard)} />
                <Route path="follow-ups" element={SafeComponent(FollowUpManagement, FallbackDoctorDashboard)} />
                <Route path="monitoring/:patientId?" element={SafeComponent(DataMonitoring, FallbackDoctorDashboard)} />
                <Route path="communications/:patientId?" element={SafeComponent(Communication, FallbackDoctorDashboard)} />
                <Route path="statistics" element={SafeComponent(Statistics, FallbackDoctorDashboard)} />
                <Route path="informed-consent" element={SafeComponent(InformedConsent, FallbackDoctorDashboard)} />
                <Route path="documents" element={SafeComponent(ConsentDocumentList, FallbackDoctorDashboard)} />
                <Route path="documents/:documentId" element={SafeComponent(ConsentDocumentView, FallbackDoctorDashboard)} />
                <Route path="documents/templates" element={SafeComponent(ConsentTemplateList, FallbackDoctorDashboard)} />
              </Route>
              
              {/* 患者专属路由 */}
              <Route path="patient" element={SafeComponent(PatientDashboard, FallbackPatientDashboard)}>
                <Route index element={<Navigate to="/app/patient/health-records" replace />} />
                <Route path="health-records" element={SafeComponent(PatientHealthRecords, FallbackPatientDashboard)} />
                <Route path="daily-records" element={SafeComponent(DailyRecords, FallbackPatientDashboard)} />
                <Route path="devices" element={SafeComponent(DeviceBinding, FallbackPatientDashboard)} />
                <Route path="communications" element={SafeComponent(PatientCommunication, FallbackPatientDashboard)} />
                <Route path="statistics" element={SafeComponent(PatientStatistics, FallbackPatientDashboard)} />
                <Route path="documents" element={SafeComponent(ConsentDocumentList, FallbackPatientDashboard)} />
                <Route path="documents/:documentId" element={SafeComponent(ConsentDocumentView, FallbackPatientDashboard)} />
                <Route path="documents/:documentId/sign" element={SafeComponent(ConsentDocumentView, FallbackPatientDashboard)} />
                <Route path="documents/templates" element={SafeComponent(ConsentTemplateList, FallbackPatientDashboard)} />
              </Route>
              
              {/* 健康管理师专属路由 */}
              <Route path="health-manager" element={SafeComponent(HealthManagerDashboard, FallbackHealthManagerDashboard)}>
                <Route index element={<Navigate to="/app/health-manager/patients" replace />} />
                <Route path="patients" element={SafeComponent(PatientManagement, FallbackHealthManagerDashboard)} />
                <Route path="health-records/:patientId?" element={SafeComponent(HealthRecords, FallbackHealthManagerDashboard)} />
                <Route path="health-data-timeline/:patientId?" element={SafeComponent(HealthDataTimelinePage, FallbackHealthManagerDashboard)} />
                <Route path="thresholds/:patientId?" element={SafeComponent(HealthThresholdPage, FallbackHealthManagerDashboard)} />
                <Route path="follow-ups" element={SafeComponent(FollowUpManagement, FallbackHealthManagerDashboard)} />
                <Route path="monitoring/:patientId?" element={SafeComponent(DataMonitoring, FallbackHealthManagerDashboard)} />
                <Route path="communications/:patientId?" element={SafeComponent(Communication, FallbackHealthManagerDashboard)} />
                <Route path="statistics" element={SafeComponent(Statistics, FallbackHealthManagerDashboard)} />
                <Route path="documents" element={SafeComponent(ConsentDocumentList, FallbackHealthManagerDashboard)} />
                <Route path="documents/:documentId" element={SafeComponent(ConsentDocumentView, FallbackHealthManagerDashboard)} />
                <Route path="documents/templates" element={SafeComponent(ConsentTemplateList, FallbackHealthManagerDashboard)} />
              </Route>
              
              {/* 管理员专属路由 */}
              <Route path="admin" element={SafeComponent(AdminDashboard, FallbackAdminDashboard)}>
                <Route index element={<Navigate to="/app/admin/doctors" replace />} />
                <Route path="doctors" element={SafeComponent(DoctorManagement, FallbackAdminDashboard)} />
                <Route path="patients" element={SafeComponent(AdminPatientManagement, FallbackAdminDashboard)} />
                <Route path="health-managers" element={SafeComponent(HealthManagerManagement, FallbackAdminDashboard)} />
                <Route path="organizations" element={SafeComponent(OrganizationManagement, FallbackAdminDashboard)} />
                <Route path="tags" element={SafeComponent(TagManagement, FallbackAdminDashboard)} />
                <Route path="devices" element={SafeComponent(DeviceManagement, FallbackAdminDashboard)} />
                <Route path="visualization" element={SafeComponent(DataVisualization, FallbackAdminDashboard)} />
              </Route>
            </Route>
            
            {/* 404 路由 */}
            <Route path="*" element={SafeComponent(NotFound, FallbackNotFoundPage)} />
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </ThemeProvider>
  </Provider>
);

// 渲染应用
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
); 