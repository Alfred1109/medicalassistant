/**
 * Material UI 和 React 组件的类型声明
 */
declare module '@mui/material/styles' {
  export const styled: any;
  export const useTheme: any;
  export type Theme = any;
  export const alpha: any;
  
  interface Theme {
    status: {
      danger: string;
    };
    customShadows: {
      card: string;
      dialog: string;
      buttonHover: string;
    };
  }

  interface ThemeOptions {
    status?: {
      danger?: string;
    };
    customShadows?: {
      card?: string;
      dialog?: string;
      buttonHover?: string;
    };
  }

  interface Palette {
    neutral: {
      main: string;
      light: string;
      dark: string;
      contrastText: string;
    };
    medical: {
      main: string;
      light: string;
      dark: string;
      contrastText: string;
    };
  }

  interface PaletteOptions {
    neutral?: {
      main?: string;
      light?: string;
      dark?: string;
      contrastText?: string;
    };
    medical?: {
      main?: string;
      light?: string;
      dark?: string;
      contrastText?: string;
    };
  }
}

declare module '@mui/material' {
  export const Box: any;
  export const Drawer: any;
  export const AppBar: any;
  export const Toolbar: any;
  export const Typography: any;
  export const Divider: any;
  export const IconButton: any;
  export const List: any;
  export const ListItem: any;
  export const ListItemButton: any;
  export const ListItemIcon: any;
  export const ListItemText: any;
  export const CssBaseline: any;
  export const useMediaQuery: any;
  export const Avatar: any;
  export const Badge: any;
  export const Menu: any;
  export const MenuItem: any;
  export const InputBase: any;
  export const Chip: any;
  export const Tooltip: any;
  export const Breadcrumbs: any;
  export const Link: any;
  export const Paper: any;
  export const Card: any;
  export const CardContent: any;
  export const Grid: any;
  export const CircularProgress: any;
  export const Button: any;
  export const CardHeader: any;
  export const Dialog: any;
  export const DialogTitle: any;
  export const DialogContent: any;
  export const DialogContentText: any;
  export const DialogActions: any;
  export const TextField: any;
  export const Step: any;
  export const StepLabel: any;
  export const StepContent: any;
  export const Stepper: any;
  export const ListItemSecondaryAction: any;
  export const ToggleButton: any;
  export const ToggleButtonGroup: any;
  export const AlertTitle: any;
  export const ButtonGroup: any;
  export const Alert: any;
}

declare module '@mui/icons-material' {
  export const Menu: any;
  export const ChevronLeft: any;
  export const ChevronRight: any;
  export const Search: any;
  export const Notifications: any;
  export const Settings: any;
  export const Dashboard: any;
  export const People: any;
  export const LocalHospital: any;
  export const CalendarMonth: any;
  export const Healing: any;
  export const Psychology: any;
  export const AccountCircle: any;
  export const Language: any;
  export const Logout: any;
  export const ViewQuilt: any;
  export const Warning: any;
  export const NavigateNext: any;
  export const MoreVert: any;
  export const TrendingUp: any;
  export const Schedule: any;
  export const Done: any;
  export const Assignment: any;
  export const Event: any;
  export const ArrowUpward: any;
  export const ArrowDownward: any;
  export const Refresh: any;
  export const Favorite: any;
  export const BluetoothSearching: any;
  export const Check: any;
  export const Close: any;
  export const DevicesOther: any;
  export const SyncProblem: any;
  export const WifiTethering: any;
  export const Help: any;
  export const Sync: any;
  export const Watch: any;
  export const BloodtypeOutlined: any;
  export const MonitorHeart: any;
  export const DeviceHub: any;
  export const Error: any;
  export const ShowChart: any;
  export const InsertChart: any;
  export const BatteryAlert: any;
  export const SignalCellularAlt: any;
  export const SignalCellularConnectedNoInternet0Bar: any;
  export const Tune: any;
}

declare module 'react' {
  export const useState: any;
  export const useEffect: any;
  export const useCallback: any;
  export const useMemo: any;
  export const useRef: any;
  export type FC<P = {}> = React.FunctionComponent<P>;
}

declare module 'notistack' {
  export const useSnackbar: any;
}

declare module 'react-beautiful-dnd' {
  export const DragDropContext: any;
  export const Droppable: any;
  export const Draggable: any;
}

declare module 'recharts' {
  export const LineChart: any;
  export const Line: any;
  export const XAxis: any;
  export const YAxis: any;
  export const CartesianGrid: any;
  export const Tooltip: any;
  export const Legend: any;
  export const BarChart: any;
  export const Bar: any;
  export const AreaChart: any;
  export const Area: any;
  export const PieChart: any;
  export const Pie: any;
  export const Cell: any;
  export const ResponsiveContainer: any;
} 