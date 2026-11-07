import React, { useState } from 'react';
import {
  Box, Typography, Switch, FormGroup, FormControlLabel,
  Divider, Button, Alert,
  Card, CardContent
} from '@mui/material';
import { NotificationSettings as NotificationSettingsType } from '../../services/notificationService';

/**
 * 通知偏好设置面板。
 *
 * 后端 /api/notifications 目前没有 GET/PUT /notifications/settings 端点，
 * 偏好设置的读取与保存为后端能力待建设：本面板仅保留本地演示状态，
 * 保存按钮禁用，不再发起注定 404 的请求。
 */
const NotificationSettings: React.FC = () => {
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

  // 处理设置变更（仅本地演示状态，不会持久化）
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
          通知偏好设置的后端接口尚未建设（GET/PUT /api/notifications/settings 不存在），
          以下开关仅为本地演示，暂无法保存。
        </Alert>

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
          <Button
            variant="contained"
            color="primary"
            disabled
          >
            保存设置
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

export default NotificationSettings;
