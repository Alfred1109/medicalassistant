import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Grid,
  Alert,
  CircularProgress,
  Divider,
  Chip,
  IconButton,
  Tooltip
} from '@mui/material';
import Step from '@mui/material/Step';
import Stepper from '@mui/material/Stepper';
import StepLabel from '@mui/material/StepLabel';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import UploadIcon from '@mui/icons-material/Upload';
import StorageIcon from '@mui/icons-material/Storage';
import CheckIcon from '@mui/icons-material/Check';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import SaveAltIcon from '@mui/icons-material/SaveAlt';
import ClearIcon from '@mui/icons-material/Clear';
import EditIcon from '@mui/icons-material/Edit';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';

// 数据类型定义
type HealthDataType = 'blood_pressure' | 'blood_glucose' | 'heart_rate' | 'body_temperature' | 'weight' | 'oxygen_saturation' | 'respiratory_rate' | 'step_count' | 'sleep' | 'other';

// 健康数据映射
const healthDataTypeMap: Record<HealthDataType, { label: string, fields: string[] }> = {
  blood_pressure: { 
    label: '血压', 
    fields: ['测量时间', '收缩压', '舒张压', '脉搏'] 
  },
  blood_glucose: { 
    label: '血糖', 
    fields: ['测量时间', '血糖值', '测量状态'] 
  },
  heart_rate: { 
    label: '心率', 
    fields: ['测量时间', '心率值'] 
  },
  body_temperature: { 
    label: '体温', 
    fields: ['测量时间', '体温值'] 
  },
  weight: { 
    label: '体重', 
    fields: ['测量时间', '体重值', '身高', 'BMI'] 
  },
  oxygen_saturation: { 
    label: '血氧饱和度', 
    fields: ['测量时间', '血氧值'] 
  },
  respiratory_rate: { 
    label: '呼吸频率', 
    fields: ['测量时间', '呼吸频率值'] 
  },
  step_count: { 
    label: '步数', 
    fields: ['日期', '步数', '距离', '消耗卡路里'] 
  },
  sleep: { 
    label: '睡眠', 
    fields: ['日期', '睡眠时长', '深睡时长', '浅睡时长', '醒来次数'] 
  },
  other: { 
    label: '其他', 
    fields: ['测量时间', '数据值', '数据类型'] 
  }
};

interface FieldMapping {
  sourceField: string;
  targetField: string;
}

interface HealthDataImportComponentProps {
  patientId?: string;
  onImportData: (data: any[], type: HealthDataType) => Promise<void>;
}

const HealthDataImportComponent: React.FC<HealthDataImportComponentProps> = ({
  patientId,
  onImportData
}) => {
  // 状态管理
  const [activeStep, setActiveStep] = React.useState(0);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [parsedData, setParsedData] = React.useState<any[]>([]);
  const [rawHeaders, setRawHeaders] = React.useState<string[]>([]);
  const [selectedDataType, setSelectedDataType] = React.useState<HealthDataType>('blood_pressure');
  const [fieldMappings, setFieldMappings] = React.useState<FieldMapping[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [success, setSuccess] = React.useState<string | null>(null);
  const [previewData, setPreviewData] = React.useState<any[]>([]);
  
  // 步骤定义
  const steps = ['选择数据类型', '上传文件', '映射字段', '预览数据', '导入确认'];
  
  // 处理数据类型选择
  const handleDataTypeChange = (event: any) => {
    setSelectedDataType(event.target.value as HealthDataType);
    // 重置字段映射
    resetFieldMappings();
  };
  
  // 重置字段映射
  const resetFieldMappings = () => {
    setFieldMappings([]);
  };
  
  // 处理文件选择
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
    
    if (file) {
      // 根据文件类型进行解析
      parseFile(file);
    } else {
      setParsedData([]);
      setRawHeaders([]);
      resetFieldMappings();
    }
  };
  
  // 解析文件
  const parseFile = (file: File) => {
    setLoading(true);
    setError(null);
    
    const fileExtension = file.name.split('.').pop()?.toLowerCase();
    
    if (fileExtension === 'csv') {
      Papa.parse(file, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => {
          handleParseResults(results.data, Object.keys(results.data[0] || {}));
          setLoading(false);
        },
        error: (error) => {
          setError(`解析CSV文件失败: ${error.message}`);
          setLoading(false);
        }
      });
    } else if (['xlsx', 'xls'].includes(fileExtension || '')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = e.target?.result;
          const workbook = XLSX.read(data, { type: 'binary' });
          const sheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[sheetName];
          const parsedData = XLSX.utils.sheet_to_json(worksheet);
          
          if (parsedData.length > 0) {
            handleParseResults(parsedData, Object.keys(parsedData[0] || {}));
          } else {
            setError('Excel文件不包含有效数据');
          }
        } catch (error: any) {
          setError(`解析Excel文件失败: ${error.message}`);
        }
        setLoading(false);
      };
      reader.onerror = () => {
        setError('读取文件失败');
        setLoading(false);
      };
      reader.readAsBinaryString(file);
    } else {
      setError('不支持的文件格式。请上传CSV或Excel文件');
      setLoading(false);
    }
  };
  
  // 处理解析结果
  const handleParseResults = (data: any[], headers: string[]) => {
    setParsedData(data);
    setRawHeaders(headers);
    
    // 尝试自动映射字段
    autoMapFields(headers);
  };
  
  // 自动映射字段
  const autoMapFields = (headers: string[]) => {
    const targetFields = healthDataTypeMap[selectedDataType].fields;
    const newMappings: FieldMapping[] = [];
    
    // 简单的自动映射逻辑
    targetFields.forEach(targetField => {
      // 寻找匹配的表头
      const matchingHeader = headers.find(header => 
        header.toLowerCase().includes(targetField.toLowerCase()) || 
        targetField.toLowerCase().includes(header.toLowerCase())
      );
      
      if (matchingHeader) {
        newMappings.push({
          sourceField: matchingHeader,
          targetField
        });
      } else {
        // 没有找到匹配项，创建空映射
        newMappings.push({
          sourceField: '',
          targetField
        });
      }
    });
    
    setFieldMappings(newMappings);
  };
  
  // 处理映射字段变更
  const handleMappingChange = (index: number, sourceField: string) => {
    const newMappings = [...fieldMappings];
    newMappings[index] = {
      ...newMappings[index],
      sourceField
    };
    setFieldMappings(newMappings);
  };
  
  // 生成预览数据
  const generatePreviewData = () => {
    // 确保所有必要的字段都已映射
    const hasRequiredMappings = fieldMappings.every(mapping => 
      mapping.targetField && mapping.sourceField
    );
    
    if (!hasRequiredMappings) {
      setError('所有必填字段都需要映射才能继续');
      return;
    }
    
    // 转换数据
    const preview = parsedData.slice(0, 10).map(row => {
      const newRow: any = {};
      
      fieldMappings.forEach(mapping => {
        if (mapping.sourceField && mapping.targetField) {
          newRow[mapping.targetField] = row[mapping.sourceField];
        }
      });
      
      return newRow;
    });
    
    setPreviewData(preview);
    setActiveStep(3); // 进入预览步骤
    setError(null);
  };
  
  // 处理导入
  const handleImport = async () => {
    if (!parsedData.length) {
      setError('没有数据可导入');
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      // 转换所有数据行
      const transformedData = parsedData.map(row => {
        const newRow: any = {};
        
        fieldMappings.forEach(mapping => {
          if (mapping.sourceField && mapping.targetField) {
            newRow[mapping.targetField] = row[mapping.sourceField];
          }
        });
        
        return newRow;
      });
      
      // 调用导入函数
      await onImportData(transformedData, selectedDataType);
      
      setSuccess(`成功导入 ${transformedData.length} 条${healthDataTypeMap[selectedDataType].label}数据`);
      setActiveStep(4); // 完成步骤
    } catch (error: any) {
      setError(`导入失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理步骤前进
  const handleNext = () => {
    if (activeStep === 0 && !selectedDataType) {
      setError('请选择数据类型');
      return;
    }
    
    if (activeStep === 1 && !selectedFile) {
      setError('请选择要上传的文件');
      return;
    }
    
    if (activeStep === 2) {
      generatePreviewData();
      return;
    }
    
    if (activeStep === 3) {
      handleImport();
      return;
    }
    
    setActiveStep(prevStep => prevStep + 1);
    setError(null);
  };
  
  // 处理步骤后退
  const handleBack = () => {
    setActiveStep(prevStep => prevStep - 1);
    setError(null);
  };
  
  // 重置整个流程
  const handleReset = () => {
    setActiveStep(0);
    setSelectedFile(null);
    setParsedData([]);
    setRawHeaders([]);
    setSelectedDataType('blood_pressure');
    setFieldMappings([]);
    setPreviewData([]);
    setError(null);
    setSuccess(null);
  };
  
  // 渲染步骤内容
  const renderStepContent = () => {
    switch (activeStep) {
      case 0:
        return (
          <Box p={3}>
            <Typography variant="h6" gutterBottom>
              选择要导入的健康数据类型
            </Typography>
            <FormControl fullWidth sx={{ mt: 2 }}>
              <InputLabel>数据类型</InputLabel>
              <Select
                value={selectedDataType}
                onChange={handleDataTypeChange}
                label="数据类型"
              >
                {Object.entries(healthDataTypeMap).map(([key, { label }]) => (
                  <MenuItem key={key} value={key}>{label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" color="textSecondary" sx={{ mt: 2 }}>
              选择的数据类型: {healthDataTypeMap[selectedDataType].label}
            </Typography>
            <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
              需要包含的字段: {healthDataTypeMap[selectedDataType].fields.join(', ')}
            </Typography>
          </Box>
        );
      
      case 1:
        return (
          <Box p={3}>
            <Typography variant="h6" gutterBottom>
              上传{healthDataTypeMap[selectedDataType].label}数据文件
            </Typography>
            <Box 
              sx={{ 
                border: '2px dashed #ccc', 
                p: 4, 
                textAlign: 'center',
                borderRadius: 2,
                bgcolor: 'background.default',
                mt: 2
              }}
            >
              <input
                accept=".csv,.xlsx,.xls"
                style={{ display: 'none' }}
                id="file-upload"
                type="file"
                onChange={handleFileChange}
              />
              <label htmlFor="file-upload">
                <Button
                  variant="contained"
                  component="span"
                  startIcon={<CloudUploadIcon />}
                >
                  选择文件
                </Button>
              </label>
              
              {selectedFile && (
                <Box mt={2}>
                  <Typography variant="body1">
                    已选择文件: {selectedFile.name}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    文件大小: {(selectedFile.size / 1024).toFixed(2)} KB
                  </Typography>
                  <Box mt={1} display="flex" justifyContent="center">
                    <Button 
                      size="small" 
                      startIcon={<ClearIcon />}
                      onClick={() => {
                        setSelectedFile(null);
                        setParsedData([]);
                        setRawHeaders([]);
                      }}
                    >
                      移除文件
                    </Button>
                  </Box>
                </Box>
              )}
              
              <Typography variant="body2" color="textSecondary" mt={2}>
                支持的文件格式: CSV, Excel (.xlsx, .xls)
              </Typography>
            </Box>
            
            {loading && (
              <Box display="flex" justifyContent="center" mt={2}>
                <CircularProgress size={24} />
                <Typography variant="body2" sx={{ ml: 1 }}>
                  正在解析文件...
                </Typography>
              </Box>
            )}
            
            {parsedData.length > 0 && (
              <Box mt={2}>
                <Alert severity="success">
                  成功解析 {parsedData.length} 条数据记录
                </Alert>
              </Box>
            )}
          </Box>
        );
      
      case 2:
        return (
          <Box p={3}>
            <Typography variant="h6" gutterBottom>
              映射数据字段
            </Typography>
            <Typography variant="body2" color="textSecondary" mb={2}>
              请将源数据字段映射到目标健康数据字段
            </Typography>
            
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: '50%' }}>目标字段</TableCell>
                    <TableCell sx={{ width: '50%' }}>源数据字段</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {fieldMappings.map((mapping, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        <Typography fontWeight="medium">{mapping.targetField}</Typography>
                      </TableCell>
                      <TableCell>
                        <FormControl fullWidth size="small">
                          <Select
                            value={mapping.sourceField}
                            onChange={(e) => handleMappingChange(index, e.target.value as string)}
                            displayEmpty
                          >
                            <MenuItem value="">
                              <em>未映射</em>
                            </MenuItem>
                            {rawHeaders.map(header => (
                              <MenuItem key={header} value={header}>
                                {header}
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            
            <Box mt={2}>
              <Typography variant="body2" color="textSecondary">
                提示: 系统已尝试自动映射字段，请检查并调整映射关系
              </Typography>
            </Box>
          </Box>
        );
      
      case 3:
        return (
          <Box p={3}>
            <Typography variant="h6" gutterBottom>
              预览数据
            </Typography>
            <Typography variant="body2" color="textSecondary" mb={2}>
              预览前 {Math.min(previewData.length, 10)} 条数据记录，检查是否正确
            </Typography>
            
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    {healthDataTypeMap[selectedDataType].fields.map(field => (
                      <TableCell key={field}>{field}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {previewData.map((row, rowIndex) => (
                    <TableRow key={rowIndex}>
                      {healthDataTypeMap[selectedDataType].fields.map(field => (
                        <TableCell key={field}>
                          {row[field] || ''}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            
            <Box mt={2} display="flex" alignItems="center">
              <Chip 
                icon={<StorageIcon />} 
                label={`总计 ${parsedData.length} 条记录`} 
                variant="outlined" 
              />
              <Typography variant="body2" color="textSecondary" ml={2}>
                确认预览数据无误后，点击"导入数据"开始导入
              </Typography>
            </Box>
          </Box>
        );
      
      case 4:
        return (
          <Box p={3} textAlign="center">
            <CheckIcon sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              数据导入完成
            </Typography>
            {success && (
              <Alert severity="success" sx={{ mt: 2, mb: 2 }}>
                {success}
              </Alert>
            )}
            <Button
              variant="contained"
              color="primary"
              onClick={handleReset}
              startIcon={<UploadIcon />}
              sx={{ mt: 2 }}
            >
              导入更多数据
            </Button>
          </Box>
        );
      
      default:
        return null;
    }
  };
  
  return (
    <Paper variant="outlined" sx={{ mb: 3 }}>
      <Box p={2}>
        <Typography variant="h6">健康数据导入</Typography>
      </Box>
      <Divider />
      
      <Box p={2}>
        <Stepper activeStep={activeStep} alternativeLabel>
          {steps.map(label => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
      </Box>
      
      {error && (
        <Box px={3} mb={2}>
          <Alert severity="error">{error}</Alert>
        </Box>
      )}
      
      {renderStepContent()}
      
      <Box p={2} display="flex" justifyContent="space-between">
        <Button
          disabled={activeStep === 0 || activeStep === 4 || loading}
          onClick={handleBack}
        >
          上一步
        </Button>
        <Box>
          {activeStep !== 4 && (
            <Button
              variant="contained"
              color="primary"
              onClick={handleNext}
              disabled={
                (activeStep === 1 && !selectedFile) ||
                loading
              }
              endIcon={loading ? <CircularProgress size={20} /> : null}
            >
              {activeStep === 3 ? '导入数据' : '下一步'}
            </Button>
          )}
        </Box>
      </Box>
    </Paper>
  );
};

export default HealthDataImportComponent; 