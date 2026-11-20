import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Card, CardContent, Chip, CircularProgress, Container, Stack, Typography } from '@mui/material';
import { useSelector } from 'react-redux';
import { Link, useParams } from 'react-router-dom';
import { API_BASE_URL } from '../../config/api';
import { useAsyncResource } from '../../hooks/useAsyncResource';
import { formIntegrationService, type PatientSelfTask } from '../../services/formIntegrationService';
import { apiErrorMessage } from '../../services/patientErrors';
import type { RootState } from '../../store';
import { formatAppDate } from '../../utils/dateTime';
import { patientQuestionnairePath, patientQuestionnaireStatus, patientQuestionnaireTitle, patientSelfBridgeUrl,
  validQuestionnaireTaskId } from '../../utils/patientSelfQuestionnaire';

const PAGE_SIZE = 20;

function TaskInfo({ task }: { task: PatientSelfTask }) {
  return <Stack spacing={1}>
    <Typography variant="h6">{patientQuestionnaireTitle(task)}</Typography>
    <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
      <Chip size="small" label={patientQuestionnaireStatus[task.status] || task.status} />
      {task.submittedAt && <Typography variant="body2" color="text.secondary">
        提交时间 {formatAppDate(task.submittedAt, 'minute')}
      </Typography>}
      {task.createdAt && !task.submittedAt && <Typography variant="body2" color="text.secondary">
        分配时间 {formatAppDate(task.createdAt, 'minute')}
      </Typography>}
    </Stack>
  </Stack>;
}

function QuestionnaireList() {
  const [page, setPage] = useState(0);
  const load = useCallback(async (signal: AbortSignal) => {
    const skip = page * PAGE_SIZE;
    const result = await formIntegrationService.listPatientSelfTasks(skip, PAGE_SIZE, signal);
    if (!Array.isArray(result?.items) || !Number.isSafeInteger(result.total) || result.total < 0 ||
        result.skip !== skip || result.limit !== PAGE_SIZE || result.items.length > PAGE_SIZE ||
        result.items.some(task => !validQuestionnaireTaskId(task.id) || !task.remoteRefs || typeof task.status !== 'string')) {
      throw new Error('问卷任务列表格式异常。');
    }
    return result;
  }, [page]);
  const { data, error, loading, reload } = useAsyncResource(load);
  return <Stack spacing={2}>
    {loading && <CircularProgress size={24} aria-label="正在读取问卷" />}
    {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>
      {apiErrorMessage(error, '无法读取本人问卷任务。')}
    </Alert>}
    {data && data.items.length === 0 && <Alert severity="info">{page ? '当前页暂无问卷任务。' : '医护尚未分配问卷任务。'}</Alert>}
    {data?.items.map(task => <Card key={task.id} variant="outlined"><CardContent>
      <TaskInfo task={task} />
      <Button component={Link} sx={{ mt: 1 }} to={`${patientQuestionnairePath}/${task.id}`}>查看任务</Button>
    </CardContent></Card>)}
    {(page > 0 || (data && data.total > PAGE_SIZE)) && <Stack direction="row" spacing={2} alignItems="center">
      <Button onClick={() => setPage(value => value - 1)} disabled={loading || page === 0}>上一页</Button>
      <Typography variant="body2">第 {page + 1} 页</Typography>
      <Button onClick={() => setPage(value => value + 1)} disabled={loading || !data || (page + 1) * PAGE_SIZE >= data.total}>下一页</Button>
    </Stack>}
  </Stack>;
}

function QuestionnaireDetail({ taskId }: { taskId: string }) {
  const [launching, setLaunching] = useState(false);
  const [opened, setOpened] = useState(false);
  const [launchError, setLaunchError] = useState('');
  const activeLaunch = useRef<AbortController | null>(null);
  const load = useCallback(async (signal: AbortSignal) => {
    const task = await formIntegrationService.getPatientSelfTask(taskId, signal);
    if (task?.id !== taskId || !task.remoteRefs || typeof task.status !== 'string') throw new Error('问卷响应与当前任务不匹配。');
    return task;
  }, [taskId]);
  const { data, error, loading, reload } = useAsyncResource(load);
  useEffect(() => () => activeLaunch.current?.abort(), []);
  useEffect(() => {
    if (!opened) return;
    const onVisible = () => { if (document.visibilityState === 'visible') reload(); };
    window.addEventListener('focus', reload);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('focus', reload);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [opened, reload]);

  const canLaunch = data && (data.status === 'assigned' || data.status === 'active');
  const launch = async () => {
    if (!canLaunch || activeLaunch.current) return;
    const tab = window.open('about:blank', '_blank');
    if (!tab) { setLaunchError('浏览器拦截了新标签页，请允许本站弹出窗口后重试。'); return; }
    tab.opener = null;
    const controller = new AbortController();
    activeLaunch.current = controller;
    setLaunching(true);
    setLaunchError('');
    try {
      const result = await formIntegrationService.launchPatientSelfTask(taskId, controller.signal);
      const url = patientSelfBridgeUrl(result, taskId, window.location.origin, API_BASE_URL);
      if (controller.signal.aborted || tab.closed) { tab.close(); return; }
      tab.location.replace(url.href);
      setOpened(true);
    } catch (failure) {
      tab.close();
      if (!controller.signal.aborted) setLaunchError(apiErrorMessage(failure, '暂时无法打开问卷。'));
    } finally {
      activeLaunch.current = null;
      if (!controller.signal.aborted) setLaunching(false);
    }
  };

  return <Stack spacing={2} alignItems="flex-start">
    <Button component={Link} to={patientQuestionnairePath}>返回我的问卷</Button>
    {loading && <CircularProgress size={24} aria-label="正在读取问卷任务" />}
    {!!error && <Alert severity="error" action={<Button onClick={reload}>重试</Button>}>
      {apiErrorMessage(error, '无法读取这项问卷任务。')}
    </Alert>}
    {data && <TaskInfo task={data} />}
    {launchError && <Alert severity="error">{launchError}</Alert>}
    {opened && canLaunch && <Alert severity="info">已在新标签页打开问卷。提交后返回这里查看状态。</Alert>}
    <Stack direction="row" spacing={2}>
      {canLaunch && <Button variant="contained" disabled={launching} onClick={() => void launch()}>
        {launching ? '正在打开' : data.status === 'active' ? '继续填写' : '开始填写'}
      </Button>}
      {data && <Button onClick={reload} disabled={launching}>刷新提交状态</Button>}
    </Stack>
  </Stack>;
}

export default function Questionnaires() {
  const actor = useSelector((state: RootState) => state.auth.user);
  const mode = useSelector((state: RootState) => state.auth.mode);
  const { taskId } = useParams();
  return <Container maxWidth="md"><Stack spacing={2}>
    <Typography variant="h5" component="h1">我的问卷</Typography>
    {mode !== 'oidc' ? <Alert severity="info">请使用患者本人的 OneID 登录后填写问卷。</Alert> :
      taskId ? validQuestionnaireTaskId(taskId) ? <QuestionnaireDetail key={`${actor?.id}:${taskId}`} taskId={taskId.toLowerCase()} />
        : <Alert severity="error" action={<Button component={Link} to={patientQuestionnairePath}>返回问卷</Button>}>问卷任务标识无效。</Alert>
      : <QuestionnaireList key={actor?.id} />}
  </Stack></Container>;
}
