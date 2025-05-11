/**
 * 性能优化工具库
 * 提供组件记忆化、预加载和性能监控功能
 */
import React, { useEffect, useRef } from 'react';

/**
 * 预加载组件配置接口
 */
interface PreloadConfig {
  preloadOnHover?: boolean;
  preloadOnVisible?: boolean;
  delay?: number;
}

/**
 * 组件预加载状态记录
 */
const preloadedComponents = new Set<string>();

/**
 * 创建可预加载的组件
 * @param importFn 组件导入函数
 * @param componentName 组件名称（用于跟踪）
 * @param config 预加载配置
 */
export const createPreloadableComponent = <T extends React.ComponentType<any>>(
  importFn: () => Promise<{ default: T }>,
  componentName: string,
  config: PreloadConfig = {}
) => {
  // 创建懒加载组件
  const LazyComponent = React.lazy(importFn);
  
  // 预加载函数
  const preload = () => {
    if (preloadedComponents.has(componentName)) return;
    
    setTimeout(() => {
      importFn().then(() => {
        preloadedComponents.add(componentName);
        console.log(`Component ${componentName} preloaded`);
      });
    }, config.delay || 0);
  };
  
  // 增强组件，添加预加载功能
  const EnhancedComponent: React.FC<React.ComponentProps<T> & { triggerRef?: React.RefObject<HTMLElement> }> = (props) => {
    const { triggerRef, ...restProps } = props;
    
    useEffect(() => {
      if (!config.preloadOnVisible || !triggerRef?.current) return;
      
      // 使用IntersectionObserver在组件可见时预加载
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            preload();
            observer.disconnect();
          }
        });
      });
      
      observer.observe(triggerRef.current);
      return () => observer.disconnect();
    }, [triggerRef]);
    
    // 使用React.createElement替代JSX语法，避免TypeScript错误
    return React.createElement(LazyComponent, restProps as any);
  };
  
  // 为组件添加预加载方法
  (EnhancedComponent as any).preload = preload;
  
  return EnhancedComponent;
};

/**
 * 智能记忆化组件，根据组件复杂度自动决定是否使用React.memo
 * @param Component 要记忆化的组件
 * @param propsAreEqual 自定义对比函数
 */
export function smartMemo<T extends React.ComponentType<any>>(
  Component: T,
  propsAreEqual?: (prevProps: Readonly<React.ComponentProps<T>>, nextProps: Readonly<React.ComponentProps<T>>) => boolean
): T {
  // 使用displayName判断是否是重型组件
  const isHeavyComponent = Component.displayName?.includes('Chart') || 
                           Component.displayName?.includes('Table') ||
                           Component.displayName?.includes('Grid') ||
                           Component.displayName?.includes('Form');
  
  // 重型组件或明确指定propsAreEqual时使用React.memo
  if (isHeavyComponent || propsAreEqual) {
    return React.memo(Component, propsAreEqual) as unknown as T;
  }
  
  return Component;
}

/**
 * 性能监控Hook
 * 用于跟踪组件渲染性能
 * @param componentName 组件名称
 */
export function useRenderPerformance(componentName: string) {
  const renderCount = useRef(0);
  const lastRenderTime = useRef(performance.now());
  
  useEffect(() => {
    renderCount.current += 1;
    const now = performance.now();
    const renderTime = now - lastRenderTime.current;
    
    // 只记录渲染时间超过16ms (60fps) 的组件
    if (renderTime > 16) {
      console.warn(
        `Performance issue: ${componentName} took ${renderTime.toFixed(2)}ms to render ` +
        `(render count: ${renderCount.current})`
      );
    }
    
    lastRenderTime.current = now;
  });
}

/**
 * 预加载链接目标页面
 * @param path 路径
 */
export function preloadRouteComponent(path: string) {
  // 获取路由配置
  const routes = (window as any).__ROUTES_CONFIG__;
  if (!routes) return;
  
  // 查找匹配的路由
  const route = routes.find((r: any) => r.path === path);
  if (route && route.component && typeof route.component.preload === 'function') {
    route.component.preload();
  }
}

/**
 * 菜单项悬停预加载指令
 * @param event 鼠标事件
 * @param path 路径
 */
export function handleMenuHover(event: React.MouseEvent, path: string) {
  preloadRouteComponent(path);
}

/**
 * 防止组件短时间内频繁重渲染
 * @param Component 组件
 * @param debounceTime 防抖时间(ms)
 */
export function withRenderDebounce<T extends React.ComponentType<any>>(
  Component: T,
  debounceTime: number = 50
): T {
  const DebounceComponent: React.FC<React.ComponentProps<T>> = (props) => {
    const [debouncedProps, setDebouncedProps] = React.useState(props);
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    useEffect(() => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      
      timeoutRef.current = setTimeout(() => {
        setDebouncedProps(props);
        timeoutRef.current = null;
      }, debounceTime);
      
      return () => {
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }
      };
    }, [props, debounceTime]);
    
    // 使用React.createElement替代JSX语法，避免TypeScript错误
    return React.createElement(Component, debouncedProps as any);
  };
  
  DebounceComponent.displayName = `Debounced(${Component.displayName || Component.name || 'Component'})`;
  
  return DebounceComponent as unknown as T;
} 