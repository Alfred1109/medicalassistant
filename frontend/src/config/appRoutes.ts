// 应用路由与侧边菜单的唯一配置源（单一事实）。
//
// 路由表（APP_ROUTES）与菜单（NAV_BASE / NAV_SECTIONS）都由本文件派生：
// - 路径、层级、角色守卫、菜单元数据只在这里声明一次；
// - src/routes.tsx 按 APP_ROUTES 渲染路由表；
// - src/components/Layout/Layout.tsx 按 NAV_* 渲染菜单；
// - frontend/tests/navigation-routes.test.cjs 校验菜单与路由表的双向一致性
//   （菜单路径必须在路由表里，反之路由必须出现在菜单里或显式标记 hidden）。
//
// 语义约定：
// - allowedRoles：路由访问守卫（RoleRoute），缺省表示登录即可访问；
// - menu.roles：菜单可见角色，缺省继承 allowedRoles（产品上刻意不同时才显式声明，
//   例如「质量监管」路由全员可访问，但只在医护/管理菜单里出现）；
// - hidden：有路由、无菜单入口（详情页、通知中心等），必须显式声明，
//   避免路由表与菜单漂移。

export type MenuIconKey =
  | 'home'
  | 'accessibility'
  | 'psychology'
  | 'fitnessCenter'
  | 'assessment'
  | 'trendingUp'
  | 'directionsRun'
  | 'star'
  | 'favorite'
  | 'admin'
  | 'doctor'
  | 'patient'
  | 'healthManager'
  | 'folder'
  | 'eventNote'
  | 'assignment'
  | 'monitorHeart'
  | 'chat'
  | 'queryStats'
  | 'description'
  | 'devices'
  | 'insights'
  | 'history'
  | 'link'
  | 'business'
  | 'label'
  | 'menuBook'
  | 'tune'
  | 'timeline'
  | 'dashboard';

export type MenuChipColor =
  | 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';

export interface MenuChip {
  text: string;
  color: MenuChipColor;
}

export interface RouteMenuMeta {
  name: string;
  icon: MenuIconKey;
  /** 菜单可见角色；缺省继承路由守卫 allowedRoles */
  roles?: string[];
  chip?: MenuChip;
}

export interface AppRouteNode {
  /** 稳定 id：路由表与菜单都用它互指（元素注册表按 id 索引） */
  id: string;
  /** react-router 相对路径（相对父路由）；index 路由省略 */
  path?: string;
  /** index 路由（父路径下的默认路由） */
  index?: boolean;
  /** 路由访问守卫；缺省 = 登录即可访问 */
  allowedRoles?: string[];
  /** 菜单元数据；缺省 = 该路由不出现在菜单里 */
  menu?: RouteMenuMeta;
  /** 有路由、无菜单入口（必须显式声明，供一致性测试守护） */
  hidden?: boolean;
  children?: AppRouteNode[];
}

// 角色分组：医生 / 健康管理师 / 患者 / 管理员
const MEDICAL_ROLES = ['doctor', 'health_manager', 'admin'];
const ADMIN_ROLES = ['admin'];
const DOCTOR_ROLES = ['doctor'];
const HEALTH_MANAGER_ROLES = ['health_manager'];
const PATIENT_ROLES = ['patient'];

export const APP_ROUTES: AppRouteNode[] = [
  { id: 'index', index: true, hidden: true },
  { id: 'dashboard', path: 'dashboard', menu: { name: '首页', icon: 'home' } },
  { id: 'notifications', path: 'notifications', hidden: true },
  { id: 'follow-up-detail', path: 'follow-ups/:followUpId', hidden: true },
  {
    id: 'quality-control',
    path: 'quality-control',
    menu: { name: '质量监管', icon: 'assessment', roles: ['admin', 'doctor', 'health_manager'] },
  },
  { id: 'rehab-plans.new', path: 'rehab-plans/new', hidden: true },
  { id: 'rehab-plans.edit', path: 'rehab-plans/edit/:id', hidden: true },
  { id: 'rehab-plans.detail', path: 'rehab-plans/:id', hidden: true },
  { id: 'rehab-plans', path: 'rehab-plans', menu: { name: '康复计划', icon: 'fitnessCenter' } },
  { id: 'exercises.new', path: 'exercises/new', hidden: true },
  { id: 'exercises.edit', path: 'exercises/edit/:id', hidden: true },
  { id: 'exercises.detail', path: 'exercises/:id', hidden: true },
  { id: 'exercises', path: 'exercises', menu: { name: '练习库', icon: 'directionsRun' } },
  {
    id: 'agents.new',
    path: 'agents/new',
    allowedRoles: MEDICAL_ROLES,
    hidden: true,
  },
  {
    id: 'agents.edit',
    path: 'agents/edit/:id',
    allowedRoles: MEDICAL_ROLES,
    hidden: true,
  },
  {
    id: 'agents.detail',
    path: 'agents/:id',
    allowedRoles: MEDICAL_ROLES,
    hidden: true,
  },
  {
    id: 'agents',
    path: 'agents',
    allowedRoles: MEDICAL_ROLES,
    menu: { name: '智能问答', icon: 'star' },
  },
  {
    id: 'exercise-recommendations',
    path: 'exercise-recommendations',
    menu: { name: '训练推荐', icon: 'favorite' },
  },
  {
    id: 'rehab-assessment',
    path: 'rehab-assessment',
    menu: { name: '康复评估', icon: 'assessment' },
  },
  {
    id: 'rehab-progress',
    path: 'rehab-progress',
    menu: { name: '进度报告', icon: 'trendingUp' },
  },
  { id: 'profile', path: 'profile', hidden: true },
  { id: 'settings', path: 'settings', hidden: true },
  { id: 'app.not-found', path: '*', hidden: true },
  {
    id: 'doctor',
    path: 'doctor',
    allowedRoles: DOCTOR_ROLES,
    menu: { name: '医生工作站', icon: 'doctor' },
    children: [
      { id: 'doctor.index', index: true, hidden: true },
      { id: 'doctor.patients', path: 'patients', menu: { name: '患者管理', icon: 'patient' } },
      { id: 'doctor.health-records', path: 'health-records/:patientId?', menu: { name: '健康档案', icon: 'folder' } },
      { id: 'doctor.follow-ups', path: 'follow-ups', menu: { name: '随访管理', icon: 'eventNote' } },
      { id: 'doctor.form-fill', path: 'form-fill', menu: { name: '问卷填报', icon: 'assignment' } },
      { id: 'doctor.clinical', path: 'clinical', menu: { name: '患者记录', icon: 'folder' } },
      { id: 'doctor.icf', path: 'icf', menu: { name: 'ICF 评估', icon: 'accessibility' } },
      { id: 'doctor.devices', path: 'devices', menu: { name: '患者设备', icon: 'devices' } },
      { id: 'doctor.monitoring', path: 'monitoring/:patientId?', menu: { name: '数据监测', icon: 'monitorHeart' } },
      { id: 'doctor.communications', path: 'communications/:patientId?', menu: { name: '医患沟通', icon: 'chat' } },
      { id: 'doctor.statistics', path: 'statistics', menu: { name: '数据统计', icon: 'queryStats' } },
      { id: 'doctor.informed-consent', path: 'informed-consent', menu: { name: '知情同意', icon: 'description' } },
      { id: 'doctor.documents', path: 'documents', menu: { name: '文档管理', icon: 'assignment' } },
      { id: 'doctor.documents.templates', path: 'documents/templates', hidden: true },
      { id: 'doctor.documents.detail', path: 'documents/:documentId', hidden: true },
      { id: 'doctor.form-fill.detail', path: 'form-fill/:taskId', hidden: true },
    ],
  },
  {
    id: 'health-manager',
    path: 'health-manager',
    allowedRoles: HEALTH_MANAGER_ROLES,
    menu: { name: '健康管理师', icon: 'healthManager' },
    children: [
      { id: 'health-manager.index', index: true, hidden: true },
      { id: 'health-manager.patients', path: 'patients', menu: { name: '患者管理', icon: 'patient' } },
      { id: 'health-manager.health-records', path: 'health-records/:patientId?', menu: { name: '健康档案', icon: 'folder' } },
      { id: 'health-manager.health-data-timeline', path: 'health-data-timeline/:patientId?', menu: { name: '健康数据时间线', icon: 'timeline' } },
      { id: 'health-manager.thresholds', path: 'thresholds/:patientId?', menu: { name: '健康数据阈值', icon: 'tune' } },
      { id: 'health-manager.follow-ups', path: 'follow-ups', menu: { name: '随访管理', icon: 'eventNote' } },
      { id: 'health-manager.form-fill', path: 'form-fill', menu: { name: '问卷填报', icon: 'assignment' } },
      { id: 'health-manager.clinical', path: 'clinical', menu: { name: '患者记录', icon: 'folder' } },
      { id: 'health-manager.icf', path: 'icf', menu: { name: 'ICF 评估', icon: 'accessibility' } },
      { id: 'health-manager.devices', path: 'devices', menu: { name: '患者设备', icon: 'devices' } },
      { id: 'health-manager.monitoring', path: 'monitoring/:patientId?', menu: { name: '数据监测', icon: 'monitorHeart' } },
      { id: 'health-manager.communications', path: 'communications/:patientId?', menu: { name: '医患沟通', icon: 'chat' } },
      { id: 'health-manager.statistics', path: 'statistics', menu: { name: '数据统计', icon: 'queryStats' } },
      { id: 'health-manager.documents', path: 'documents', menu: { name: '文档管理', icon: 'assignment' } },
      { id: 'health-manager.documents.templates', path: 'documents/templates', hidden: true },
      { id: 'health-manager.documents.detail', path: 'documents/:documentId', hidden: true },
      { id: 'health-manager.form-fill.detail', path: 'form-fill/:taskId', hidden: true },
    ],
  },
  {
    id: 'patient',
    path: 'patient',
    allowedRoles: PATIENT_ROLES,
    menu: { name: '患者中心', icon: 'patient' },
    children: [
      { id: 'patient.index', index: true, hidden: true },
      { id: 'patient.main-dashboard', path: 'main-dashboard', menu: { name: '主面板', icon: 'dashboard' } },
      { id: 'patient.health-records', path: 'health-records', menu: { name: '健康档案', icon: 'folder' } },
      { id: 'patient.clinical', path: 'clinical', menu: { name: '我的记录', icon: 'folder' } },
      { id: 'patient.daily-records', path: 'daily-records', menu: { name: '日常记录', icon: 'eventNote' } },
      { id: 'patient.devices', path: 'devices', menu: { name: '设备绑定', icon: 'devices' } },
      { id: 'patient.communications', path: 'communications', menu: { name: '医患沟通', icon: 'chat' } },
      { id: 'patient.statistics', path: 'statistics', menu: { name: '数据统计', icon: 'queryStats' } },
      { id: 'patient.education', path: 'education', menu: { name: '宣教材料', icon: 'menuBook' } },
      { id: 'patient.follow-ups', path: 'follow-ups', menu: { name: '我的随访', icon: 'eventNote' } },
      { id: 'patient.health-status', path: 'health-status', menu: { name: '健康指标与预警', icon: 'monitorHeart' } },
      { id: 'patient.documents', path: 'documents', menu: { name: '知情同意文档', icon: 'assignment' } },
      { id: 'patient.documents.templates', path: 'documents/templates', hidden: true },
      { id: 'patient.documents.sign', path: 'documents/:documentId/sign', hidden: true },
      { id: 'patient.documents.detail', path: 'documents/:documentId', hidden: true },
    ],
  },
  {
    id: 'admin',
    path: 'admin',
    allowedRoles: ADMIN_ROLES,
    menu: { name: '管理员', icon: 'admin' },
    children: [
      { id: 'admin.index', index: true, hidden: true },
      { id: 'admin.doctors', path: 'doctors', menu: { name: '医生管理', icon: 'doctor' } },
      { id: 'admin.patients', path: 'patients', menu: { name: '患者管理', icon: 'patient' } },
      { id: 'admin.patient-links', path: 'patient-links', menu: { name: '患者与问卷来源', icon: 'assignment' } },
      { id: 'admin.account-bindings', path: 'account-bindings', menu: { name: '账号绑定管理', icon: 'link' } },
      { id: 'admin.access-applications', path: 'access-applications', menu: { name: '接入申请', icon: 'assignment' } },
      { id: 'admin.integration-runs', path: 'integration-runs', menu: { name: '同步记录', icon: 'history' } },
      { id: 'admin.clinical', path: 'clinical', menu: { name: '患者记录', icon: 'folder' } },
      { id: 'admin.health-managers', path: 'health-managers', menu: { name: '健管师管理', icon: 'healthManager' } },
      { id: 'admin.organizations', path: 'organizations', menu: { name: '组织机构', icon: 'business' } },
      { id: 'admin.tags', path: 'tags', menu: { name: '标签管理', icon: 'label' } },
      { id: 'admin.devices', path: 'devices', menu: { name: '设备查看', icon: 'devices' } },
      { id: 'admin.visualization', path: 'visualization', menu: { name: '数据可视化', icon: 'insights' } },
      { id: 'admin.audit-logs', path: 'audit-logs', menu: { name: '审计日志', icon: 'history', chip: { text: '审', color: 'info' } } },
      { id: 'admin.permission-audit', path: 'permission-audit', hidden: true },
      { id: 'admin.settings', path: 'settings', hidden: true },
    ],
  },
];

export interface NavEntry {
  /** 绑定的路由 id；虚拟分组（无对应路由）不绑定 */
  routeId?: string;
  /** 菜单项 id（虚拟分组必填） */
  id?: string;
  /** 覆盖显示名/图标（缺省取路由的菜单元数据） */
  name?: string;
  icon?: MenuIconKey;
  /** 覆盖可见角色（缺省取路由的菜单可见角色） */
  roles?: string[];
  chip?: MenuChip;
  /** 虚拟分组的路径（不绑定路由时必填） */
  path?: string;
  children?: NavEntry[];
}

export interface NavGroup extends NavEntry {
  path: string;
}

// 基础菜单区（所有角色可见；「康复中心」「智能助手」为虚拟分组，无对应路由）
export const NAV_BASE: NavEntry[] = [
  { routeId: 'dashboard' },
  {
    id: 'rehab-center',
    name: '康复中心',
    icon: 'accessibility',
    path: '/app/rehabilitation',
    children: [
      { routeId: 'rehab-plans' },
      { routeId: 'rehab-assessment' },
      { routeId: 'rehab-progress' },
      { routeId: 'exercises' },
    ],
  },
  {
    id: 'ai-assistant',
    name: '智能助手',
    icon: 'psychology',
    path: '/app/ai-assistant',
    children: [
      { routeId: 'agents' },
      { routeId: 'exercise-recommendations' },
    ],
  },
];

// 角色菜单区（每个分组绑定一个角色分区路由）
export const NAV_SECTIONS: NavGroup[] = [
  {
    id: 'admin',
    routeId: 'admin',
    path: '/app/admin',
    children: [
      { routeId: 'admin.doctors' },
      { routeId: 'admin.patients' },
      { routeId: 'admin.patient-links' },
      { routeId: 'admin.account-bindings' },
      { routeId: 'admin.access-applications' },
      { routeId: 'admin.integration-runs' },
      { routeId: 'admin.clinical' },
      { routeId: 'admin.health-managers' },
      { routeId: 'admin.organizations' },
      { routeId: 'admin.tags' },
      { routeId: 'admin.devices' },
      { routeId: 'admin.visualization' },
      { routeId: 'quality-control' },
      { routeId: 'admin.audit-logs' },
    ],
  },
  {
    id: 'doctor',
    routeId: 'doctor',
    path: '/app/doctor',
    children: [
      { routeId: 'doctor.patients' },
      { routeId: 'doctor.health-records' },
      { routeId: 'doctor.follow-ups' },
      { routeId: 'doctor.form-fill' },
      { routeId: 'doctor.clinical' },
      { routeId: 'doctor.icf' },
      { routeId: 'doctor.devices' },
      { routeId: 'quality-control' },
      { routeId: 'doctor.monitoring' },
      { routeId: 'doctor.communications' },
      { routeId: 'doctor.statistics' },
      { routeId: 'doctor.informed-consent' },
      { routeId: 'doctor.documents' },
    ],
  },
  {
    id: 'patient',
    routeId: 'patient',
    path: '/app/patient',
    children: [
      { routeId: 'patient.main-dashboard' },
      { routeId: 'patient.health-records' },
      { routeId: 'patient.clinical' },
      { routeId: 'patient.daily-records' },
      { routeId: 'patient.devices' },
      { routeId: 'patient.communications' },
      { routeId: 'patient.statistics' },
      { routeId: 'patient.education' },
      { routeId: 'patient.follow-ups' },
      { routeId: 'patient.health-status' },
      { routeId: 'patient.documents' },
    ],
  },
  {
    id: 'health-manager',
    routeId: 'health-manager',
    path: '/app/health-manager',
    children: [
      { routeId: 'health-manager.patients' },
      { routeId: 'health-manager.health-records' },
      { routeId: 'health-manager.health-data-timeline' },
      { routeId: 'health-manager.thresholds' },
      { routeId: 'health-manager.follow-ups' },
      { routeId: 'health-manager.form-fill' },
      { routeId: 'health-manager.clinical' },
      { routeId: 'health-manager.icf' },
      { routeId: 'health-manager.devices' },
      { routeId: 'quality-control' },
      { routeId: 'health-manager.monitoring' },
      { routeId: 'health-manager.communications' },
      { routeId: 'health-manager.statistics' },
      { routeId: 'health-manager.documents' },
    ],
  },
];

// ---------------------------------------------------------------------------
// 派生工具（路由表与菜单的唯一派生入口）
// ---------------------------------------------------------------------------

export function flattenRoutes(nodes: AppRouteNode[] = APP_ROUTES): AppRouteNode[] {
  const flat: AppRouteNode[] = [];
  for (const node of nodes) {
    flat.push(node);
    if (node.children) flat.push(...flattenRoutes(node.children));
  }
  return flat;
}

/** 路由 id → 相对 /app 的路径（index 路由取父路径） */
export function resolveRoutePaths(
  nodes: AppRouteNode[] = APP_ROUTES,
  parent = '',
): Record<string, string> {
  const paths: Record<string, string> = {};
  for (const node of nodes) {
    const absolute = node.index
      ? parent
      : (parent ? `${parent}/${node.path ?? ''}` : (node.path ?? ''));
    paths[node.id] = absolute;
    if (node.children) Object.assign(paths, resolveRoutePaths(node.children, absolute));
  }
  return paths;
}

export const APP_ROUTE_PATHS: Record<string, string> = resolveRoutePaths();
export const APP_ROUTE_IDS: string[] = flattenRoutes().map(node => node.id);

/** 路由节点的菜单元数据（按 id 查找） */
export function routeMenuMeta(id: string): RouteMenuMeta | undefined {
  return flattenRoutes().find(node => node.id === id)?.menu;
}

/** 路由节点的菜单可见角色（menu.roles 缺省继承路由守卫 allowedRoles） */
export function routeVisibleRoles(id: string): string[] | undefined {
  const node = flattenRoutes().find(item => item.id === id);
  if (!node) return undefined;
  return node.menu?.roles ?? node.allowedRoles;
}

export interface ResolvedNavItem {
  name: string;
  path: string;
  icon: MenuIconKey;
  roles?: string[];
  chip?: MenuChip;
  children?: ResolvedNavItem[];
}

/** 把 NAV_* 声明展开成菜单项（名称/图标/角色都从路由表派生）。 */
export function resolveNavEntry(entry: NavEntry): ResolvedNavItem {
  const meta = entry.routeId ? routeMenuMeta(entry.routeId) : undefined;
  const icon = entry.icon ?? meta?.icon;
  const name = entry.name ?? meta?.name;
  if (!icon || !name) {
    throw new Error(`菜单项缺少名称或图标：${entry.routeId ?? entry.id ?? ''}`);
  }
  return {
    name,
    path: entry.path ?? (entry.routeId ? menuPathFor(entry.routeId) : ''),
    icon,
    roles: entry.roles ?? (entry.routeId ? routeVisibleRoles(entry.routeId) : undefined),
    chip: entry.chip ?? meta?.chip,
    children: entry.children?.map(resolveNavEntry),
  };
}

function collectNavRouteIds(entries: NavEntry[], into: Set<string>) {
  for (const entry of entries) {
    if (entry.routeId) into.add(entry.routeId);
    if (entry.children) collectNavRouteIds(entry.children, into);
  }
}

/**
 * 菜单与路由表的一致性缺口。空数组表示：
 * 菜单引用的 routeId 都在路由表里；带菜单的路由都进了 NAV_*（或显式 hidden）。
 */
export function navigationGaps(): string[] {
  const gaps: string[] = [];
  const byId = new Map(flattenRoutes().map(node => [node.id, node]));
  const referenced = new Set<string>();
  collectNavRouteIds(NAV_BASE, referenced);
  collectNavRouteIds(NAV_SECTIONS, referenced);
  for (const id of referenced) {
    if (!byId.has(id)) gaps.push(`菜单引用了不存在的路由 ${id}`);
  }
  for (const node of flattenRoutes()) {
    if (node.hidden && node.menu) gaps.push(`${node.id} 同时标记了 hidden 与菜单`);
    if (!node.hidden && !node.menu) gaps.push(`${node.id} 既没有菜单也没有 hidden`);
    if (node.menu && !node.hidden && !referenced.has(node.id)) {
      gaps.push(`${node.id} 有菜单但没有出现在 NAV_BASE / NAV_SECTIONS`);
    }
  }
  return gaps;
}

/** 菜单路径：路由绝对路径去掉参数段（菜单只到功能页，不带详情参数） */
export function menuPathFor(id: string): string {
  const path = APP_ROUTE_PATHS[id] ?? '';
  const segments = path.split('/').filter(segment => segment && !segment.includes(':'));
  return segments.length ? `/app/${segments.join('/')}` : '/app';
}
