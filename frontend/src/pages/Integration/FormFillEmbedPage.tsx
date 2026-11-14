import React, { useEffect, useId, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { RootState } from '../../store';
import { Alert, Box, Button, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import { formIntegrationService, isTrustedFormPlatformFillStatusEvent, submitFillLaunch, EmbedUrlResult, FillTask } from '../../services/formIntegrationService';

type Phase = 'loading' | 'idle' | 'launching' | 'ready' | 'confirming' | 'confirmed' | 'error';

const FormFillEmbedPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const actorId = useSelector((state: RootState) => state.auth.user?.id);
  const authMode = useSelector((state: RootState) => state.auth.mode);
  const authToken = useSelector((state: RootState) => state.auth.token);
  const [phase, setPhase] = useState<Phase>('loading');
  const [task, setTask] = useState<FillTask | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [opened, setOpened] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const sequence = useRef(0);
  const busy = useRef(false);
  const embed = useRef<EmbedUrlResult | null>(null);
  const frameName = `form-fill-${useId()}`;

  useEffect(() => {
    const generation = ++sequence.current;
    busy.current = false;
    embed.current = null;
    setOpened(false);
    setTask(null);
    setMessage(null);
    setPhase('loading');
    if (iframeRef.current) iframeRef.current.src = 'about:blank';
    if (!taskId) {
      setMessage('缺少任务标识');
      setPhase('error');
      return;
    }
    formIntegrationService.getFillTask(taskId).then(loaded => {
      if (sequence.current !== generation) return;
      setTask(loaded);
      setPhase(loaded.status === 'confirmed' ? 'confirmed' : 'idle');
    }).catch(() => {
      if (sequence.current !== generation) return;
      setMessage('任务加载失败，请返回任务列表后重试');
      setPhase('error');
    });
    return () => { sequence.current += 1; };
  }, [taskId, actorId, authMode, authToken]);

  const confirm = async () => {
    if (!taskId || busy.current) return;
    const generation = sequence.current;
    busy.current = true;
    setPhase('confirming');
    setMessage(null);
    try {
      const result = await formIntegrationService.confirmFillTask(taskId);
      if (generation !== sequence.current) return;
      setTask(result);
      setPhase(result.status === 'confirmed' ? 'confirmed' : opened ? 'ready' : 'idle');
      if (result.status !== 'confirmed') setMessage('尚未核实到已提交答卷，可以继续填写后再确认');
    } catch {
      if (generation !== sequence.current) return;
      setMessage('提交确认失败，可以保留当前填写页面并稍后重新确认');
      setPhase(opened ? 'ready' : 'idle');
    } finally {
      if (generation === sequence.current) busy.current = false;
    }
  };

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (!embed.current || !isTrustedFormPlatformFillStatusEvent(event, iframeRef.current?.contentWindow ?? null, embed.current)) return;
      if (event.data.status === 'submitted') void confirm();
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  });

  const launch = async () => {
    if (!taskId || busy.current) return;
    const generation = sequence.current;
    busy.current = true;
    setPhase('launching');
    setMessage(null);
    try {
      const result = await formIntegrationService.launchFillTask(taskId);
      if (generation !== sequence.current) return;
      if (result.taskId !== taskId || result.sessionUuid !== task?.session.sessionUuid || result.allowedOrigin !== window.location.origin || !iframeRef.current) throw new Error('填报会话不匹配');
      embed.current = { taskId, embedUrl: result.mode === 'launch' ? result.action : result.url, sessionUuid: result.sessionUuid, expiresAt: result.expiresAt, allowedOrigin: result.allowedOrigin };
      submitFillLaunch(result, iframeRef.current);
      setOpened(true);
      setPhase('ready');
    } catch (error) {
      if (generation !== sequence.current) return;
      setMessage(error instanceof Error ? error.message : '填报入口暂不可用，请重新登录后重试');
      setPhase('idle');
    } finally {
      if (generation === sequence.current) busy.current = false;
    }
  };

  if (phase === 'confirmed') return <Paper sx={{ p: 4, maxWidth: 720, mx: 'auto', mt: 4 }}>
    <Alert severity="success">答卷已核实提交，等待医护审阅。</Alert>
    {task?.confirmation && <Typography sx={{ mt: 2 }}>答卷标识 {task.confirmation.response_id}</Typography>}
    <Button sx={{ mt: 3 }} onClick={() => navigate(-1)}>返回任务列表</Button>
  </Paper>;

  const available = task && ['session_created', 'waiting_fill'].includes(task.status);
  return <Box sx={{ p: 2 }}>
    <Stack spacing={2}>
      {message && <Alert severity="warning">{message}</Alert>}
      {(phase === 'loading' || phase === 'launching' || phase === 'confirming') && <CircularProgress size={24} />}
      {task && !available && <Alert severity="info">当前任务状态为 {task.status}，可以返回任务列表核查。</Alert>}
      <Stack direction="row" spacing={2}>
        {available && <Button variant="contained" disabled={busy.current} onClick={launch}>打开或继续填写</Button>}
        {task && <Button disabled={busy.current} onClick={confirm}>核实提交状态</Button>}
        <Button onClick={() => navigate(-1)}>返回任务列表</Button>
      </Stack>
    </Stack>
    <Box sx={{ mt: 2, display: opened ? 'block' : 'none', height: '72vh', border: '1px solid', borderColor: 'divider' }}>
      <iframe key={`${actorId}-${taskId}`} ref={iframeRef} name={frameName} title="113.44 填报表单" style={{ width: '100%', height: '100%', border: 'none' }} sandbox="allow-forms allow-scripts allow-same-origin allow-popups" />
    </Box>
  </Box>;
};
export default FormFillEmbedPage;
