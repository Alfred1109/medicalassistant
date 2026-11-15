// 菜单与路由表必须来自同一份声明（config/appRoutes.ts）。
// 运行：node --experimental-strip-types frontend/tests/navigation-routes.test.mjs
import { NAV_BASE, NAV_SECTIONS, navigationGaps, resolveNavEntry } from '../src/config/appRoutes.ts';

const gaps = navigationGaps();
if (gaps.length) {
  console.error(gaps.join('\n'));
  process.exit(1);
}

const paths = [
  ...NAV_BASE.flatMap(entry => {
    const item = resolveNavEntry(entry);
    return [item.path, ...(item.children ?? []).map(child => child.path)];
  }),
  ...NAV_SECTIONS.flatMap(entry => {
    const item = resolveNavEntry(entry);
    return [item.path, ...(item.children ?? []).map(child => child.path)];
  }),
];

const required = [
  '/app/dashboard',
  '/app/rehab-plans',
  '/app/agents',
  '/app/doctor/patients',
  '/app/doctor/statistics',
  '/app/health-manager/statistics',
  '/app/health-manager/health-data-timeline',
  '/app/patient/main-dashboard',
  '/app/admin/account-bindings',
  '/app/quality-control',
];
const missing = required.filter(path => !paths.includes(path));
if (missing.length) {
  console.error('菜单缺少路径：\n' + missing.join('\n'));
  process.exit(1);
}
console.log('navigation routes consistent');
