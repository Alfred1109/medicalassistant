import React from 'react';
import {
  Box,
  Container,
  Typography,
  Paper,
  Button,
  Alert,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';

/**
 * 知情同意文档中心（占位页）。
 *
 * 原页面依赖 frontend/src/services/consentService.ts 的 /consent/* 系列端点
 * （documents / templates / signatures / pdf），后端从未注册过 /api/consent 路由，
 * 全部为注定 404 的死链，服务文件已随本次清理删除。
 * 知情同意能力待后端建设后重新接入（后端现仅有医生端 GET/POST /api/doctors/informed-consents 桩）。
 */
const ConsentUnavailableNotice: React.FC<{ title: string; description: string }> = ({
  title,
  description,
}) => {
  const navigate = useNavigate();

  return (
    <Container maxWidth="md" sx={{ py: 6 }}>
      <Paper sx={{ p: 4 }}>
        <Typography variant="h5" gutterBottom>
          {title}
        </Typography>
        <Alert severity="info" sx={{ my: 3 }}>
          {description}
        </Alert>
        <Typography variant="body2" color="text.secondary" paragraph>
          后端知情同意能力待建设：/api/consent 下的文档、模板、签名与 PDF 下载端点均未注册，
          相关功能已停用以避免无效请求。
        </Typography>
        <Button
          variant="outlined"
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(-1)}
        >
          返回
        </Button>
      </Paper>
    </Container>
  );
};

export default ConsentUnavailableNotice;
