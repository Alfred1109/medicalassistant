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
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import VisibilityIcon from '@mui/icons-material/Visibility';
import { useNavigate } from 'react-router-dom';

// 模拟数据
const mockPatients = [
  { id: '1', name: '张三', age: 45, gender: '男', diagnosis: '腰椎间盘突出', status: '在治疗' },
  { id: '2', name: '李四', age: 62, gender: '女', diagnosis: '膝关节炎', status: '已完成' },
  { id: '3', name: '王五', age: 38, gender: '男', diagnosis: '肩周炎', status: '在治疗' },
  { id: '4', name: '赵六', age: 55, gender: '女', diagnosis: '颈椎病', status: '随访中' },
  { id: '5', name: '钱七', age: 41, gender: '男', diagnosis: '腕管综合征', status: '已完成' },
];

const PatientManagement: React.FC = () => {
  const [patients, setPatients] = useState(mockPatients);
  const [searchTerm, setSearchTerm] = useState('');
  const navigate = useNavigate();
  
  useEffect(() => {
    // 这里可以替换为实际的API调用
    // fetchPatients();
  }, []);
  
  const handleSearch = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
    // 在实际应用中可以发起API请求进行搜索
    // 这里简单模拟本地搜索功能
    if (event.target.value === '') {
      setPatients(mockPatients);
    } else {
      const filtered = mockPatients.filter(patient => 
        patient.name.includes(event.target.value) || 
        patient.diagnosis.includes(event.target.value)
      );
      setPatients(filtered);
    }
  };
  
  const handleViewPatient = (patientId: string) => {
    navigate(`/doctor/health-records/${patientId}`);
  };
  
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h2">
          患者管理
        </Typography>
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          onClick={() => console.log('添加患者')}
        >
          添加患者
        </Button>
      </Box>
      
      <Box mb={3}>
        <TextField
          fullWidth
          placeholder="搜索患者姓名或诊断..."
          variant="outlined"
          value={searchTerm}
          onChange={handleSearch}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
      </Box>
      
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>姓名</TableCell>
              <TableCell>年龄</TableCell>
              <TableCell>性别</TableCell>
              <TableCell>主要诊断</TableCell>
              <TableCell>状态</TableCell>
              <TableCell align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {patients.map((patient) => (
              <TableRow key={patient.id}>
                <TableCell>{patient.name}</TableCell>
                <TableCell>{patient.age}</TableCell>
                <TableCell>{patient.gender}</TableCell>
                <TableCell>{patient.diagnosis}</TableCell>
                <TableCell>
                  <Chip 
                    label={patient.status} 
                    color={
                      patient.status === '在治疗' ? 'primary' : 
                      patient.status === '已完成' ? 'success' : 
                      'warning'
                    }
                    size="small"
                  />
                </TableCell>
                <TableCell align="center">
                  <IconButton
                    color="primary"
                    onClick={() => handleViewPatient(patient.id)}
                  >
                    <VisibilityIcon />
                  </IconButton>
                  <IconButton
                    color="primary"
                    onClick={() => console.log('编辑', patient.id)}
                  >
                    <EditIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default PatientManagement; 