import { Alert, Box, Button, Paper, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { RootState } from '../../store';
import { PatientPlanList } from '../RehabPlan/PatientPlans';
import ClinicianPlanWorkbench from '../RehabPlan/ClinicianPlanWorkbench';

export default function RehabProgress() {
  const role = useSelector((state: RootState) => state.auth.user?.role);
  if (role === 'patient') return <PatientPlanList progress />;
  if (role === 'doctor' || role === 'health_manager') return <ClinicianPlanWorkbench progress />;
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>康复执行反馈</Typography>
      <Paper sx={{ p: 3 }}>
        <Alert severity="info" action={<Button component={Link} to="/app/rehab-plans">查看康复方案</Button>}>
          训练反馈和验收记录由授权医护和患者本人查看。
        </Alert>
      </Paper>
    </Box>
  );
}
