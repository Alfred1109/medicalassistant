import React from 'react';
import { Alert, Box, Button, Card, CardContent, Grid, Paper, Stack, Typography } from '@mui/material';
import { Link } from 'react-router-dom';
import { rehabPublications, PublishedRehabPage } from '../../services/rehabPublications';

const Statistics: React.FC = () => {
  const [planPage, setPlanPage] = React.useState<PublishedRehabPage | null>(null);
  const [page, setPage] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  const loadPlans = React.useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await rehabPublications.myPlans(page * 20, 20);
      if (!Array.isArray(data.items) || !Number.isSafeInteger(data.total) || data.skip !== page * 20
          || !data.status_counts || !Number.isSafeInteger(data.status_counts.active)
          || !Number.isSafeInteger(data.status_counts.completed)) throw new Error('康复方案统计格式异常');
      setPlanPage(data);
    } catch (failure: any) {
      setPlanPage(null);
      setError(failure?.response?.data?.detail || '康复方案暂时无法加载，请重试。');
    } finally {
      setLoading(false);
    }
  }, [page]);

  React.useEffect(() => { void loadPlans(); }, [loadPlans]);

  return <Box>
    <Typography variant="h5" component="h1" gutterBottom>我的康复数据</Typography>
    <Alert severity="info" sx={{ mb: 3 }}>
      方案和患者执行自述来自当前已发布方案及反馈记录。系统尚未定义训练场次与完成率口径，因此不显示推算的完成率或训练时长。
    </Alert>
    {error && <Alert severity="error" sx={{ mb: 3 }} action={<Button onClick={() => void loadPlans()}>重试</Button>}>{error}</Alert>}
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card><CardContent>
          <Typography variant="h6">已发布康复方案</Typography>
          <Typography variant="h3" color="primary" sx={{ my: 1 }}>{loading ? '…' : error ? '—' : planPage?.total}</Typography>
          <Typography color="text.secondary">仅统计医护发布且当前对本人可见的方案；进行中 {planPage?.status_counts.active ?? '—'}，已完成 {planPage?.status_counts.completed ?? '—'}。</Typography>
          <Button component={Link} to="/app/rehab-plans" sx={{ mt: 1 }}>查看方案和执行反馈</Button>
        </CardContent></Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card><CardContent>
          <Typography variant="h6">训练完成率与时长</Typography>
          <Typography variant="h4" color="text.disabled" sx={{ my: 1 }}>暂不可计算</Typography>
          <Typography color="text.secondary">患者自述记录描述单次感受；目前没有经确认的训练场次归并和统计规则。</Typography>
        </CardContent></Card>
      </Grid>
      <Grid item xs={12}>
        <Paper sx={{ p: 3 }}>
          <Stack spacing={2}>
            <Typography variant="h6">最近发布的方案</Typography>
            {loading ? <Typography color="text.secondary">加载中…</Typography>
              : error ? <Alert severity="error">方案统计加载失败，无法确认方案数量或状态。</Alert>
              : !planPage?.items.length ? <Alert severity="info">暂无医护发布的康复方案。</Alert>
              : planPage.items.map(plan => <Box key={plan.id}>
                <Typography variant="subtitle1">{plan.content.name || '康复方案'}</Typography>
                <Typography variant="body2" color="text.secondary">{plan.content.goal || '未填写目标'}</Typography>
                <Button component={Link} to={`/app/rehab-plans/${plan.id}`}>查看方案与我的执行反馈</Button>
              </Box>)}
            {planPage && planPage.total > (page + 1) * planPage.limit && <Button disabled={loading} onClick={() => setPage(value => value + 1)} sx={{ alignSelf: 'flex-start' }}>下一页</Button>}
            {page > 0 && <Button disabled={loading} onClick={() => setPage(value => value - 1)} sx={{ alignSelf: 'flex-start' }}>上一页</Button>}
          </Stack>
        </Paper>
      </Grid>
    </Grid>
  </Box>;
};

export default Statistics;
