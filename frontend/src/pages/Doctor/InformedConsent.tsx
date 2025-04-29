import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
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
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import VisibilityIcon from '@mui/icons-material/Visibility';
import AddIcon from '@mui/icons-material/Add';

const InformedConsent: React.FC = () => {
  // 模拟数据
  const consentForms = [
    {
      id: 1,
      patientName: '张三',
      patientId: 'P20230001',
      formName: '神经康复治疗知情同意书',
      signedDate: '2023-05-15',
      status: '已签署',
      doctorName: '王医生',
    },
    {
      id: 2,
      patientName: '李四',
      patientId: 'P20230012',
      formName: '物理治疗知情同意书',
      signedDate: '2023-05-18',
      status: '已签署',
      doctorName: '赵医生',
    },
    {
      id: 3,
      patientName: '王五',
      patientId: 'P20230015',
      formName: '康复训练知情同意书',
      signedDate: null,
      status: '待签署',
      doctorName: '李医生',
    },
    {
      id: 4,
      patientName: '赵六',
      patientId: 'P20230022',
      formName: '神经康复治疗知情同意书',
      signedDate: '2023-05-20',
      status: '已签署',
      doctorName: '王医生',
    },
    {
      id: 5,
      patientName: '孙七',
      patientId: 'P20230025',
      formName: '物理治疗知情同意书',
      signedDate: null,
      status: '待签署',
      doctorName: '钱医生',
    },
  ];

  const [searchTerm, setSearchTerm] = React.useState('');
  const [filteredForms, setFilteredForms] = React.useState(consentForms);

  React.useEffect(() => {
    if (searchTerm) {
      setFilteredForms(consentForms.filter(form => 
        form.patientName.includes(searchTerm) || 
        form.patientId.includes(searchTerm) ||
        form.formName.includes(searchTerm)
      ));
    } else {
      setFilteredForms(consentForms);
    }
  }, [searchTerm]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
  };

  const getStatusChipColor = (status: string) => {
    return status === '已签署' ? 'success' : 'warning';
  };

  return (
    <Box>
      <Typography variant="h5" component="h1" gutterBottom>
        知情同意书管理
      </Typography>

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
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
        >
          新建知情同意书
        </Button>
      </Box>

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
            {filteredForms.map((form) => (
              <TableRow key={form.id}>
                <TableCell>{form.patientName}</TableCell>
                <TableCell>{form.patientId}</TableCell>
                <TableCell>{form.formName}</TableCell>
                <TableCell>{form.signedDate || '未签署'}</TableCell>
                <TableCell>
                  <Chip 
                    label={form.status} 
                    color={getStatusChipColor(form.status) as "success" | "warning"}
                    size="small" 
                  />
                </TableCell>
                <TableCell>{form.doctorName}</TableCell>
                <TableCell align="right">
                  <IconButton 
                    color="primary"
                    size="small"
                    title="查看"
                  >
                    <VisibilityIcon fontSize="small" />
                  </IconButton>
                  <IconButton 
                    color="primary"
                    size="small"
                    title="下载"
                  >
                    <FileDownloadIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Grid container spacing={3} sx={{ mt: 3 }}>
        <Grid item xs={12}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              知情同意书说明
            </Typography>
            <Typography variant="body1">
              本模块用于管理患者的知情同意书，医生可以创建、查看和下载患者的知情同意书。患者需要签署知情同意书后才能进行相关的康复治疗。
            </Typography>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default InformedConsent; 