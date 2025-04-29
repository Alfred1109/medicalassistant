import React, { useState, useEffect } from 'react';
import {
  Box, Typography, Switch, FormGroup, FormControlLabel,
  Divider, Paper, Button, Alert, Snackbar,
  CircularProgress, Card, CardContent
} from '@mui/material';
import { notificationApi, NotificationSettings as NotificationSettingsType } from '../../services/notificationService';

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
  
  const [loading, setLoading] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [notification, setNotification] = useState({ 
    open: false, 
    message: '', 
    severity: 'success' as 'success' | 'error' | 'info' | 'warning' 
  });
  
  // 加载设置
  useEffect(() => {
    const loadSettings = async () => {
      try {
        setLoading(true);
        const response = await notificationApi.getSettings();
        setSettings(response.data);
      } catch (error) {
        console.error('加载通知设置失败:', error);
        setNotification({
          open: true,
          message: '加载通知设置失败',
          severity: 'error'
        });
      } finally {
        setLoading(false);
      }
    };
    
    loadSettings();
  }, []);
  
  // 处理设置变更
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSettings({
      ...settings,
      [event.target.name]: event.target.checked
    });
  };
  
  // 保存设置
  const handleSave = async () => {
    try {
      setSaveLoading(true);
      await notificationApi.updateSettings(settings);
      setNotification({
        open: true,
        message: '通知设置已保存',
        severity: 'success'
      });
    } catch (error) {
      console.error('保存通知设置失败:', error);
      setNotification({
        open: true,
        message: '保存通知设置失败',
        severity: 'error'
      });
    } finally {
      setSaveLoading(false);
    }
  };
  
  // 关闭通知
  const handleCloseNotification = () => {
    setNotification({ ...notification, open: false });
  };
  
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="300px">
        <CircularProgress />
      </Box>
    );
  }
  
  return (
    <Card>
      <CardContent>
        <Box mb={3}>
          <Typography variant="h6" gutterBottom>通知设置</Typography>
          <Divider />
        </Box>
        
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
            onClick={handleSave}
            disabled={saveLoading}
            startIcon={saveLoading ? <CircularProgress size={20} /> : null}
          >
            {saveLoading ? '保存中...' : '保存设置'}
          </Button>
        </Box>
        
        <Snackbar
          open={notification.open}
          autoHideDuration={6000}
          onClose={handleCloseNotification}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert onClose={handleCloseNotification} severity={notification.severity}>
            {notification.message}
          </Alert>
        </Snackbar>
      </CardContent>
    </Card>
  );
};

export default NotificationSettings; 