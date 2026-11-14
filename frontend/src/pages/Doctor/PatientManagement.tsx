import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Chip,
  InputAdornment,
  CircularProgress,
  Alert,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { useNavigate } from 'react-router-dom';
import { apiService } from '../../services/api';
import { patientDomainErrorCopy } from '../../services/patientErrors';
import {
  mergePatientBatches,
  patientBatchComplete,
  patientLoadMoreAvailable,
  PATIENT_LIST_ONE_SHOT_CAP,
  PATIENT_LIST_PAGE_SIZE,
} from '../../services/patientList';
import { useApi } from '../../hooks/useApi';
import { Patient } from '../../types/patient.types';

const PatientManagement: React.FC = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredPatients, setFilteredPatients] = useState<Patient[]>([]);
  // T59 分页预适配：缺省仍为一次性全量拉取；「加载更多」为可选追加路径，
  // 仅在一次性结果达到上限阈值（canonical 域缺省截断场景）时出现。
  const [morePatients, setMorePatients] = useState<Patient[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState('');
  const [allLoaded, setAllLoaded] = useState(false);

  // 使用API钩子获取患者列表
  const {
    data: patients,
    loading,
    error,
    execute: fetchPatients
  } = useApi<Patient[], []>(apiService.doctor.getPatients, true);

  // 一次性全量 + 「加载更多」追加的合并视图；未追加时与原全量行为一致。
  const allPatients = useMemo(
    () => mergePatientBatches<Patient>(patients, morePatients),
    [patients, morePatients]
  );

  // 基础列表刷新（首次/重试）时清空追加批次与加载完成标记
  useEffect(() => {
    setMorePatients([]);
    setMoreError('');
    setAllLoaded(false);
  }, [patients]);

  // 搜索处理
  useEffect(() => {
    if (allPatients.length > 0) {
      if (searchTerm) {
        const filtered = allPatients.filter(
          (patient) =>
            patient.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            patient.diagnosis?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            patient.status?.toLowerCase().includes(searchTerm.toLowerCase())
        );
        setFilteredPatients(filtered);
      } else {
        setFilteredPatients(allPatients);
      }
    } else {
      // 没有数据时显示空数组，而不是使用模拟数据
      setFilteredPatients([]);
    }
  }, [searchTerm, allPatients]);

  const totalLoaded = allPatients.length;
  const showLoadMore = patientLoadMoreAvailable(totalLoaded, allLoaded);

  const handleLoadMore = async () => {
    if (loadingMore || loading) return;
    setLoadingMore(true);
    setMoreError('');
    try {
      const { data } = await apiService.doctor.getPatients(
        { skip: totalLoaded, limit: PATIENT_LIST_PAGE_SIZE });
      const batch = Array.isArray(data) ? data : [];
      setMorePatients((prev) => mergePatientBatches<Patient>(prev, batch));
      if (patientBatchComplete(batch.length)) setAllLoaded(true);
    } catch (err) {
      // 患者域错误（含 503 INVALID_PATIENT_PAGINATION）走统一文案映射
      setMoreError(patientDomainErrorCopy(err) ?? '加载更多患者失败，请重试。');
    } finally {
      setLoadingMore(false);
    }
  };
  
  // 重试获取数据
  const handleRetry = () => {
    fetchPatients();
  };
  
  // 状态显示样式
  const getStatusChipColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case '在治疗':
        return 'primary';
      case '已完成':
        return 'success';
      case '随访中':
        return 'info';
      default:
        return 'default';
    }
  };

  return (
    <Box p={3}>
      <Typography variant="h4" gutterBottom>
        患者管理
      </Typography>
      
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <TextField
          placeholder="搜索患者"
          variant="outlined"
          size="small"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
          sx={{ width: '300px' }}
        />
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          onClick={() => navigate('/app/doctor/patients/add')}
        >
          添加患者
        </Button>
      </Box>

      {error && (
        <Alert 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={handleRetry}>
              重试
            </Button>
          }
        >
          获取患者数据时出错：{error.message}
        </Alert>
      )}

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>患者姓名</TableCell>
              <TableCell>年龄</TableCell>
              <TableCell>性别</TableCell>
              <TableCell>诊断</TableCell>
              <TableCell>状态</TableCell>
              <TableCell align="right">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <CircularProgress size={24} />
                  <Typography variant="body2" sx={{ ml: 1 }}>
                    加载中...
                  </Typography>
                </TableCell>
              </TableRow>
            ) : filteredPatients.length > 0 ? (
              filteredPatients.map((patient) => (
                <TableRow key={patient.id}>
                  <TableCell>{patient.name}</TableCell>
                  <TableCell>{patient.age}</TableCell>
                  <TableCell>{patient.gender}</TableCell>
                  <TableCell>{patient.diagnosis}</TableCell>
                  <TableCell>
                    <Chip
                      label={patient.status || '未知'}
                      color={getStatusChipColor(patient.status || '')}
                      size="small"
                    />
                  </TableCell>
                  <TableCell align="right">
                    <IconButton
                      color="primary"
                      onClick={() => navigate(`/app/doctor/patients/${patient.id}`)}
                    >
                      <VisibilityIcon />
                    </IconButton>
                    <IconButton
                      color="secondary"
                      onClick={() => navigate(`/app/doctor/patients/${patient.id}/edit`)}
                    >
                      <EditIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  {error ? '加载数据失败，请点击重试按钮' : '没有找到匹配的患者'}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {moreError && (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button color="inherit" size="small" onClick={handleLoadMore}>
              重试
            </Button>
          }
        >
          {moreError}
        </Alert>
      )}
      {showLoadMore && (
        <Box display="flex" flexDirection="column" alignItems="center" mt={2}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            已加载 {totalLoaded} 名患者，可能还有更多
          </Typography>
          <Button
            variant="outlined"
            onClick={handleLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? '加载中...' : '加载更多患者'}
          </Button>
        </Box>
      )}
      {!showLoadMore && allLoaded && totalLoaded >= PATIENT_LIST_ONE_SHOT_CAP && (
        <Typography variant="body2" color="text.secondary" align="center" mt={2}>
          已加载全部患者
        </Typography>
      )}
    </Box>
  );
};

export default PatientManagement; 