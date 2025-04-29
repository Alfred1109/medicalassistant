import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Provider } from 'react-redux';
import { CssBaseline } from '@mui/material';
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
import AuthPage from './pages/Auth/AuthPage';
import Dashboard from './pages/Dashboard/Dashboard';
import RehabPlans from './pages/RehabPlan/RehabPlans';
import RehabPlanDetail from './pages/RehabPlan/RehabPlanDetail';
import RehabPlanForm from './pages/RehabPlan/RehabPlanForm';
import Exercises from './pages/Exercise/Exercises';
import ExerciseDetail from './pages/Exercise/ExerciseDetail';
import ExerciseForm from './pages/Exercise/ExerciseForm';
import Agents from './pages/Agent/Agents';
import AgentDetail from './pages/Agent/AgentDetail';
import AgentForm from './pages/Agent/AgentForm';
import DoctorDashboard from './pages/Doctor/DoctorDashboard';
import PatientDashboard from './pages/Patient/PatientDashboard';
import HealthManagerDashboard from './pages/HealthManager/HealthManagerDashboard';
import AdminDashboard from './pages/Admin/AdminDashboard';
import RehabAssessment from './pages/Assessment/RehabAssessment';
import RehabProgress from './pages/Assessment/RehabProgress';
import ExerciseRecommendations from './pages/Recommendations/ExerciseRecommendations';
import Profile from './pages/Profile/Profile';
import NotFound from './pages/NotFound';

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

// 如果页面组件加载失败，使用备用组件
const SafeComponent = (Component: React.ComponentType, Fallback: React.ComponentType) => {
  try {
    return <Component />;
  } catch (error) {
    console.error("组件加载失败:", error);
    return <Fallback />;
  }
};

const App = () => (
  <Provider store={store}>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          {/* 尝试使用实际页面，如果失败则使用备用页面 */}
          <Route path="/" element={SafeComponent(IndexPage, FallbackIndexPage)} />
          
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