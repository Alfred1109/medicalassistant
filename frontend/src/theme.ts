import { createTheme } from '@mui/material/styles';
import { Theme, PaletteOptions } from '@mui/material/styles';

// 声明模块扩展MUI的主题类型
declare module '@mui/material/styles' {
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

// 主题配色方案
// 创建医疗主题配色
const createMedicalTheme = () => {
  return createTheme({
    palette: {
      primary: {
        main: '#2563EB', // 医疗蓝色
        light: '#60A5FA',
        dark: '#1E40AF',
        contrastText: '#FFFFFF',
      },
      secondary: {
        main: '#10B981', // 治愈绿色
        light: '#34D399',
        dark: '#059669',
        contrastText: '#FFFFFF',
      },
      error: {
        main: '#EF4444',
        light: '#F87171',
        dark: '#B91C1C',
        contrastText: '#FFFFFF',
      },
      warning: {
        main: '#F59E0B',
        light: '#FBBF24',
        dark: '#D97706',
        contrastText: '#FFFFFF',
      },
      info: {
        main: '#3B82F6',
        light: '#60A5FA',
        dark: '#2563EB',
        contrastText: '#FFFFFF',
      },
      success: {
        main: '#10B981',
        light: '#34D399',
        dark: '#059669',
        contrastText: '#FFFFFF',
      },
      neutral: {
        main: '#6B7280',
        light: '#9CA3AF',
        dark: '#4B5563',
        contrastText: '#FFFFFF',
      },
      medical: {
        main: '#8B5CF6', // 医疗紫色
        light: '#A78BFA',
        dark: '#7C3AED',
        contrastText: '#FFFFFF',
      },
      background: {
        default: '#F9FAFB',
        paper: '#FFFFFF',
      },
      text: {
        primary: '#111827',
        secondary: '#6B7280',
        disabled: '#9CA3AF',
      },
    },
    typography: {
      fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
      h1: {
        fontSize: '2.5rem',
        fontWeight: 700,
        lineHeight: 1.2,
      },
      h2: {
        fontSize: '2rem',
        fontWeight: 700,
        lineHeight: 1.2,
      },
      h3: {
        fontSize: '1.75rem',
        fontWeight: 600,
        lineHeight: 1.2,
      },
      h4: {
        fontSize: '1.5rem',
        fontWeight: 600,
        lineHeight: 1.2,
      },
      h5: {
        fontSize: '1.25rem',
        fontWeight: 600,
        lineHeight: 1.2,
      },
      h6: {
        fontSize: '1rem',
        fontWeight: 600,
        lineHeight: 1.2,
      },
      subtitle1: {
        fontSize: '1rem',
        fontWeight: 500,
      },
      subtitle2: {
        fontSize: '0.875rem',
        fontWeight: 500,
      },
      body1: {
        fontSize: '1rem',
        lineHeight: 1.5,
      },
      body2: {
        fontSize: '0.875rem',
        lineHeight: 1.5,
      },
      button: {
        fontWeight: 600,
        fontSize: '0.875rem',
        textTransform: 'none',
      },
    },
    shape: {
      borderRadius: 10,
    },
    status: {
      danger: '#FF1943',
    },
    customShadows: {
      card: '0px 2px 8px rgba(0, 0, 0, 0.08)',
      dialog: '0px 8px 24px rgba(0, 0, 0, 0.12)',
      buttonHover: '0px 4px 8px rgba(37, 99, 235, 0.3)',
    },
    components: {
      MuiButton: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            borderRadius: 8,
            boxShadow: 'none',
            fontWeight: 600,
            ':hover': {
              boxShadow: '0px 4px 8px rgba(0, 0, 0, 0.1)',
            },
          },
          contained: {
            ':hover': {
              boxShadow: '0px 4px 8px rgba(0, 0, 0, 0.2)',
            },
          },
          containedPrimary: {
            ':hover': {
              boxShadow: '0px 4px 8px rgba(37, 99, 235, 0.3)',
            },
          },
          containedSecondary: {
            ':hover': {
              boxShadow: '0px 4px 8px rgba(16, 185, 129, 0.3)',
            },
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 12,
            boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.08)',
            border: '1px solid rgba(0, 0, 0, 0.05)',
            transition: 'transform 0.3s, box-shadow 0.3s',
            ':hover': {
              boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.12)',
              transform: 'translateY(-2px)',
            },
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 12,
          },
          elevation1: {
            boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.08)',
          },
          elevation2: {
            boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.12)',
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            padding: '12px 16px',
            borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
          },
          head: {
            backgroundColor: '#F9FAFB',
            fontWeight: 600,
            color: '#111827',
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            borderRadius: 8,
          },
          filled: {
            '&.MuiChip-colorDefault': {
              backgroundColor: '#F3F4F6',
            },
            '&.MuiChip-colorPrimary': {
              backgroundColor: '#DBEAFE',
              color: '#1E40AF',
            },
            '&.MuiChip-colorSecondary': {
              backgroundColor: '#D1FAE5',
              color: '#065F46',
            },
            '&.MuiChip-colorInfo': {
              backgroundColor: '#DBEAFE',
              color: '#1E40AF',
            },
            '&.MuiChip-colorSuccess': {
              backgroundColor: '#D1FAE5',
              color: '#065F46',
            },
            '&.MuiChip-colorWarning': {
              backgroundColor: '#FEF3C7',
              color: '#92400E',
            },
            '&.MuiChip-colorError': {
              backgroundColor: '#FEE2E2',
              color: '#B91C1C',
            },
          },
        },
      },
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            margin: 0,
            padding: 0,
            scrollBehavior: 'smooth',
            '&::-webkit-scrollbar': {
              width: '8px',
              height: '8px',
            },
            '&::-webkit-scrollbar-track': {
              background: '#F1F1F1',
            },
            '&::-webkit-scrollbar-thumb': {
              background: '#C1C1C1',
              borderRadius: '4px',
            },
            '&::-webkit-scrollbar-thumb:hover': {
              background: '#A8A8A8',
            },
          },
        },
      },
      MuiToolbar: {
        styleOverrides: {
          root: {
            borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
          },
        },
      },
      MuiTextField: {
        styleOverrides: {
          root: {
            '& .MuiOutlinedInput-root': {
              borderRadius: 8,
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: '#2563EB',
              },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                borderColor: '#2563EB',
                borderWidth: '1.5px',
              },
            },
          },
        },
      },
      MuiDialogTitle: {
        styleOverrides: {
          root: {
            fontSize: '1.25rem',
            fontWeight: 600,
          },
        },
      },
      MuiUseMediaQuery: {
        defaultProps: {
          noSsr: true,
        },
      },
    },
    transitions: {
      easing: {
        easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
        easeOut: 'cubic-bezier(0.0, 0, 0.2, 1)',
        easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
        sharp: 'cubic-bezier(0.4, 0, 0.6, 1)',
      },
      duration: {
        shortest: 150,
        shorter: 200,
        short: 250,
        standard: 300,
        complex: 375,
        enteringScreen: 225,
        leavingScreen: 195,
      },
    },
  });
};

const theme = createMedicalTheme();

export default theme; 