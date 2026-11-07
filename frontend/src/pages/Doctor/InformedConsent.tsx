import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  TextField,
  InputAdornment,
  IconButton,
  Alert,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import VisibilityIcon from '@mui/icons-material/Visibility';
import AddIcon from '@mui/icons-material/Add';
// 直接使用 api.ts 默认导出的 axios 实例调用后端（知情同意暂无独立 service 方法）
import api from '../../services/api';

// 后端 GET /api/doctors/informed-consents 目前是桩（doctor_router.py 直接 return []），
// 无正式响应模型，此处仅按 dict 兜底渲染。
type ConsentRow = Record<string, any>;

const InformedConsent: React.FC = () => {
  const [consentForms, setConsentForms] = React.useState<ConsentRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [searchTerm, setSearchTerm] = React.useState('');

  // 加载知情同意书列表（后端为桩，当前始终返回空列表）
  const loadConsents = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get('/doctors/informed-consents');
      setConsentForms(Array.isArray(response.data) ? response.data : []);
    } catch (err: any) {
      setError(err.response?.data?.detail || '加载知情同意书列表失败');
      console.error('加载知情同意书列表失败:', err);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadConsents();
  }, []);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
  };

  // 前端按患者姓名/ID/表单名称过滤（后端暂无搜索参数）
  const filteredForms = consentForms.filter(form => {
    if (!searchTerm) return true;
    const keyword = searchTerm.toLowerCase();
    return [form.patient_name, form.patient_id, form.form_name, form.title]
      .some(field => typeof field === 'string' && field.toLowerCase().includes(keyword));
  });

  const getStatusChipColor = (status: string) => {
    return status === '已签署' || status === 'signed' ? 'success' : 'warning';
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        知情同意书管理
      </Typography>

      {/* 后端知情同意能力建设中：列表为桩接口，创建接口不落库，相关操作暂不可用 */}
      <Alert severity="info" sx={{ mb: 3 }}>
        知情同意书功能后端建设中，暂无数据。新建、查看、下载能力待后端建设后重新接入。
      </Alert>

      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between' }}>
        <TextField
          placeholder="搜索患者姓名、ID或表单名称..."
          variant="outlined"
          size="small"
          sx={{ width: 300 }}
          value={searchTerm}
          onChange={handleSearchChange}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
        {/* 后端 POST /doctors/informed-consents 为不落库的桩，禁用以免伪造创建成功 */}
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          disabled
          title="知情同意书创建接口后端暂未落库，暂不可用"
        >
          新建知情同意书
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
      )}

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>患者姓名</TableCell>
              <TableCell>患者ID</TableCell>
              <TableCell>表单名称</TableCell>
              <TableCell>签署日期</TableCell>
              <TableCell>状态</TableCell>
              <TableCell>主治医生</TableCell>
              <TableCell align="right">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  <CircularProgress size={24} sx={{ mr: 1 }} />
                  加载中...
                </TableCell>
              </TableRow>
            ) : filteredForms.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center">
                  {error ? '加载失败，请稍后重试' : '知情同意书功能后端建设中，暂无数据'}
                </TableCell>
              </TableRow>
            ) : (
              filteredForms.map((form, index) => (
                <TableRow key={form.id ?? index}>
                  <TableCell>{form.patient_name ?? form.patientName ?? '-'}</TableCell>
                  <TableCell>{form.patient_id ?? form.patientId ?? '-'}</TableCell>
                  <TableCell>{form.form_name ?? form.formName ?? form.title ?? '-'}</TableCell>
                  <TableCell>{form.signed_date ?? form.signedDate ?? '未签署'}</TableCell>
                  <TableCell>
                    {form.status ? (
                      <Chip
                        label={String(form.status)}
                        color={getStatusChipColor(String(form.status)) as "success" | "warning"}
                        size="small"
                      />
                    ) : '-'}
                  </TableCell>
                  <TableCell>{form.doctor_name ?? form.doctorName ?? '-'}</TableCell>
                  <TableCell align="right">
                    {/* 后端无知情同意书详情/文件下载接口，按钮禁用 */}
                    <IconButton
                      color="primary"
                      size="small"
                      title="查看（后端暂未提供）"
                      disabled
                    >
                      <VisibilityIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      <Box sx={{ mt: 3 }}>
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>
            知情同意书说明
          </Typography>
          <Typography variant="body1">
            本模块用于管理患者的知情同意书，医生可以创建、查看和下载患者的知情同意书。患者需要签署知情同意书后才能进行相关的康复治疗。
          </Typography>
        </Paper>
      </Box>
    </Box>
  );
};

export default InformedConsent;
