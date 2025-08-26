import React from 'react';
import SimpleDevelopmentApp from './SimpleDevelopmentApp';

// 为未实现的页面创建备用组件
export const FallbackIndexPage = () => (
  <SimpleDevelopmentApp 
    pageName="首页" 
    description="首页功能正在开发中，稍后将提供完整的导航和功能概览。"
  />
);

export const FallbackAuthPage = () => (
  <SimpleDevelopmentApp 
    pageName="认证页面" 
    description="用户登录和注册功能正在开发中，稍后将支持多种认证方式。"
  />
);

export const FallbackDashboard = () => (
  <SimpleDevelopmentApp 
    pageName="控制面板" 
    description="用户控制面板正在开发中，稍后将提供个性化的数据统计和功能快捷入口。"
  />
);

// 康复计划相关页面
export const FallbackRehabPlans = () => (
  <SimpleDevelopmentApp 
    pageName="康复计划管理" 
    description="康复计划管理功能正在开发中，稍后将支持计划的创建、编辑和跟踪。"
  />
);

export const FallbackRehabPlanDetail = () => (
  <SimpleDevelopmentApp 
    pageName="康复计划详情" 
    description="康复计划详情页面正在开发中，稍后将提供完整的计划查看和进度跟踪。"
  />
);

export const FallbackRehabPlanForm = () => (
  <SimpleDevelopmentApp 
    pageName="康复计划表单" 
    description="康复计划创建/编辑表单正在开发中，稍后将支持完整的计划配置。"
  />
);

// 康复练习相关页面
export const FallbackExercises = () => (
  <SimpleDevelopmentApp 
    pageName="康复练习库" 
    description="康复练习库功能正在开发中，稍后将提供丰富的练习资源和分类浏览。"
  />
);

export const FallbackExerciseDetail = () => (
  <SimpleDevelopmentApp 
    pageName="康复练习详情" 
    description="康复练习详情页面正在开发中，稍后将提供详细的练习说明和演示视频。"
  />
);

export const FallbackExerciseForm = () => (
  <SimpleDevelopmentApp 
    pageName="康复练习表单" 
    description="康复练习创建/编辑表单正在开发中，稍后将支持完整的练习配置。"
  />
);

// 智能助手相关页面
export const FallbackAgents = () => (
  <SimpleDevelopmentApp 
    pageName="智能助手列表" 
    description="智能助手列表页面正在开发中，稍后将提供可用的智能助手及其功能介绍。"
  />
);

export const FallbackAgentDetail = () => (
  <SimpleDevelopmentApp 
    pageName="智能助手详情" 
    description="智能助手详情页面正在开发中，稍后将提供助手的详细功能和使用方法。"
  />
);

export const FallbackAgentForm = () => (
  <SimpleDevelopmentApp 
    pageName="智能助手配置" 
    description="智能助手配置页面正在开发中，稍后将支持自定义智能助手的功能和行为。"
  />
);

// 康复评估相关页面
export const FallbackRehabAssessment = () => (
  <SimpleDevelopmentApp 
    pageName="康复评估" 
    description="康复评估功能正在开发中，稍后将提供专业的康复状态评估和报告生成。"
  />
);

export const FallbackRehabProgress = () => (
  <SimpleDevelopmentApp 
    pageName="康复进度" 
    description="康复进度跟踪功能正在开发中，稍后将提供直观的进度可视化和趋势分析。"
  />
);

// 训练推荐相关页面
export const FallbackExerciseRecommendations = () => (
  <SimpleDevelopmentApp 
    pageName="训练推荐" 
    description="智能训练推荐功能正在开发中，稍后将基于个人情况提供定制化训练建议。"
  />
);

// 用户档案
export const FallbackProfile = () => (
  <SimpleDevelopmentApp 
    pageName="用户档案" 
    description="用户档案管理功能正在开发中，稍后将支持个人信息的查看和编辑。"
  />
);

// 角色相关页面
export const FallbackDoctorDashboard = () => (
  <SimpleDevelopmentApp 
    pageName="医生工作站" 
    description="医生工作站功能正在开发中，稍后将支持患者管理、健康记录查看和康复计划制定。"
  />
);

export const FallbackPatientDashboard = () => (
  <SimpleDevelopmentApp 
    pageName="患者控制面板" 
    description="患者控制面板功能正在开发中，稍后将提供健康记录、康复训练和医生沟通等功能。"
  />
);

export const FallbackHealthManagerDashboard = () => (
  <SimpleDevelopmentApp 
    pageName="健康管理师工作站" 
    description="健康管理师工作站功能正在开发中，稍后将提供患者健康数据管理和跟踪功能。"
  />
);

export const FallbackAdminDashboard = () => (
  <SimpleDevelopmentApp 
    pageName="系统管理" 
    description="系统管理功能正在开发中，稍后将支持用户管理、数据统计和系统配置等功能。"
  />
);

export const FallbackNotFoundPage = () => (
  <SimpleDevelopmentApp 
    pageName="404 - 页面未找到" 
    description="您访问的页面不存在或已被移除。"
  />
); 