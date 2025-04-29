// React
declare module 'react' {
  export default React;
  export * from 'react';
}

// React Router
declare module 'react-router-dom' {
  export function useNavigate(): (to: string) => void;
  export function useParams<T extends Record<string, string>>(): T;
  export function Navigate(props: { to: string; replace?: boolean }): JSX.Element;
  export function useLocation(): { pathname: string; search: string; hash: string; state: any };
  export function Link(props: { to: string; children: React.ReactNode; [key: string]: any }): JSX.Element;
  export function BrowserRouter(props: { children: React.ReactNode }): JSX.Element;
  export function Routes(props: { children: React.ReactNode }): JSX.Element;
  export function Route(props: { path: string; element: React.ReactNode }): JSX.Element;
  export function Outlet(): JSX.Element;
}

// React Redux
declare module 'react-redux' {
  export function useSelector<T = any, S = any>(selector: (state: S) => T): T;
  export function useDispatch<D = any>(): D;
  export function Provider(props: { store: any; children: React.ReactNode }): JSX.Element;
}

// Redux Toolkit
declare module '@reduxjs/toolkit' {
  export function createSlice(options: any): any;
  export function configureStore(options: any): any;
  export function createAsyncThunk(type: string, payloadCreator: any): any;
  export type PayloadAction<P = void> = { payload: P; type: string };
}

// Material UI
declare module '@mui/material' {
  export const Box: any;
  export const Button: any;
  export const Typography: any;
  export const TextField: any;
  export const Container: any;
  export const Grid: any;
  export const Card: any;
  export const CardContent: any;
  export const CardActions: any;
  export const Paper: any;
  export const List: any;
  export const ListItem: any;
  export const ListItemText: any;
  export const ListItemIcon: any;
  export const ListItemAvatar: any;
  export const Avatar: any;
  export const Divider: any;
  export const Chip: any;
  export const Alert: any;
  export const Stack: any;
  export const FormControl: any;
  export const InputLabel: any;
  export const Select: any;
  export const MenuItem: any;
  export const CircularProgress: any;
  export const Dialog: any;
  export const DialogTitle: any;
  export const DialogContent: any;
  export const DialogActions: any;
  export const Snackbar: any;
  export const IconButton: any;
  export const LinearProgress: any;
  export const Tab: any;
  export const Tabs: any;
  export const Tooltip: any;
  export const CssBaseline: any;
}

// Material UI Icons
declare module '@mui/icons-material' {
  export const Add: any;
  export const Edit: any;
  export const Delete: any;
  export const Save: any;
  export const Cancel: any;
  export const Person: any;
  export const Lock: any;
  export const Logout: any;
  export const Dashboard: any;
  export const FitnessCenter: any;
  export const Psychology: any;
  export const CalendarToday: any;
  export const CheckCircle: any;
  export const PendingActions: any;
  export const Launch: any;
  export const TrendingUp: any;
  export const SentimentDissatisfied: any;
  export const ArrowBack: any;
  export const Send: any;
  export const SmartToy: any;
  export const Chat: any;
  export const Settings: any;
  export const Code: any;
  export const PersonAddOutlined: any;
  export const LockOutlined: any;
  export const Visibility: any;
  export const Refresh: any;
}

// Material UI Styles
declare module '@mui/material/styles' {
  export function ThemeProvider(props: { theme: any; children: React.ReactNode }): JSX.Element;
  export function createTheme(options: any): any;
}

// Axios
declare module 'axios' {
  export interface AxiosRequestConfig {
    baseURL?: string;
    headers?: Record<string, string>;
    params?: any;
  }
  
  export interface AxiosResponse<T = any> {
    data: T;
    status: number;
    statusText: string;
    headers: Record<string, string>;
    config: AxiosRequestConfig;
  }
  
  export interface AxiosError<T = any> {
    response?: AxiosResponse<T>;
    request?: any;
    message: string;
    config: AxiosRequestConfig;
    code?: string;
  }
  
  export interface AxiosInstance {
    (config: AxiosRequestConfig): Promise<AxiosResponse>;
    (url: string, config?: AxiosRequestConfig): Promise<AxiosResponse>;
    defaults: AxiosRequestConfig;
    interceptors: {
      request: any;
      response: any;
    };
    get<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>;
    post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>;
    put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>;
    delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<AxiosResponse<T>>;
  }
  
  export function create(config?: AxiosRequestConfig): AxiosInstance;
  export default create;
}

// Formik
declare module 'formik' {
  export function Formik(props: any): JSX.Element;
  export function Form(props: any): JSX.Element;
  export function Field(props: any): JSX.Element;
  export function ErrorMessage(props: any): JSX.Element;
  export function FieldArray(props: any): JSX.Element;
  export function useFormik(props: any): any;
  export function useFormikContext(): any;
}

// Yup
declare module 'yup' {
  export function object(): any;
  export function string(): any;
  export function number(): any;
  export function boolean(): any;
  export function array(): any;
} 