/**
 * 样式引擎代理
 * 
 * 这个文件解决了 @mui/styled-engine 与 @mui/system 之间的兼容性问题
 * 提供了系统所需但在当前版本中缺失的 internal_serializeStyles 和 internal_mutateStyles 接口
 */

import styledOriginal from '@emotion/styled';
import { serializeStyles } from '@emotion/serialize';

// 导出原始的 styled 函数
const styled = styledOriginal;

// 实现 internal_serializeStyles 接口
export const internal_serializeStyles = (...args) => {
  return serializeStyles(args);
};

// 实现 internal_mutateStyles 接口
export const internal_mutateStyles = (style, newStyle) => {
  return { ...style, ...newStyle };
};

// 默认导出保持不变
export default styled; 