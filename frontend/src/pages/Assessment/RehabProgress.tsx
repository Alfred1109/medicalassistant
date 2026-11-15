import { Alert, Box, Button, Paper, Typography } from '@mui/material';
import { Link } from 'react-router-dom';

export default function RehabProgress() {
  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>康复执行反馈</Typography>
      <Paper sx={{ p: 3 }}>
        <Alert severity="info" action={<Button component={Link} to="/app/rehab-plans">查看已发布方案</Button>}>
          训练完成情况只记录患者本人自述。旧计划进度不再用于计算完成率或训练次数。
        </Alert>
      </Paper>
    </Box>
  );
}
