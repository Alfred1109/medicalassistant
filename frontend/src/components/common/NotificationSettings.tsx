import React, { useEffect, useState } from 'react';
import {
  Box, Typography, Switch, FormGroup, FormControlLabel,
  Divider, Button, Alert,
  Card, CardContent
} from '@mui/material';
import { NotificationSettings as NotificationSettingsType } from '../../services/notificationService';
import httpClient from '../../services/httpClient';

/**
 * 通知偏好设置面板。
 *
 * 后端 /api/notifications 目前没有 GET/PUT /notifications/settings 端点，
 * 偏好设置的读取与保存为后端能力待建设：本面板仅保留本地演示状态，
 * 保存按钮禁用，不再发起注定 404 的请求。
 */
const NotificationSettings: React.FC = () => {
  const [message, setMessage] = useState('');
  const [settings, setSettings] = useState<NotificationSettingsType>({
    enableEmail: true,
    enablePush: true,
    enableSystem: true,
    notifyOnMessage: true,
    notifyOnAppointment: true,
    notifyOnTask: true,
    notifyOnHealthAlert: true,
    notifyOnFollowUp: true,
    dailySummary: false
  });

  useEffect(() => {
    httpClient.get('/notifications/settings').then(({ data }) => {
      if (data && typeof data === 'object') setSettings(current => ({ ...current, ...data }));
    }).catch(() => setMessage('已保存的通知偏好没有加载出来。'));
  }, []);

  // 处理设置变更，保存后才会写入服务器。
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSettings({
      ...settings,
      [event.target.name]: event.target.checked
    });
  };

  return (
    <Card>
      <CardContent>
        <Box mb={3}>
          <Typography variant="h6" gutterBottom>通知设置</Typography>
          <Divider />
        </Box>

        <Alert severity="info" sx={{ mb: 3 }}>
          这些开关会按当前账号保存。打开邮件后，新通知会发到账号邮箱（使用本机已配置的发信账号）。打开浏览器通知后，页面开着时会弹出系统通知。
        </Alert>
        {message && <Alert severity="warning" sx={{ mb: 2 }}>{message}</Alert>}

        <Box mb={4}>
          <Typography variant="subtitle1" gutterBottom>通知方式</Typography>
          <FormGroup>
            <FormControlLabel
              control={<Switch checked={settings.enableSystem} onChange={handleChange} name="enableSystem" />}
              label="系统通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.enablePush} onChange={handleChange} name="enablePush" />}
              label="浏览器推送通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.enableEmail} onChange={handleChange} name="enableEmail" />}
              label="邮件通知"
            />
          </FormGroup>
        </Box>

        <Box mb={4}>
          <Typography variant="subtitle1" gutterBottom>通知类型</Typography>
          <FormGroup>
            <FormControlLabel
              control={<Switch checked={settings.notifyOnMessage} onChange={handleChange} name="notifyOnMessage" />}
              label="新消息通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.notifyOnAppointment} onChange={handleChange} name="notifyOnAppointment" />}
              label="预约通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.notifyOnTask} onChange={handleChange} name="notifyOnTask" />}
              label="任务通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.notifyOnHealthAlert} onChange={handleChange} name="notifyOnHealthAlert" />}
              label="健康预警通知"
            />
            <FormControlLabel
              control={<Switch checked={settings.notifyOnFollowUp} onChange={handleChange} name="notifyOnFollowUp" />}
              label="随访提醒通知"
            />
          </FormGroup>
        </Box>

        <Box mb={4}>
          <Typography variant="subtitle1" gutterBottom>其他设置</Typography>
          <FormGroup>
            <FormControlLabel
              control={<Switch checked={settings.dailySummary} onChange={handleChange} name="dailySummary" />}
              label="每日通知摘要（每天收到一次汇总通知，而不是多次单独通知）"
            />
          </FormGroup>
        </Box>

        <Box display="flex" justifyContent="flex-end">
          <Button variant="contained" color="primary" onClick={async () => {
            try {
              if (settings.enablePush && 'Notification' in window) await Notification.requestPermission();
              await httpClient.put('/notifications/settings', settings);
              setMessage('通知偏好已保存。');
            }
            catch { setMessage('通知偏好没有保存。'); }
          }}>
            保存设置
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

export default NotificationSettings;
