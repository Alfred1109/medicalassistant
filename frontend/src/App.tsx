import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from './store';
import { checkAuthStatus } from './store/slices/authSlice';
import { closeSnackbar } from './store/slices/uiSlice';
import { Snackbar, Alert, Box, Button } from '@mui/material';
import AppRoutes, { LoadingFallback } from './routes';

const App: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { checking, token, mode, error } = useSelector((state: RootState) => state.auth);
  const { snackbar } = useSelector((state: RootState) => state.ui);

  React.useEffect(() => {
    dispatch(checkAuthStatus());
  }, [dispatch, token]);

  if (checking) return <LoadingFallback />;
  if (!mode) {
    return <Box sx={{ p: 3 }}><Alert severity="error">{error || '登录配置加载失败'}</Alert>
      <Button onClick={() => dispatch(checkAuthStatus())}>重新连接</Button></Box>;
  }

  return (
    <>
      <AppRoutes />
      <Snackbar
        open={snackbar.open}
        autoHideDuration={snackbar.duration || 6000}
        onClose={() => dispatch(closeSnackbar())}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => dispatch(closeSnackbar())}
          severity={snackbar.severity || 'info'}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </>
  );
};

export default App;
