import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
  Stepper,
  Step,
  StepLabel,
  Paper,
  Divider,
  Grid,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormHelperText,
  IconButton,
  Chip,
  Tab,
  Tabs,
  CircularProgress,
  Alert,
  Stack
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import FileUploadIcon from '@mui/icons-material/FileUpload';
import CloudSyncIcon from '@mui/icons-material/CloudSync';
import HealthAndSafetyIcon from '@mui/icons-material/HealthAndSafety';
import DevicesIcon from '@mui/icons-material/Devices';
import TableChartIcon from '@mui/icons-material/TableChart';
import CableIcon from '@mui/icons-material/Cable';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { styled } from '@mui/material/styles';

// 导入类型定义（假设已经从HealthDataForm.tsx中导出）
import { HealthDataRecord } from './HealthDataForm';

// 定义导入来源类型
enum ImportSourceType {
  CSV_FILE = 'csv_file',
  EXCEL_FILE = 'excel_file',
  APPLE_HEALTH = 'apple_health',
  GOOGLE_FIT = 'google_fit',
  FITBIT = 'fitbit',
  WITHINGS = 'withings',
  GARMIN = 'garmin',
  CUSTOM_DEVICE = 'custom_device'
}

// 设备导入选项接口
interface DeviceImportOption {
  id: ImportSourceType;
  name: string;
  icon: React.ReactNode;
  description: string;
  supported: boolean;
}

// 文件导入选项接口
interface FileImportOption {
  id: ImportSourceType;
  name: string;
  icon: React.ReactNode;
  description: string;
  supportedExtensions: string[];
  templateUrl?: string;
}

// 数据行接口（用于验证导入的数据）
interface DataRow {
  [key: string]: any;
}

// 定义导入标签页
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 标签页面板组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`import-tabpanel-${index}`}
      aria-labelledby={`import-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// 上传区域样式组件
const UploadArea = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(4),
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  borderStyle: 'dashed',
  borderWidth: 2,
  borderColor: theme.palette.divider,
  backgroundColor: theme.palette.background.default,
  cursor: 'pointer',
  '&:hover': {
    borderColor: theme.palette.primary.main,
    backgroundColor: theme.palette.action.hover,
  },
  minHeight: 200,
}));

// 设备图标样式组件
const DeviceIconWrapper = styled(Box)(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 64,
  height: 64,
  borderRadius: '50%',
  backgroundColor: theme.palette.background.default,
  marginBottom: theme.spacing(2),
}));

// 设备选项样式组件
const DeviceOption = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(3),
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  height: '100%',
  '&:hover': {
    borderColor: theme.palette.primary.main,
    backgroundColor: theme.palette.action.hover,
  },
  '&.selected': {
    borderColor: theme.palette.primary.main,
    borderWidth: 2,
    borderStyle: 'solid',
  },
}));

// 健康数据导入对话框组件属性
interface HealthDataImportModalProps {
  open: boolean;
  onClose: () => void;
  onImportComplete: (data: HealthDataRecord[]) => void;
  patientId: string;
}

// 文件导入选项
const fileImportOptions: FileImportOption[] = [
  {
    id: ImportSourceType.CSV_FILE,
    name: 'CSV文件导入',
    icon: <TableChartIcon fontSize="large" />,
    description: '导入CSV格式的健康数据文件',
    supportedExtensions: ['.csv'],
    templateUrl: '/templates/health_data_import_template.csv',
  },
  {
    id: ImportSourceType.EXCEL_FILE,
    name: 'Excel文件导入',
    icon: <TableChartIcon fontSize="large" />,
    description: '导入Excel格式的健康数据文件',
    supportedExtensions: ['.xlsx', '.xls'],
    templateUrl: '/templates/health_data_import_template.xlsx',
  },
];

// 设备导入选项
const deviceImportOptions: DeviceImportOption[] = [
  {
    id: ImportSourceType.APPLE_HEALTH,
    name: 'Apple健康',
    icon: <HealthAndSafetyIcon fontSize="large" />,
    description: '从Apple健康应用导入数据',
    supported: true,
  },
  {
    id: ImportSourceType.GOOGLE_FIT,
    name: 'Google Fit',
    icon: <HealthAndSafetyIcon fontSize="large" />,
    description: '从Google Fit应用导入数据',
    supported: true,
  },
  {
    id: ImportSourceType.FITBIT,
    name: 'Fitbit',
    icon: <DevicesIcon fontSize="large" />,
    description: '从Fitbit设备导入数据',
    supported: true,
  },
  {
    id: ImportSourceType.WITHINGS,
    name: 'Withings',
    icon: <DevicesIcon fontSize="large" />,
    description: '从Withings设备导入数据',
    supported: false,
  },
  {
    id: ImportSourceType.GARMIN,
    name: 'Garmin',
    icon: <DevicesIcon fontSize="large" />,
    description: '从Garmin设备导入数据',
    supported: false,
  },
  {
    id: ImportSourceType.CUSTOM_DEVICE,
    name: '自定义设备',
    icon: <CableIcon fontSize="large" />,
    description: '配置自定义设备导入',
    supported: true,
  },
];

// 健康数据导入组件
const HealthDataImportModal: React.FC<HealthDataImportModalProps> = ({
  open,
  onClose,
  onImportComplete,
  patientId
}) => {
  // 当前步骤
  const [activeStep, setActiveStep] = useState(0);
  // 当前标签页
  const [tabValue, setTabValue] = useState(0);
  // 选择的导入源
  const [selectedSource, setSelectedSource] = useState<ImportSourceType | null>(null);
  // 上传的文件
  const [file, setFile] = useState<File | null>(null);
  // 导入进度
  const [importing, setImporting] = useState(false);
  // 导入错误
  const [importError, setImportError] = useState<string | null>(null);
  // 预览数据
  const [previewData, setPreviewData] = useState<DataRow[]>([]);
  // 验证结果
  const [validationResults, setValidationResults] = useState<{
    valid: boolean;
    errors: { row: number; message: string }[];
  }>({
    valid: true,
    errors: []
  });
  // 导入的数据
  const [importedData, setImportedData] = useState<HealthDataRecord[]>([]);
  
  // 步骤定义
  const steps = ['选择导入源', '上传和验证数据', '映射字段', '确认导入'];

  // 处理标签页切换
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
    setSelectedSource(null);
  };

  // 处理文件选择
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      // 这里会进行文件读取和预览，但现在还未实现
      setActiveStep(1);
    }
  };

  // 处理设备选择
  const handleDeviceSelect = (sourceType: ImportSourceType) => {
    setSelectedSource(sourceType);
    // 对于设备导入，我们可以直接进入授权或连接步骤
    setActiveStep(1);
  };

  // 处理文件拖放
  const handleFileDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    
    const droppedFile = event.dataTransfer.files?.[0];
    if (droppedFile) {
      setFile(droppedFile);
      // 检查文件类型，确定导入源
      if (droppedFile.name.endsWith('.csv')) {
        setSelectedSource(ImportSourceType.CSV_FILE);
      } else if (droppedFile.name.endsWith('.xlsx') || droppedFile.name.endsWith('.xls')) {
        setSelectedSource(ImportSourceType.EXCEL_FILE);
      }
      setActiveStep(1);
    }
  };

  // 处理拖拽事件
  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  // 下载导入模板
  const handleDownloadTemplate = (templateUrl: string) => {
    window.open(templateUrl, '_blank');
  };
  
  // 返回上一步
  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
  };

  // 继续下一步
  const handleNext = () => {
    setActiveStep((prevStep) => prevStep + 1);
  };

  // 重置所有状态
  const handleReset = () => {
    setActiveStep(0);
    setTabValue(0);
    setSelectedSource(null);
    setFile(null);
    setImporting(false);
    setImportError(null);
    setPreviewData([]);
    setValidationResults({ valid: true, errors: [] });
    setImportedData([]);
  };

  // 处理关闭
  const handleCloseModal = () => {
    handleReset();
    onClose();
  };

  // 渲染选择导入源步骤
  const renderSelectSourceStep = () => {
    return (
      <Box>
        <Tabs value={tabValue} onChange={handleTabChange} centered>
          <Tab label="文件导入" />
          <Tab label="设备同步" />
        </Tabs>
        
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            {fileImportOptions.map((option) => (
              <Grid item xs={12} md={6} key={option.id}>
                <DeviceOption 
                  className={selectedSource === option.id ? 'selected' : ''}
                  onClick={() => setSelectedSource(option.id)}
                >
                  <DeviceIconWrapper>
                    {option.icon}
                  </DeviceIconWrapper>
                  <Typography variant="h6" align="center">{option.name}</Typography>
                  <Typography variant="body2" color="text.secondary" align="center">
                    {option.description}
                  </Typography>
                  <Box mt={2}>
                    <Typography variant="caption" display="block" gutterBottom>
                      支持的格式: {option.supportedExtensions.join(', ')}
                    </Typography>
                  </Box>
                  {option.templateUrl && (
                    <Button 
                      size="small" 
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownloadTemplate(option.templateUrl!);
                      }}
                    >
                      下载模板
                    </Button>
                  )}
                </DeviceOption>
              </Grid>
            ))}
          </Grid>
          
          <Box mt={4}>
            <UploadArea
              onDrop={handleFileDrop}
              onDragOver={handleDragOver}
              onClick={() => document.getElementById('file-upload-input')?.click()}
            >
              <input
                id="file-upload-input"
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={handleFileSelect}
                style={{ display: 'none' }}
              />
              <FileUploadIcon fontSize="large" color="primary" />
              <Typography variant="h6" align="center" gutterBottom>
                拖放文件到这里或点击上传
              </Typography>
              <Typography variant="body2" color="text.secondary" align="center">
                支持的格式: .csv, .xlsx, .xls
              </Typography>
            </UploadArea>
          </Box>
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          <Grid container spacing={3}>
            {deviceImportOptions.map((option) => (
              <Grid item xs={12} sm={6} md={4} key={option.id}>
                <DeviceOption 
                  className={selectedSource === option.id ? 'selected' : ''}
                  onClick={() => option.supported && handleDeviceSelect(option.id)}
                  sx={{ opacity: option.supported ? 1 : 0.5 }}
                >
                  <DeviceIconWrapper>
                    {option.icon}
                  </DeviceIconWrapper>
                  <Typography variant="h6" align="center">{option.name}</Typography>
                  <Typography variant="body2" color="text.secondary" align="center">
                    {option.description}
                  </Typography>
                  {!option.supported && (
                    <Chip 
                      label="即将支持" 
                      color="warning" 
                      size="small" 
                      sx={{ mt: 1 }} 
                    />
                  )}
                </DeviceOption>
              </Grid>
            ))}
          </Grid>
        </TabPanel>
      </Box>
    );
  };

  // 渲染上传和验证步骤
  const renderUploadAndValidateStep = () => {
    // 这里将在下一部分代码中实现文件解析和预览功能
    return (
      <Box>
        <Typography variant="h6" gutterBottom>
          数据验证
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          请稍候，正在处理您的数据...在这个步骤中，我们将验证数据格式并准备导入预览。
        </Alert>
        <Box display="flex" justifyContent="center" alignItems="center" sx={{ py: 4 }}>
          <CircularProgress />
        </Box>
      </Box>
    );
  };

  // 渲染字段映射步骤
  const renderFieldMappingStep = () => {
    // 这里将在下一部分代码中实现字段映射功能
    return (
      <Box>
        <Typography variant="h6" gutterBottom>
          字段映射
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          请将导入文件的字段与系统字段进行映射。这将帮助系统正确解析您的数据。
        </Alert>
      </Box>
    );
  };

  // 渲染确认导入步骤
  const renderConfirmImportStep = () => {
    // 这里将在下一部分代码中实现确认导入功能
    return (
      <Box>
        <Typography variant="h6" gutterBottom>
          确认导入
        </Typography>
        <Alert severity="info" sx={{ mb: 2 }}>
          请确认以下数据正确无误。点击"完成导入"按钮将数据导入系统。
        </Alert>
      </Box>
    );
  };

  // 渲染完成导入步骤
  const renderCompleteImportStep = () => {
    return (
      <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" sx={{ py: 4 }}>
        <CheckCircleIcon color="success" sx={{ fontSize: 64, mb: 2 }} />
        <Typography variant="h5" gutterBottom>
          导入完成！
        </Typography>
        <Typography variant="body1" align="center" paragraph>
          成功导入了 {importedData.length} 条健康数据记录。
        </Typography>
        <Button variant="contained" color="primary" onClick={handleCloseModal}>
          关闭
        </Button>
      </Box>
    );
  };

  // 根据当前步骤渲染内容
  const renderStepContent = () => {
    switch (activeStep) {
      case 0:
        return renderSelectSourceStep();
      case 1:
        return renderUploadAndValidateStep();
      case 2:
        return renderFieldMappingStep();
      case 3:
        return renderConfirmImportStep();
      case 4:
        return renderCompleteImportStep();
      default:
        return null;
    }
  };

  return (
    <Dialog
      open={open}
      onClose={handleCloseModal}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { height: 'calc(100% - 64px)', maxHeight: 700 }
      }}
    >
      <DialogTitle>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">健康数据导入</Typography>
          <IconButton onClick={handleCloseModal} size="small">
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      
      <DialogContent dividers>
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        
        {importError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {importError}
          </Alert>
        )}
        
        {renderStepContent()}
      </DialogContent>
      
      <DialogActions>
        <Button onClick={handleCloseModal}>取消</Button>
        {activeStep > 0 && activeStep < 4 && (
          <Button onClick={handleBack}>上一步</Button>
        )}
        {activeStep < 3 && (
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleNext}
            disabled={!selectedSource || 
              (activeStep === 0 && tabValue === 0 && !file) ||
              importing}
          >
            下一步
          </Button>
        )}
        {activeStep === 3 && (
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleNext}
            disabled={importing}
          >
            完成导入
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default HealthDataImportModal; 