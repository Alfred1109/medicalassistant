# 前端类型边界

本目录保存应用的业务类型。React、React Router、Redux Toolkit、React Redux、Material UI、Axios、Formik、Yup、Recharts、Vite 等依赖使用安装包自身的类型；`react-beautiful-dnd` 使用已声明的 `@types/react-beautiful-dnd`。

不要使用全局 `declare module` 重新声明第三方完整模块或用 `any` 列举它的导出。这会覆盖真实类型，掩盖错误的组件属性、接口调用和业务状态结构。

确需扩展第三方类型时，先导入被扩展模块，再只声明应用新增的接口字段。现有主题扩展位于 `src/theme.ts`；Vite 环境类型入口位于 `src/env.d.ts`。不要重复定义这些扩展。

依赖未安装、导出不存在或业务契约不一致时，应修复实际依赖和调用；不应添加伪类型声明、关闭严格检查或排除业务页面来通过构建。
