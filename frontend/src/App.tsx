import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from './store';
import { checkAuthStatus } from './store/slices/authSlice';
import { closeSnackbar } from './store/slices/uiSlice';
import { Snackbar, Alert } from '@mui/material';
import AppRoutes, { LoadingFallback } from './routes';

const App: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { checking, token } = useSelector((state: RootState) => state.auth);
  const [validatedToken, setValidatedToken] = React.useState<string | null | undefined>(undefined);
  const { snackbar } = useSelector((state: RootState) => state.ui);

  React.useEffect(() => {
    let active = true;

    if (!token) {
      setValidatedToken(null);
      return;
    }

    dispatch(checkAuthStatus()).finally(() => {
      if (active) setValidatedToken(token);
    });

    return () => {
      active = false;
    };
  }, [dispatch, token]);

  if (validatedToken !== token || (token && checking)) {
    return <LoadingFallback />;
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
