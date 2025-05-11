import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { CircularProgress, Box } from '@mui/material';

// Layout
import Layout from './components/Layout/Layout';

// IndexPage - 新添加的入口页面
import IndexPage from './pages/IndexPage';

// 测试页面
import TestPage from './pages/TestPage';

// Auth Pages
import AuthPage from './pages/Auth/AuthPage';
import Login from './pages/Auth/Login';
import Register from './pages/Auth/Register';

// App Pages
import Dashboard from './pages/Dashboard';
import RehabPlans from './pages/RehabPlan/RehabPlans';
import RehabPlanDetail from './pages/RehabPlan/RehabPlanDetail';
import RehabPlanForm from './pages/RehabPlan/RehabPlanForm';
import Agents from './pages/Agent/Agents';
import AgentDetail from './pages/Agent/AgentDetail';
import AgentForm from './pages/Agent/AgentForm';
import Profile from './pages/Profile/Profile';
import NotFound from './pages/NotFound';

// 通知中心组件
import NotificationsPage from './pages/NotificationsPage';

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
import PatientMainDashboard from './pages/Patient/PatientMainDashboard';
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
import AuditLogsPage from './pages/Admin/AuditLogsPage';
import PermissionAuditLog from './components/Admin/PermissionAuditLog';

// 康复评估相关页面
import RehabAssessment from './pages/Assessment/RehabAssessment';
import RehabProgress from './pages/Assessment/RehabProgress';

// 训练推荐相关页面
import ExerciseRecommendations from './pages/Recommendations/ExerciseRecommendations';

// 功能开发演示页面
import FeatureDemoPage from './pages/Common/FeatureDemoPage';

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

// 加载中组件
export const LoadingFallback = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
    <CircularProgress />
  </Box>
);

// 错误边界组件
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode, fallback: React.ReactNode },
  { hasError: boolean, error: Error | null }
> {
  constructor(props: { children: React.ReactNode, fallback: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    // 在开发环境下不捕获错误，方便调试
    if (import.meta.env.DEV) {
      console.error('开发环境下错误:', error);
      return { hasError: false, error };
    }
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
export const SafeComponent = (
  Component: React.ComponentType,
  FallbackComponent: React.ComponentType
) => {
  return (
    <ErrorBoundary fallback={<FallbackComponent />}>
      <React.Suspense fallback={<LoadingFallback />} >
        <Component />
      </React.Suspense>
    </ErrorBoundary>
  );
};

// 直接加载组件（绕过安全检查，用于开发环境中有编译错误但仍需强制显示的组件）
export const ForceLoadComponent = (
  Component: React.ComponentType
) => {
  return (
    <React.Suspense fallback={<LoadingFallback />}>
      <Component />
    </React.Suspense>
  );
};

// Protected Route Component
export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Check if user is authenticated
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (!isAuthenticated) {
    // Redirect to login if not authenticated
    return <Navigate to="/auth" replace />;
  }
  
  return <>{children}</>;
};

// Public Route Component (accessible only if NOT authenticated)
export const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (isAuthenticated) {
    // Redirect to dashboard if already authenticated
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// 角色路由守卫组件
export const RoleRoute: React.FC<{ children: React.ReactNode, allowedRoles: string[] }> = ({ children, allowedRoles }) => {
  const userRole = localStorage.getItem('userRole');
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }
  
  if (!userRole || !allowedRoles.includes(userRole)) {
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// 创建应用路由组件
const AppRoutes: React.FC = () => (
  <Routes>
    {/* 主入口页面 - 重定向到登录页面 */}
    <Route path="/" element={<Navigate to="/auth/login" replace />} />

    {/* Public routes (Auth) */}
    <Route 
      path="/auth" 
      element={
        <PublicRoute>
          <AuthPage />
        </PublicRoute>
      }
    >
      <Route index element={<Navigate to="/auth/login" replace />} />
      <Route path="login" element={<Login />} />
      <Route path="register" element={<Register />} />
    </Route>
    
    {/* Protected routes (App) */}
    <Route 
      path="/app" 
      element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }
    >
      {/* 首页/导航页面 */}
      <Route index element={<IndexPage />} />

      {/* 测试路由 */}
      <Route path="test" element={<TestPage />} />

      {/* Dashboard route - 主面板 */}
      <Route path="dashboard" element={<Dashboard />} />
      
      {/* 功能演示页面 */}
      <Route path="feature-demo" element={<FeatureDemoPage />} />
      
      {/* 通知中心路由 */}
      <Route path="notifications" element={<NotificationsPage />} />
      
      {/* Rehabilitation Plans routes - 注意路由顺序，特定路由需要在参数路由前定义 */}
      <Route path="rehab-plans/new" element={<RehabPlanForm />} />
      <Route path="rehab-plans/edit/:id" element={<RehabPlanForm />} />
      <Route path="rehab-plans/:id" element={<RehabPlanDetail />} />
      <Route path="rehab-plans" element={<RehabPlans />} />
      
      {/* Exercises routes - 注意路由顺序 */}
      <Route path="exercises/new" element={<ExerciseForm />} />
      <Route path="exercises/edit/:id" element={<ExerciseForm />} />
      <Route path="exercises/:id" element={<ExerciseDetail />} />
      <Route path="exercises" element={<Exercises />} />
      
      {/* Agents routes - 注意路由顺序 */}
      <Route path="agents/new" element={<AgentForm />} />
      <Route path="agents/edit/:id" element={<AgentForm />} />
      <Route path="agents/:id" element={<AgentDetail />} />
      <Route path="agents" element={<Agents />} />
      
      {/* Exercise Recommendations route */}
      <Route path="exercise-recommendations" element={<ExerciseRecommendations />} />
      
      {/* Rehab Assessment routes */}
      <Route path="rehab-assessment" element={<RehabAssessment />} />
      <Route path="rehab-progress" element={<RehabProgress />} />
      
      {/* Profile route */}
      <Route path="profile" element={<Profile />} />
      
      {/* 医生专属路由 */}
      <Route 
        path="doctor" 
        element={<RoleRoute allowedRoles={['doctor']}><DoctorDashboard /></RoleRoute>}
      >
        <Route index element={<Navigate to="/app/doctor/patients" replace />} />
        <Route path="patients" element={<PatientManagement />} />
        <Route path="health-records/:patientId?" element={<HealthRecords />} />
        <Route path="follow-ups" element={<FollowUpManagement />} />
        <Route path="monitoring/:patientId?" element={<DataMonitoring />} />
        <Route path="communications/:patientId?" element={<Communication />} />
        <Route path="statistics" element={<Statistics />} />
        <Route path="informed-consent" element={<InformedConsent />} />
        {/* 医生端知情同意文档管理 */}
        <Route path="documents/templates" element={<ConsentTemplateList />} />
        <Route path="documents/:documentId" element={<ConsentDocumentView />} />
        <Route path="documents" element={<ConsentDocumentList />} />
      </Route>
      
      {/* 健康管理师专属路由 */}
      <Route 
        path="health-manager" 
        element={<RoleRoute allowedRoles={['health_manager']}><HealthManagerDashboard /></RoleRoute>}
      >
        <Route index element={<Navigate to="/app/health-manager/patients" replace />} />
        <Route path="patients" element={<PatientManagement />} />
        <Route path="health-records/:patientId?" element={<HealthRecords />} />
        <Route path="health-data-timeline/:patientId?" element={<HealthDataTimelinePage />} />
        <Route path="thresholds/:patientId?" element={<HealthThresholdPage />} />
        <Route path="follow-ups" element={<FollowUpManagement />} />
        <Route path="monitoring/:patientId?" element={<DataMonitoring />} />
        <Route path="communications/:patientId?" element={<Communication />} />
        <Route path="statistics" element={<Statistics />} />
        {/* 健康管理师端知情同意文档管理 */}
        <Route path="documents/templates" element={<ConsentTemplateList />} />
        <Route path="documents/:documentId" element={<ConsentDocumentView />} />
        <Route path="documents" element={<ConsentDocumentList />} />
      </Route>
      
      {/* 患者专属路由 */}
      <Route 
        path="patient" 
        element={<RoleRoute allowedRoles={['patient']}><PatientDashboard /></RoleRoute>}
      >
        <Route index element={<Navigate to="/app/patient/main-dashboard" replace />} />
        <Route path="main-dashboard" element={<PatientMainDashboard />} />
        <Route path="health-records" element={<PatientHealthRecords />} />
        <Route path="daily-records" element={<DailyRecords />} />
        <Route path="devices" element={<DeviceBinding />} />
        <Route path="communications" element={<PatientCommunication />} />
        <Route path="statistics" element={<PatientStatistics />} />
        {/* 患者端知情同意文档路由 - 注意路由顺序 */}
        <Route path="documents/:documentId/sign" element={<ConsentDocumentView />} />
        <Route path="documents/:documentId" element={<ConsentDocumentView />} />
        <Route path="documents/templates" element={<ConsentTemplateList />} />
        <Route path="documents" element={<ConsentDocumentList />} />
      </Route>
      
      {/* 系统管理员专属路由 */}
      <Route 
        path="admin" 
        element={<RoleRoute allowedRoles={['admin']}><AdminDashboard /></RoleRoute>}
      >
        <Route index element={<Navigate to="/app/admin/doctors" replace />} />
        <Route path="doctors" element={<DoctorManagement />} />
        <Route path="patients" element={<AdminPatientManagement />} />
        <Route path="health-managers" element={<HealthManagerManagement />} />
        <Route path="organizations" element={<OrganizationManagement />} />
        <Route path="tags" element={<TagManagement />} />
        <Route path="devices" element={<DeviceManagement />} />
        <Route path="visualization" element={<DataVisualization />} />
        <Route path="audit-logs" element={<AuditLogsPage />} />
        <Route path="permission-audit" element={<PermissionAuditLog />} />
      </Route>
    </Route>
    
    {/* Not Found route */}
    <Route path="*" element={<NotFound />} />
  </Routes>
);

// 导出路由组件
export { AppRoutes };
export default AppRoutes; 