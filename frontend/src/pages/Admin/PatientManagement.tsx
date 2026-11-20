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
import { apiErrorMessage } from '../../services/patientErrors';
import AccountCreateDialog from '../../components/Admin/AccountCreateDialog';

// 患者账号与临床患者档案是不同的实体。此页面管理 users 中的患者账号。
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
  const [createOpen, setCreateOpen] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchPatients = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const rows: PatientRow[] = [];
        const limit = 1000;
        for (let skip = 0; ; skip += limit) {
          const response = await apiClient.get('/admin/patients', { params: { skip, limit } });
          if (!Array.isArray(response.data)) throw new Error('患者列表格式无效');
          rows.push(...response.data);
          if (response.data.length < limit) break;
        }
        if (!cancelled) {
          setPatients(rows);
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
  if (isLoading && patients.length === 0) {
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
  if (error && patients.length === 0) {
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
          <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            添加患者
          </Button>
        </Box>
      </Box>

      <Paper sx={{ p: 2, mb: 3 }}>
        {error && <Typography color="error" role="alert" sx={{ mb: 2 }}>{error}</Typography>}
        {actionError && <Typography color="error" role="alert" sx={{ mb: 2 }}>{actionError}</Typography>}
        {isLoading && <CircularProgress size={20} sx={{ mb: 1 }} />}
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
              {searchTerm ? '没有符合搜索条件的患者' : '患者账号会显示在这里'}
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
                  <TableCell>账号</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredPatients.map((patient, index) => (
                  <TableRow key={patient.id || `patient-${index}`}>
                    <TableCell>{renderText(patient.id)}</TableCell>
                    <TableCell>{renderText(patient.name)}</TableCell>
                    <TableCell>
                      {patient.age != null ? `${patient.age}岁` : '—'}/{renderText(patient.gender)}
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
                    <TableCell>
                      <Button size="small" onClick={async () => {
                        setActionError('');
                        try {
                          await apiClient.put(`/admin/accounts/${patient.id}/active`, { active: patient.status !== '正常' });
                          setReloadKey(key => key + 1);
                        } catch (failure: any) {
                          setActionError(apiErrorMessage(failure, '账号状态更新失败，请重试。'));
                        }
                      }}>{patient.status === '正常' ? '停用' : '恢复'}</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
      <AccountCreateDialog open={createOpen} title="添加患者" path="/admin/patients" role="patient" onClose={() => setCreateOpen(false)} onCreated={() => setReloadKey(key => key + 1)} />
    </Box>
  );
};

export default PatientManagement;
