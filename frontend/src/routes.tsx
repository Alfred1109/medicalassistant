import React from 'react';
import { Navigate } from 'react-router-dom';
import { RouteObject } from 'react-router';

// Layout
import Layout from './components/Layout/Layout';

// IndexPage - 新添加的入口页面
import IndexPage from './pages/IndexPage';

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
import NotFound from './pages/NotFound';

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

// 康复评估相关页面
import RehabAssessment from './pages/Assessment/RehabAssessment';
import RehabProgress from './pages/Assessment/RehabProgress';

// 训练推荐相关页面
import ExerciseRecommendations from './pages/Recommendations/ExerciseRecommendations';

// Protected Route Component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Check if user is authenticated
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (!isAuthenticated) {
    // Redirect to login if not authenticated
    return <Navigate to="/auth" replace />;
  }
  
  return <>{children}</>;
};

// Public Route Component (accessible only if NOT authenticated)
const PublicRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isAuthenticated = localStorage.getItem('token') !== null;
  
  if (isAuthenticated) {
    // Redirect to dashboard if already authenticated
    return <Navigate to="/app/dashboard" replace />;
  }
  
  return <>{children}</>;
};

// 角色路由守卫组件
const RoleRoute: React.FC<{ children: React.ReactNode, allowedRoles: string[] }> = ({ children, allowedRoles }) => {
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

const routes: RouteObject[] = [
  // 主入口页面 - 无需验证，直接访问
  {
    path: '/',
    element: <IndexPage />,
    index: true,
  },

  // Public routes (Auth)
  {
    path: '/auth',
    element: (
      <PublicRoute>
        <AuthPage />
      </PublicRoute>
    ),
    children: [
      { index: true, element: <Navigate to="/auth/login" replace /> },
      { path: 'login', element: <Login /> },
      { path: 'register', element: <Register /> },
    ],
  },
  
  // Protected routes (App) - Partially uncommented for debugging
  {
    path: '/app',
    element: (
      <ProtectedRoute>
        <Layout />
      </ProtectedRoute>
    ),
    children: [
      // Dashboard route - 主面板
      { path: 'dashboard', element: <Dashboard /> },
      
      // Rehabilitation Plans routes
      { path: 'rehab-plans', element: <RehabPlans /> },
      { path: 'rehab-plans/:id', element: <RehabPlanDetail /> },
      { path: 'rehab-plans/new', element: <RehabPlanForm /> },
      { path: 'rehab-plans/edit/:id', element: <RehabPlanForm /> },
      
      // Exercises routes
      { path: 'exercises', element: <Exercises /> },
      { path: 'exercises/:id', element: <ExerciseDetail /> },
      { path: 'exercises/new', element: <ExerciseForm /> },
      { path: 'exercises/edit/:id', element: <ExerciseForm /> },
      
      // Agents routes
      { path: 'agents', element: <Agents /> },
      { path: 'agents/:id', element: <AgentDetail /> },
      { path: 'agents/new', element: <AgentForm /> },
      { path: 'agents/edit/:id', element: <AgentForm /> },
      
      // Exercise Recommendations route
      { path: 'exercise-recommendations', element: <ExerciseRecommendations /> },
      
      // Rehab Assessment routes
      { path: 'rehab-assessment', element: <RehabAssessment /> },
      { path: 'rehab-progress', element: <RehabProgress /> },
      
      // Profile route
      { path: 'profile', element: <Profile /> },
      
      // 医生专属路由
      { 
        path: 'doctor',
        element: <RoleRoute allowedRoles={['doctor']}><DoctorDashboard /></RoleRoute>,
        children: [
          { index: true, element: <Navigate to="/app/doctor/patients" replace /> },
          { path: 'patients', element: <PatientManagement /> },
          { path: 'health-records/:patientId?', element: <HealthRecords /> },
          { path: 'follow-ups', element: <FollowUpManagement /> },
          { path: 'monitoring/:patientId?', element: <DataMonitoring /> },
          { path: 'communications/:patientId?', element: <Communication /> },
          { path: 'statistics', element: <Statistics /> },
          { path: 'informed-consent', element: <InformedConsent /> },
          // 医生端知情同意文档管理
          { path: 'documents', element: <ConsentDocumentList /> },
          { path: 'documents/:documentId', element: <ConsentDocumentView /> },
          { path: 'documents/templates', element: <ConsentTemplateList /> },
        ]
      },
      
      // 健康管理师专属路由
      { 
        path: 'health-manager',
        element: <RoleRoute allowedRoles={['health_manager']}><HealthManagerDashboard /></RoleRoute>,
        children: [
          { index: true, element: <Navigate to="/app/health-manager/patients" replace /> },
          { path: 'patients', element: <PatientManagement /> },
          { path: 'health-records/:patientId?', element: <HealthRecords /> },
          { path: 'health-data-timeline/:patientId?', element: <HealthDataTimelinePage /> },
          { path: 'thresholds/:patientId?', element: <HealthThresholdPage /> },
          { path: 'follow-ups', element: <FollowUpManagement /> },
          { path: 'monitoring/:patientId?', element: <DataMonitoring /> },
          { path: 'communications/:patientId?', element: <Communication /> },
          { path: 'statistics', element: <Statistics /> },
          // 健康管理师端知情同意文档管理
          { path: 'documents', element: <ConsentDocumentList /> },
          { path: 'documents/:documentId', element: <ConsentDocumentView /> },
          { path: 'documents/templates', element: <ConsentTemplateList /> },
        ]
      },
      
      // 患者专属路由
      { 
        path: 'patient',
        element: <RoleRoute allowedRoles={['patient']}><PatientDashboard /></RoleRoute>,
        children: [
          { index: true, element: <Navigate to="/app/patient/health-records" replace /> },
          { path: 'health-records', element: <PatientHealthRecords /> },
          { path: 'daily-records', element: <DailyRecords /> },
          { path: 'devices', element: <DeviceBinding /> },
          { path: 'communications', element: <PatientCommunication /> },
          { path: 'statistics', element: <PatientStatistics /> },
          // 患者端知情同意文档路由
          { path: 'documents', element: <ConsentDocumentList /> },
          { path: 'documents/:documentId', element: <ConsentDocumentView /> },
          { path: 'documents/:documentId/sign', element: <ConsentDocumentView /> },
          { path: 'documents/templates', element: <ConsentTemplateList /> },
        ]
      },
      
      // 系统管理员专属路由
      { 
        path: 'admin',
        element: <RoleRoute allowedRoles={['admin']}><AdminDashboard /></RoleRoute>,
        children: [
          { index: true, element: <Navigate to="/app/admin/doctors" replace /> },
          { path: 'doctors', element: <DoctorManagement /> },
          { path: 'patients', element: <AdminPatientManagement /> },
          { path: 'health-managers', element: <HealthManagerManagement /> },
          { path: 'organizations', element: <OrganizationManagement /> },
          { path: 'tags', element: <TagManagement /> },
          { path: 'devices', element: <DeviceManagement /> },
          { path: 'visualization', element: <DataVisualization /> },
        ]
      },
    ],
  },
  
  // Not Found route
  {
    path: '*',
    element: <NotFound />
  }
];

export default routes; 