import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  TextField,
  InputAdornment,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import apiClient from '../../services/api';

// 患者管理：数据来自 GET /api/admin/patients
// 该接口目前为后端占位实现（恒返回 []），创建/编辑/删除接口未持久化，故禁用相关入口
// 行字段按管理员接口预期结构定义，渲染时逐字段兜底，避免占位/异常数据导致崩溃
interface PatientRow {
  id?: string;
  name?: string;
  age?: number;
  gender?: string;
  contact_number?: string;
  email?: string;
  address?: string;
  diagnosis?: string;
  doctor_assigned?: string;
  treatment_plan?: string;
  admission_date?: string;
  status?: string;
}

const PatientManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [patients, setPatients] = useState<PatientRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const fetchPatients = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get('/admin/patients');
        if (!cancelled) {
          setPatients(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取患者数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取患者数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchPatients();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 客户端关键词搜索
  const filteredPatients = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) {
      return patients;
    }
    return patients.filter(patient =>
      [patient.name, patient.id, patient.diagnosis, patient.doctor_assigned]
        .filter(Boolean)
        .some(field => String(field).toLowerCase().includes(keyword))
    );
  }, [patients, searchTerm]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const renderText = (value: unknown) => {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    return String(value);
  };

  // 加载中
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <CircularProgress />
        <Typography variant="body1" sx={{ ml: 2 }}>
          患者数据加载中...
        </Typography>
      </Box>
    );
  }

  // 加载失败：真实错误状态 + 重试
  if (error) {
    return (
      <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" height="300px">
        <Typography color="error" variant="body1" gutterBottom>
          {error}
        </Typography>
        <Button variant="outlined" onClick={() => setReloadKey(key => key + 1)}>
          重试
        </Button>
      </Box>
    );
  }

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h1">
          患者管理
        </Typography>
        <Box textAlign="right">
          <Button variant="contained" color="primary" startIcon={<AddIcon />} disabled>
            添加患者
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            后端患者创建/编辑/删除接口尚未实现持久化，功能待开放
          </Typography>
        </Box>
      </Box>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <TextField
            placeholder="搜索患者姓名、ID、诊断或医生..."
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={handleSearchChange}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
            sx={{ width: 300 }}
          />
        </Box>

        {filteredPatients.length === 0 ? (
          <Box sx={{ p: 4, textAlign: 'center' }}>
            <Typography variant="body1" color="text.secondary">
              暂无患者数据
            </Typography>
            <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
              后端管理接口建设中，暂无数据
            </Typography>
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>患者ID</TableCell>
                  <TableCell>姓名</TableCell>
                  <TableCell>年龄/性别</TableCell>
                  <TableCell>诊断</TableCell>
                  <TableCell>主治医生</TableCell>
                  <TableCell>治疗方案</TableCell>
                  <TableCell>联系方式</TableCell>
                  <TableCell>状态</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredPatients.map((patient, index) => (
                  <TableRow key={patient.id || `patient-${index}`}>
                    <TableCell>{renderText(patient.id)}</TableCell>
                    <TableCell>{renderText(patient.name)}</TableCell>
                    <TableCell>
                      {patient.age ? `${patient.age}岁` : '—'}/{renderText(patient.gender)}
                    </TableCell>
                    <TableCell>{renderText(patient.diagnosis)}</TableCell>
                    <TableCell>{renderText(patient.doctor_assigned)}</TableCell>
                    <TableCell>{renderText(patient.treatment_plan)}</TableCell>
                    <TableCell>{renderText(patient.contact_number)}</TableCell>
                    <TableCell>
                      {patient.status ? (
                        <Chip label={patient.status} size="small" />
                      ) : (
                        '—'
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
};

export default PatientManagement;
