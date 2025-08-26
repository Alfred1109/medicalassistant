/**
 * React Router 类型声明
 */
declare module 'react-router-dom' {
  import { ComponentType, ReactNode } from 'react';
  
  export interface RouteProps {
    path?: string;
    index?: boolean;
    children?: ReactNode;
    element?: ReactNode;
    caseSensitive?: boolean;
  }
  
  export const BrowserRouter: ComponentType<any>;
  export const Routes: ComponentType<any>;
  export const Route: ComponentType<RouteProps>;
  export const Navigate: ComponentType<any>;
  export const Outlet: ComponentType<any>;
  export const Link: ComponentType<any>;
  export const NavLink: ComponentType<any>;
  export const useNavigate: () => any;
  export const useLocation: () => any;
  export const useParams: () => any;
} 