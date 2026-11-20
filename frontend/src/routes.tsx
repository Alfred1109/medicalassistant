import React from 'react';
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from './store';
import { CircularProgress, Box } from '@mui/material';

// Layout
import Layout from './components/Layout/Layout';
import { APP_ROUTES, AppRouteNode } from './config/appRoutes';

// IndexPage - 新添加的入口页面
import IndexPage from './pages/IndexPage';

// Auth Pages
import AuthPage from './pages/Auth/AuthPage';
import Login from './pages/Auth/Login';
import Register from './pages/Auth/Register';

// App Pages
import Dashboard from './pages/Dashboard';
import RehabPlans from './pages/RehabPlan/RehabPlans';
import RehabPlanDetail from './pages/RehabPlan/RehabPlanDetail';
import RehabPlanForm from './pages/RehabPlan/RehabPlanForm';
import { PatientPlanList, PatientPlanDetail } from './pages/RehabPlan/PatientPlans';
import ClinicianPlanWorkbench from './pages/RehabPlan/ClinicianPlanWorkbench';
import Agents from './pages/Agent/Agents';
import AgentDetail from './pages/Agent/AgentDetail';
import AgentForm from './pages/Agent/AgentForm';
import Profile from './pages/Profile/Profile';
import NotFound from './pages/NotFound';

// 通知中心组件
import NotificationsPage from './pages/NotificationsPage';
import FollowUpDetailPage from './pages/FollowUpDetailPage';
import QualityControlWorkbench from './pages/Quality/QualityControlWorkbench';

function RehabPlansEntry() {
  const role = useSelector((state: RootState) => state.auth.user?.role);
  return role === 'patient' ? <PatientPlanList /> :
    role === 'doctor' || role === 'health_manager' ? <ClinicianPlanWorkbench /> : <RehabPlans />;
}

function RehabPlanDetailEntry() {
  const role = useSelector((state: RootState) => state.auth.user?.role);
  return role === 'patient' ? <PatientPlanDetail /> : <RehabPlanDetail />;
}

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

// 表单平台（113.44）嵌入填报（首轮隔离联调）
import FormFillEmbedPage from './pages/Integration/FormFillEmbedPage';
import FormFillTasksPage from './pages/Integration/FormFillTasksPage';

import HealthManagerDashboard from './pages/HealthManager/HealthManagerDashboard';
import HealthDataTimelinePage from './pages/HealthManager/HealthDataTimelinePage';
import HealthThresholdPage from './pages/HealthManager/HealthThresholdPage';

import PatientDashboard from './pages/Patient/PatientDashboard';
import PatientMainDashboard from './pages/Patient/PatientMainDashboard';
import PatientHealthRecords from './pages/Patient/HealthRecords';
import DailyRecords from './pages/Patient/DailyRecords';
import DeviceBinding from './pages/Patient/DeviceBinding';
import PatientDevices from './pages/Clinical/PatientDevices';
import PatientCommunication from './pages/Patient/Communication';
import PatientStatistics from './pages/Patient/Statistics';
import PatientEducation from './pages/Patient/Education';
import PatientHealthStatus from './pages/Patient/HealthStatus';
import PatientMyFollowUps from './pages/Patient/MyFollowUps';

// 知情同意文档相关页面
import ConsentDocumentList from './pages/Patient/ConsentDocumentList';
import ConsentDocumentView from './pages/Patient/ConsentDocumentView';
import Questionnaires from './pages/Patient/Questionnaires';
import TodoCenter from './pages/Patient/TodoCenter';
import ConsentTemplateList from './pages/Patient/ConsentTemplateList';

import AdminDashboard from './pages/Admin/AdminDashboard';
import DoctorManagement from './pages/Admin/DoctorManagement';
import AdminPatientManagement from './pages/Admin/PatientManagement';
import PatientLinks from './pages/Admin/PatientLinks';
import AccountBindings from './pages/Admin/AccountBindings';
import AccessApplications from './pages/Admin/AccessApplications';
import IntegrationRuns from './pages/Admin/IntegrationRuns';
import ClinicalWorkbench from './pages/Clinical/ClinicalWorkbench';
import IcfWorkbenchPage from './pages/Clinical/IcfWorkbenchPage';
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

// 系统设置页面
import SystemSettings from './pages/Settings/SystemSettings';

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
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('页面渲染错误:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
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
  const { token, user, checking, mode } = useSelector((state: RootState) => state.auth);
  if (checking) return <LoadingFallback />;
  const isAuthenticated = Boolean(user && (mode === 'oidc' || token));
  
  if (!isAuthenticated) {
    // Redirect to login if not authenticated
    return <Navigate to="/auth" replace />;
  }
  
  return <>{children}</>;
};

// Public Route Component (accessible only if NOT authenticated)
export const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token, user, checking, mode } = useSelector((state: RootState) => state.auth);
  if (checking) return <LoadingFallback />;
  const isAuthenticated = Boolean(user && (mode === 'oidc' || token));
  
  if (isAuthenticated && !new URLSearchParams(window.location.search).has('error')) {
    // Redirect to dashboard if already authenticated
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// 角色路由守卫组件
export const RoleRoute: React.FC<{ children: React.ReactNode, allowedRoles: string[] }> = ({ children, allowedRoles }) => {
  const { token, user, checking, mode } = useSelector((state: RootState) => state.auth);
  if (checking) return <LoadingFallback />;
  const isAuthenticated = Boolean(user && (mode === 'oidc' || token));
  
  if (!isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }
  
  if (!user || !allowedRoles.includes(user.role)) {
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// Legacy paths remain inside the same authenticated and role-guarded /app tree.
const LegacyRedirect: React.FC<{ to: string }> = ({ to }) => {
  const params = useParams();
  const location = useLocation();
  const rest = params['*'] || '';
  return <Navigate to={{ pathname: rest ? `${to}/${rest}` : to, search: location.search, hash: location.hash }} replace />;
};

// 页面绑定（路径、角色、菜单在 config/appRoutes.ts，这里只登记每个 id 画什么）
const ROUTE_ELEMENTS: Record<string, React.ReactNode> = {
  index: <IndexPage />,
  dashboard: <Dashboard />,
  notifications: <NotificationsPage />,
  'follow-up-detail': <FollowUpDetailPage />,
  'quality-control': <QualityControlWorkbench />,
  'rehab-plans.new': <RehabPlanForm />,
  'rehab-plans.edit': <RehabPlanForm />,
  'rehab-plans.detail': <RehabPlanDetailEntry />,
  'rehab-plans': <RehabPlansEntry />,
  'exercises.new': <ExerciseForm />,
  'exercises.edit': <ExerciseForm />,
  'exercises.detail': <ExerciseDetail />,
  exercises: <Exercises />,
  'agents.new': <AgentForm />,
  'agents.edit': <AgentForm />,
  'agents.detail': <AgentDetail />,
  agents: <Agents />,
  'exercise-recommendations': <ExerciseRecommendations />,
  'rehab-assessment': <RehabAssessment />,
  'rehab-progress': <RehabProgress />,
  profile: <Profile />,
  settings: <SystemSettings />,
  'app.not-found': <NotFound />,
  doctor: <DoctorDashboard />,
  'doctor.index': <Navigate to="/app/doctor/patients" replace />,
  'doctor.patients': <PatientManagement />,
  'doctor.health-records': <HealthRecords />,
  'doctor.follow-ups': <FollowUpManagement />,
  'doctor.form-fill': <FormFillTasksPage />,
  'doctor.clinical': <ClinicalWorkbench />,
  'doctor.icf': <IcfWorkbenchPage />,
  'doctor.devices': <PatientDevices />,
  'doctor.monitoring': <DataMonitoring />,
  'doctor.communications': <Communication />,
  'doctor.statistics': <Statistics />,
  'doctor.informed-consent': <InformedConsent />,
  'doctor.documents': <ConsentDocumentList />,
  'doctor.documents.templates': <ConsentTemplateList />,
  'doctor.documents.detail': <ConsentDocumentView />,
  'doctor.form-fill.detail': <FormFillEmbedPage />,
  'health-manager': <HealthManagerDashboard />,
  'health-manager.index': <Navigate to="/app/health-manager/patients" replace />,
  'health-manager.patients': <PatientManagement />,
  'health-manager.health-records': <HealthRecords />,
  'health-manager.health-data-timeline': <HealthDataTimelinePage />,
  'health-manager.thresholds': <HealthThresholdPage />,
  'health-manager.follow-ups': <FollowUpManagement />,
  'health-manager.form-fill': <FormFillTasksPage />,
  'health-manager.clinical': <ClinicalWorkbench />,
  'health-manager.icf': <IcfWorkbenchPage />,
  'health-manager.devices': <PatientDevices />,
  'health-manager.monitoring': <DataMonitoring />,
  'health-manager.communications': <Communication />,
  'health-manager.statistics': <Statistics />,
  'health-manager.documents': <ConsentDocumentList />,
  'health-manager.documents.templates': <ConsentTemplateList />,
  'health-manager.documents.detail': <ConsentDocumentView />,
  'health-manager.form-fill.detail': <FormFillEmbedPage />,
  patient: <PatientDashboard />,
  'patient.index': <Navigate to="/app/patient/main-dashboard" replace />,
  'patient.main-dashboard': <PatientMainDashboard />,
  'patient.todos': <TodoCenter />,
  'patient.questionnaires': <Questionnaires />,
  'patient.questionnaires.detail': <Questionnaires />,
  'patient.health-records': <PatientHealthRecords />,
  'patient.clinical': <ClinicalWorkbench />,
  'patient.daily-records': <DailyRecords />,
  'patient.devices': <DeviceBinding />,
  'patient.communications': <PatientCommunication />,
  'patient.statistics': <PatientStatistics />,
  'patient.education': <PatientEducation />,
  'patient.follow-ups': <PatientMyFollowUps />,
  'patient.health-status': <PatientHealthStatus />,
  'patient.documents': <ConsentDocumentList />,
  'patient.documents.templates': <ConsentTemplateList />,
  'patient.documents.sign': <ConsentDocumentView />,
  'patient.documents.detail': <ConsentDocumentView />,
  admin: <AdminDashboard />,
  'admin.index': <Navigate to="/app/admin/doctors" replace />,
  'admin.doctors': <DoctorManagement />,
  'admin.patients': <AdminPatientManagement />,
  'admin.patient-links': <PatientLinks />,
  'admin.form-fill': <FormFillTasksPage />,
  'admin.form-fill.detail': <FormFillEmbedPage />,
  'admin.account-bindings': <AccountBindings />,
  'admin.access-applications': <AccessApplications />,
  'admin.integration-runs': <IntegrationRuns />,
  'admin.clinical': <ClinicalWorkbench />,
  'admin.health-managers': <HealthManagerManagement />,
  'admin.organizations': <OrganizationManagement />,
  'admin.tags': <TagManagement />,
  'admin.devices': <DeviceManagement />,
  'admin.visualization': <DataVisualization />,
  'admin.audit-logs': <AuditLogsPage />,
  'admin.permission-audit': <PermissionAuditLog />,
  'admin.settings': <SystemSettings />,
};

function renderConfiguredRoutes(nodes: AppRouteNode[]): React.ReactNode {
  return nodes.map((node) => {
    const page = ROUTE_ELEMENTS[node.id];
    if (page === undefined) {
      throw new Error(`路由 ${node.id} 没有对应页面`);
    }
    const element = node.allowedRoles
      ? <RoleRoute allowedRoles={node.allowedRoles}>{page}</RoleRoute>
      : page;
    if (node.index) {
      return <Route key={node.id} index element={element} />;
    }
    return (
      <Route key={node.id} path={node.path} element={element}>
        {node.children?.length ? renderConfiguredRoutes(node.children) : null}
      </Route>
    );
  });
}

// 创建应用路由组件
const AppRoutes: React.FC = () => (
  <Routes>
    {/* 主入口页面 - 重定向到登录页面 */}
    <Route path="/" element={<Navigate to="/auth/login" replace />} />

    {/* 兼容线上历史链接，目标仍受 /app 身份和角色检查。 */}
    <Route path="/rehab-plans/*" element={<LegacyRedirect to="/app/rehab-plans" />} />
    <Route path="/exercises/*" element={<LegacyRedirect to="/app/exercises" />} />
    <Route path="/agents/*" element={<LegacyRedirect to="/app/agents" />} />
    <Route path="/patient/*" element={<LegacyRedirect to="/app/patient" />} />
    <Route path="/doctor/*" element={<LegacyRedirect to="/app/doctor" />} />
    <Route path="/health-manager/*" element={<LegacyRedirect to="/app/health-manager" />} />

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
      <Route path="oidc/complete" element={<Login />} />
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
      {renderConfiguredRoutes(APP_ROUTES)}
    </Route>
    
    {/* Not Found route */}
    <Route path="*" element={<NotFound />} />
  </Routes>
);

// 导出路由组件
export { AppRoutes };
export default AppRoutes;
