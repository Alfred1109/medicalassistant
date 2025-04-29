import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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

// 懒加载其他页面以提高性能
const AuthPage = React.lazy(() => import('./pages/Auth/AuthPage'));
const Dashboard = React.lazy(() => import('./pages/Dashboard/Dashboard'));
const RehabPlans = React.lazy(() => import('./pages/RehabPlan/RehabPlans'));
const RehabPlanDetail = React.lazy(() => import('./pages/RehabPlan/RehabPlanDetail'));
const RehabPlanForm = React.lazy(() => import('./pages/RehabPlan/RehabPlanForm'));
const Exercises = React.lazy(() => import('./pages/Exercise/Exercises'));
const ExerciseDetail = React.lazy(() => import('./pages/Exercise/ExerciseDetail'));
const ExerciseForm = React.lazy(() => import('./pages/Exercise/ExerciseForm'));
const Agents = React.lazy(() => import('./pages/Agent/Agents'));
const AgentDetail = React.lazy(() => import('./pages/Agent/AgentDetail'));
const AgentForm = React.lazy(() => import('./pages/Agent/AgentForm'));
const DoctorDashboard = React.lazy(() => import('./pages/Doctor/DoctorDashboard'));
const PatientDashboard = React.lazy(() => import('./pages/Patient/PatientDashboard'));
const HealthManagerDashboard = React.lazy(() => import('./pages/HealthManager/HealthManagerDashboard'));
const AdminDashboard = React.lazy(() => import('./pages/Admin/AdminDashboard'));
const RehabAssessment = React.lazy(() => import('./pages/Assessment/RehabAssessment'));
const RehabProgress = React.lazy(() => import('./pages/Assessment/RehabProgress'));
const ExerciseRecommendations = React.lazy(() => import('./pages/Recommendations/ExerciseRecommendations'));
const Profile = React.lazy(() => import('./pages/Profile/Profile'));
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

// 改进的安全组件加载方式
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
            <Route path="/auth/*" element={SafeComponent(AuthPage, FallbackAuthPage)} />
            
            {/* 应用主路由 */}
            <Route path="/app/dashboard" element={SafeComponent(Dashboard, FallbackDashboard)} />
            
            {/* 康复计划路由 */}
            <Route path="/app/rehab-plans" element={SafeComponent(RehabPlans, FallbackRehabPlans)} />
            <Route path="/app/rehab-plans/:id" element={SafeComponent(RehabPlanDetail, FallbackRehabPlanDetail)} />
            <Route path="/app/rehab-plans/new" element={SafeComponent(RehabPlanForm, FallbackRehabPlanForm)} />
            <Route path="/app/rehab-plans/edit/:id" element={SafeComponent(RehabPlanForm, FallbackRehabPlanForm)} />
            
            {/* 康复练习路由 */}
            <Route path="/app/exercises" element={SafeComponent(Exercises, FallbackExercises)} />
            <Route path="/app/exercises/:id" element={SafeComponent(ExerciseDetail, FallbackExerciseDetail)} />
            <Route path="/app/exercises/new" element={SafeComponent(ExerciseForm, FallbackExerciseForm)} />
            <Route path="/app/exercises/edit/:id" element={SafeComponent(ExerciseForm, FallbackExerciseForm)} />
            
            {/* 智能助手路由 */}
            <Route path="/app/agents" element={SafeComponent(Agents, FallbackAgents)} />
            <Route path="/app/agents/:id" element={SafeComponent(AgentDetail, FallbackAgentDetail)} />
            <Route path="/app/agents/new" element={SafeComponent(AgentForm, FallbackAgentForm)} />
            <Route path="/app/agents/edit/:id" element={SafeComponent(AgentForm, FallbackAgentForm)} />
            
            {/* 康复评估路由 */}
            <Route path="/app/rehab-assessment" element={SafeComponent(RehabAssessment, FallbackRehabAssessment)} />
            <Route path="/app/rehab-progress" element={SafeComponent(RehabProgress, FallbackRehabProgress)} />
            
            {/* 训练推荐路由 */}
            <Route path="/app/exercise-recommendations" element={SafeComponent(ExerciseRecommendations, FallbackExerciseRecommendations)} />
            
            {/* 用户档案路由 */}
            <Route path="/app/profile" element={SafeComponent(Profile, FallbackProfile)} />
            
            {/* 医生专属路由 */}
            <Route path="/app/doctor/*" element={SafeComponent(DoctorDashboard, FallbackDoctorDashboard)} />
            
            {/* 患者专属路由 */}
            <Route path="/app/patient/*" element={SafeComponent(PatientDashboard, FallbackPatientDashboard)} />
            
            {/* 健康管理师专属路由 */}
            <Route path="/app/health-manager/*" element={SafeComponent(HealthManagerDashboard, FallbackHealthManagerDashboard)} />
            
            {/* 管理员专属路由 */}
            <Route path="/app/admin/*" element={SafeComponent(AdminDashboard, FallbackAdminDashboard)} />
            
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