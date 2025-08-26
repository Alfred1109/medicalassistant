import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface SnackbarMessage {
  message: string;
  severity?: 'success' | 'info' | 'warning' | 'error';
  duration?: number;
  open: boolean;
}

export interface ModalState {
  open: boolean;
  content: React.ReactNode | null;
  title: string;
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

export interface UIState {
  snackbar: SnackbarMessage;
  modal: ModalState;
  sidebarOpen: boolean;
  darkMode: boolean;
}

const initialState: UIState = {
  snackbar: {
    message: '',
    severity: 'info',
    duration: 6000,
    open: false,
  },
  modal: {
    open: false,
    content: null,
    title: '',
    maxWidth: 'sm',
  },
  sidebarOpen: true,
  darkMode: false,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    showSnackbar: (state, action: PayloadAction<Omit<SnackbarMessage, 'open'>>) => {
      state.snackbar = {
        ...state.snackbar,
        ...action.payload,
        open: true,
      };
    },
    closeSnackbar: (state) => {
      state.snackbar.open = false;
    },
    openModal: (state, action: PayloadAction<Omit<ModalState, 'open'>>) => {
      state.modal = {
        ...action.payload,
        open: true,
      };
    },
    closeModal: (state) => {
      state.modal.open = false;
    },
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen;
    },
    toggleDarkMode: (state) => {
      state.darkMode = !state.darkMode;
    },
  },
});

export const {
  showSnackbar,
  closeSnackbar,
  openModal,
  closeModal,
  toggleSidebar,
  toggleDarkMode,
} = uiSlice.actions;

export default uiSlice.reducer; 