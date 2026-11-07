/**
 * 嵌入填报壳页面（医护侧，首轮隔离联调）。
 *
 * 职责：
 * - 从后端取一次性 embed_url 并在 iframe 中打开；
 * - 严格校验 postMessage：origin 必须等于后端登记的 allowedOrigin，
 *   且消息满足 source/type/结构与 sessionId 匹配，才触发后端 confirm；
 * - 状态展示：过期/失败/已确认各自有明确提示；不缓存任何令牌材料。
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';

import {
  formIntegrationService,
  isFormPlatformFillStatusMessage,
  EmbedUrlResult,
  FillTask,
} from '../../services/formIntegrationService';

type PagePhase = 'loading' | 'ready' | 'confirming' | 'confirmed' | 'error';

const FormFillEmbedPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [phase, setPhase] = useState<PagePhase>('loading');
  const [embed, setEmbed] = useState<EmbedUrlResult | null>(null);
  const [task, setTask] = useState<FillTask | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadTask = useCallback(async (id: string) => {
    try {
      const loaded = await formIntegrationService.getFillTask(id);
      setTask(loaded);
      return loaded;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const boot = async () => {
      if (!taskId) {
        setErrorMessage('缺少任务标识');
        setPhase('error');
        return;
      }
      try {
        const [embedUrl, loadedTask] = await Promise.all([
          formIntegrationService.getEmbedUrl(taskId),
          loadTask(taskId),
        ]);
        if (cancelled) return;
        setEmbed(embedUrl);
        if (loadedTask && loadedTask.status === 'confirmed') {
          setPhase('confirmed');
        } else {
          setPhase('ready');
        }
      } catch (error) {
        if (cancelled) return;
        setErrorMessage(
          error instanceof Error && error.message
            ? error.message
            : '无法获取嵌入链接：任务可能已过期或被取消，请重新创建填报任务',
        );
        setPhase('error');
      }
    };
    void boot();
    return () => {
      cancelled = true;
    };
  }, [taskId, loadTask]);

  useEffect(() => {
    if (!taskId || !embed) return;

    // event.origin 是消息发送方（表单平台 iframe）的来源，
    // 必须等于 embed_url 的来源；allowedOrigin 是本页面自身来源（postMessage 的目标），二者不能混用。
    const formPlatformOrigin = (() => {
      try {
        return new URL(embed.embedUrl).origin;
      } catch {
        return '';
      }
    })();

    const handler = (event: MessageEvent) => {
      // 严格校验 origin：必须与表单平台来源完全一致
      if (!formPlatformOrigin || event.origin !== formPlatformOrigin) return;
      if (!isFormPlatformFillStatusMessage(event.data)) return;
      if (embed.sessionUuid && event.data.sessionSid !== embed.sessionUuid) return;
      if (event.data.status !== 'submitted') return;

      setPhase('confirming');
      formIntegrationService
        .confirmFillTask(taskId)
        .then((confirmed) => {
          setTask(confirmed);
          if (confirmed.status === 'confirmed') {
            setPhase('confirmed');
          } else {
            setErrorMessage('远端尚未确认提交，请稍后重试或联系管理员核查');
            setPhase('error');
          }
        })
        .catch(() => {
          setErrorMessage('提交确认失败：远端状态核验未通过，请重新确认或联系管理员');
          setPhase('error');
        });
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [taskId, embed]);

  const handleManualConfirm = async () => {
    if (!taskId) return;
    setPhase('confirming');
    try {
      const confirmed = await formIntegrationService.confirmFillTask(taskId);
      setTask(confirmed);
      if (confirmed.status === 'confirmed') {
        setPhase('confirmed');
      } else {
        setErrorMessage('远端尚未确认提交：请等待患者/操作者完成填写后再确认');
        setPhase('error');
      }
    } catch {
      setErrorMessage('确认失败：远端状态核验未通过，请稍后重试');
      setPhase('error');
    }
  };

  if (phase === 'loading' || phase === 'confirming') {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight={400}>
        <Stack spacing={2} alignItems="center">
          <CircularProgress />
          <Typography>
            {phase === 'confirming' ? '正在向表单平台核实提交状态…' : '正在加载填报页面…'}
          </Typography>
        </Stack>
      </Box>
    );
  }

  if (phase === 'confirmed') {
    return (
      <Paper sx={{ p: 4, maxWidth: 720, mx: 'auto', mt: 4 }}>
        <Alert severity="success">
          表单已提交并通过远端核实，任务已转为“待审阅”。
        </Alert>
        {task?.confirmation && (
          <Typography sx={{ mt: 2 }} variant="body2" color="text.secondary">
            答卷标识：{task.confirmation.response_id}；远端提交时间：
            {task.confirmation.submitted_at ?? '未知'}
          </Typography>
        )}
        <Button sx={{ mt: 3 }} variant="contained" onClick={() => navigate(-1)}>
          返回任务列表
        </Button>
      </Paper>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      {errorMessage && (
        <Alert
          severity={phase === 'error' ? 'error' : 'warning'}
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={handleManualConfirm}>
              重新确认
            </Button>
          }
        >
          {errorMessage}
        </Alert>
      )}
      {embed && phase !== 'error' && (
        <Box
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            overflow: 'hidden',
            height: '72vh',
          }}
        >
          <iframe
            title="113.44 填报表单"
            src={embed.embedUrl}
            style={{ width: '100%', height: '100%', border: 'none' }}
            sandbox="allow-forms allow-scripts allow-same-origin allow-popups"
          />
        </Box>
      )}
      <Typography sx={{ mt: 1 }} variant="caption" color="text.secondary">
        嵌入链接为一次性令牌；关闭或过期后需重新创建填报任务，不能复用旧链接。
      </Typography>
    </Box>
  );
};

export default FormFillEmbedPage;
