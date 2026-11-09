import React from 'react';
import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';

export interface CatalogPageStateProps {
  loading: boolean; error: string | null; more: boolean; reload: () => unknown; next: () => unknown;
}
export default function CatalogPageState({ loading, error, more, reload, next }: CatalogPageStateProps) {
  return <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1 }}>
    {loading && <><CircularProgress size={18} /><Typography variant="body2">正在读取来源目录…</Typography></>}
    {error && <Alert severity="error" action={<Button color="inherit" onClick={() => void reload()}>重试</Button>}>{error}</Alert>}
    {more && <Button size="small" disabled={loading} onClick={() => void next()}>加载更多</Button>}
  </Box>;
}
