import React, { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Divider,
  Grid,
  Chip,
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab,
  Menu,
  MenuItem,
  Tooltip,
  CircularProgress,
  Alert
} from '@mui/material';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

// 图标
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import HistoryIcon from '@mui/icons-material/History';
import FileCopyIcon from '@mui/icons-material/FileCopy';
import PrintIcon from '@mui/icons-material/Print';
import ShareIcon from '@mui/icons-material/Share';
import AttachFileIcon from '@mui/icons-material/AttachFile';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';

// 标签页内容容器
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`health-record-tab-${index}`}
      aria-labelledby={`health-record-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// 记录类型映射
const recordTypeMap: { [key: string]: string } = {
  medical_record: '门诊病历',
  admission_record: '入院记录',
  discharge_summary: '出院小结',
  surgery_record: '手术记录',
  examination_report: '检查报告',
  progress_note: '病程记录',
  consultation: '会诊意见',
  prescription: '处方',
  nursing_record: '护理记录',
  other: '其他'
};

// 可见性映射
const visibilityMap: { [key: string]: string } = {
  all: '所有人可见',
  doctor_only: '仅医生可见',
  patient_only: '仅患者可见',
  medical_staff: '医护人员可见'
};

interface Attachment {
  file_name: string;
  file_type: string;
  file_url: string;
  file_size?: number;
  description?: string;
  uploaded_at: string;
}

interface RecordVersion {
  version_number: number;
  content: any;
  created_by: string;
  created_at: string;
  change_description?: string;
}

interface HealthRecordData {
  id: string;
  patient_id: string;
  record_type: string;
  title: string;
  content: any;
  created_by: string;
  organization_id?: string;
  attachments: Attachment[];
  tags: string[];
  visibility: string;
  created_at: string;
  updated_at: string;
  versions?: RecordVersion[];
  metadata?: any;
}

interface HealthRecordDetailProps {
  record: HealthRecordData;
  loading?: boolean;
  error?: string;
  onEdit?: () => void;
  onDelete?: () => void;
  onBack?: () => void;
  onVersionView?: (versionNumber: number) => void;
  currentUser?: any;
}

const HealthRecordDetail: React.FC<HealthRecordDetailProps> = ({
  record,
  loading = false,
  error,
  onEdit,
  onDelete,
  onBack,
  onVersionView,
  currentUser
}) => {
  // 状态
  const [tabValue, setTabValue] = useState(0);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const menuOpen = Boolean(menuAnchorEl);
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  
  // 处理标签页变更
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };
  
  // 处理菜单打开
  const handleMenuClick = (event: React.MouseEvent<HTMLElement>) => {
    setMenuAnchorEl(event.currentTarget);
  };
  
  // 处理菜单关闭
  const handleMenuClose = () => {
    setMenuAnchorEl(null);
  };
  
  // 处理删除确认对话框
  const handleDeleteDialogOpen = () => {
    setDeleteDialogOpen(true);
    handleMenuClose();
  };
  
  const handleDeleteDialogClose = () => {
    setDeleteDialogOpen(false);
  };
  
  const handleConfirmDelete = () => {
    if (onDelete) {
      onDelete();
    }
    setDeleteDialogOpen(false);
  };
  
  // 处理版本历史对话框
  const handleHistoryDialogOpen = () => {
    setHistoryDialogOpen(true);
    handleMenuClose();
  };
  
  const handleHistoryDialogClose = () => {
    setHistoryDialogOpen(false);
  };
  
  const handleViewVersion = (versionNumber: number) => {
    if (onVersionView) {
      onVersionView(versionNumber);
    }
    setHistoryDialogOpen(false);
  };
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return format(new Date(dateString), 'yyyy年MM月dd日 HH:mm', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };
  
  // 格式化文件大小
  const formatFileSize = (size?: number) => {
    if (!size) return '未知';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(2)} KB`;
    return `${(size / (1024 * 1024)).toFixed(2)} MB`;
  };
  
  // 检查当前用户是否可以编辑
  const canEdit = () => {
    if (!currentUser) return false;
    
    // 医生和健康管理师可以编辑
    return ['doctor', 'health_manager'].includes(currentUser.user_type) || 
           currentUser.id === record.created_by;
  };
  
  // 渲染内容字段
  const renderContentFields = () => {
    if (!record.content) return null;
    
    return Object.entries(record.content).map(([key, value]) => {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      
      // 处理日期字段
      if (key.includes('date') && typeof value === 'string' && value.includes('-')) {
        value = formatDate(value as string);
      }
      
      return (
        <Grid item xs={12} md={key.includes('notes') || key.includes('details') ? 12 : 6} key={key}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            {label}
          </Typography>
          <Typography variant="body1" paragraph>
            {value as React.ReactNode}
          </Typography>
        </Grid>
      );
    });
  };
  
  // 如果正在加载或出错
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height={400}>
        <CircularProgress />
      </Box>
    );
  }
  
  if (error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }
  
  if (!record) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        未找到健康档案
      </Alert>
    );
  }
  
  return (
    <Paper elevation={2}>
      <Box p={3}>
        {/* 标题栏 */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center">
            {onBack && (
              <IconButton onClick={onBack} sx={{ mr: 1 }}>
                <ArrowBackIcon />
              </IconButton>
            )}
            <Typography variant="h5" component="h2">
              {record.title}
            </Typography>
          </Box>
          <Box>
            {canEdit() && (
              <Box display="flex">
                <Button 
                  startIcon={<EditIcon />} 
                  onClick={onEdit}
                  variant="outlined"
                  sx={{ mr: 1 }}
                >
                  编辑
                </Button>
                <IconButton
                  onClick={handleMenuClick}
                  size="small"
                >
                  <MoreVertIcon />
                </IconButton>
                <Menu
                  anchorEl={menuAnchorEl}
                  open={menuOpen}
                  onClose={handleMenuClose}
                >
                  <MenuItem onClick={handleHistoryDialogOpen}>
                    <HistoryIcon fontSize="small" sx={{ mr: 1 }} />
                    查看版本历史
                  </MenuItem>
                  <MenuItem onClick={() => {handleMenuClose(); if (onEdit) onEdit();}}>
                    <FileCopyIcon fontSize="small" sx={{ mr: 1 }} />
                    复制为新记录
                  </MenuItem>
                  <MenuItem onClick={() => {handleMenuClose();}}>
                    <PrintIcon fontSize="small" sx={{ mr: 1 }} />
                    打印
                  </MenuItem>
                  <MenuItem onClick={() => {handleMenuClose();}}>
                    <ShareIcon fontSize="small" sx={{ mr: 1 }} />
                    分享
                  </MenuItem>
                  <Divider />
                  <MenuItem onClick={handleDeleteDialogOpen} sx={{ color: 'error.main' }}>
                    <DeleteIcon fontSize="small" sx={{ mr: 1 }} />
                    删除
                  </MenuItem>
                </Menu>
              </Box>
            )}
          </Box>
        </Box>
        
        {/* 基本信息卡片 */}
        <Box mb={3}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  记录类型
                </Typography>
                <Chip 
                  label={recordTypeMap[record.record_type] || record.record_type} 
                  color="primary" 
                  size="small" 
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  创建时间
                </Typography>
                <Typography variant="body2">
                  {formatDate(record.created_at)}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  最后更新
                </Typography>
                <Typography variant="body2">
                  {formatDate(record.updated_at)}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  可见性
                </Typography>
                <Chip 
                  label={visibilityMap[record.visibility] || record.visibility} 
                  color="secondary" 
                  size="small" 
                  variant="outlined"
                />
              </Grid>
            </Grid>
          </Paper>
        </Box>
        
        {/* 标签 */}
        {record.tags && record.tags.length > 0 && (
          <Box mb={3}>
            <Typography variant="subtitle2" gutterBottom>
              标签
            </Typography>
            <Box>
              {record.tags.map((tag, index) => (
                <Chip 
                  key={index} 
                  label={tag} 
                  sx={{ m: 0.5 }} 
                  size="small" 
                  color="default"
                />
              ))}
            </Box>
          </Box>
        )}
        
        {/* 内容标签页 */}
        <Box mt={3}>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            indicatorColor="primary"
            textColor="primary"
            aria-label="健康档案标签页"
          >
            <Tab label="内容详情" />
            {record.attachments && record.attachments.length > 0 && (
              <Tab label={`附件 (${record.attachments.length})`} />
            )}
          </Tabs>
          
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              {renderContentFields()}
            </Grid>
          </TabPanel>
          
          {record.attachments && record.attachments.length > 0 && (
            <TabPanel value={tabValue} index={1}>
              <TableContainer>
                <Table aria-label="附件列表">
                  <TableHead>
                    <TableRow>
                      <TableCell>文件名</TableCell>
                      <TableCell>类型</TableCell>
                      <TableCell>大小</TableCell>
                      <TableCell>上传时间</TableCell>
                      <TableCell>操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {record.attachments.map((attachment, index) => (
                      <TableRow key={index}>
                        <TableCell>
                          <Box display="flex" alignItems="center">
                            <AttachFileIcon fontSize="small" sx={{ mr: 1 }} />
                            {attachment.description ? (
                              <Tooltip title={attachment.description}>
                                <Typography>{attachment.file_name}</Typography>
                              </Tooltip>
                            ) : (
                              <Typography>{attachment.file_name}</Typography>
                            )}
                          </Box>
                        </TableCell>
                        <TableCell>{attachment.file_type}</TableCell>
                        <TableCell>{formatFileSize(attachment.file_size)}</TableCell>
                        <TableCell>{formatDate(attachment.uploaded_at)}</TableCell>
                        <TableCell>
                          <IconButton 
                            size="small" 
                            component="a" 
                            href={attachment.file_url} 
                            target="_blank" 
                            download
                          >
                            <CloudDownloadIcon fontSize="small" />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </TabPanel>
          )}
        </Box>
      </Box>
      
      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={handleDeleteDialogClose}
      >
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>
            您确定要删除这条健康档案记录吗？此操作不可撤销。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleDeleteDialogClose}>取消</Button>
          <Button onClick={handleConfirmDelete} color="error" autoFocus>
            删除
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* 版本历史对话框 */}
      <Dialog
        open={historyDialogOpen}
        onClose={handleHistoryDialogClose}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>版本历史</DialogTitle>
        <DialogContent>
          {record.versions && record.versions.length > 0 ? (
            <TableContainer>
              <Table aria-label="版本历史">
                <TableHead>
                  <TableRow>
                    <TableCell>版本</TableCell>
                    <TableCell>修改说明</TableCell>
                    <TableCell>修改人</TableCell>
                    <TableCell>修改时间</TableCell>
                    <TableCell>操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {/* 当前版本 */}
                  <TableRow sx={{ bgcolor: 'action.hover' }}>
                    <TableCell>当前版本</TableCell>
                    <TableCell>-</TableCell>
                    <TableCell>{record.created_by}</TableCell>
                    <TableCell>{formatDate(record.updated_at)}</TableCell>
                    <TableCell>
                      <Button size="small" disabled>
                        当前查看
                      </Button>
                    </TableCell>
                  </TableRow>
                  {/* 历史版本 */}
                  {record.versions.map((version) => (
                    <TableRow key={version.version_number}>
                      <TableCell>版本 {version.version_number}</TableCell>
                      <TableCell>{version.change_description || '-'}</TableCell>
                      <TableCell>{version.created_by}</TableCell>
                      <TableCell>{formatDate(version.created_at)}</TableCell>
                      <TableCell>
                        <Button 
                          size="small" 
                          onClick={() => handleViewVersion(version.version_number)}
                        >
                          查看
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Typography align="center" color="text.secondary" py={3}>
              暂无版本历史记录
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleHistoryDialogClose}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default HealthRecordDetail; 