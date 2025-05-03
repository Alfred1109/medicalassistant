import React, { useState, useEffect } from 'react';
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
import { useApi } from '../../hooks/useApi';
import { Patient } from '../../types/patient.types';

const PatientManagement: React.FC = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [filteredPatients, setFilteredPatients] = useState<Patient[]>([]);
  
  // 使用API钩子获取患者列表
  const { 
    data: patients,
    loading,
    error,
    execute: fetchPatients 
  } = useApi<Patient[]>(apiService.doctor.getPatients, true);
  
  // 搜索处理
  useEffect(() => {
    if (patients) {
      if (searchTerm) {
        const filtered = patients.filter(
          (patient) =>
            patient.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            patient.diagnosis?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            patient.status?.toLowerCase().includes(searchTerm.toLowerCase())
        );
        setFilteredPatients(filtered);
      } else {
        setFilteredPatients(patients);
      }
    } else {
      // 没有数据时显示空数组，而不是使用模拟数据
      setFilteredPatients([]);
    }
  }, [searchTerm, patients]);
  
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
    </Box>
  );
};

export default PatientManagement; 