import React from 'react';
import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Chip,
  Tooltip,
  CircularProgress,
  Divider
} from '@mui/material';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import HistoryIcon from '@mui/icons-material/History';
import VisibilityIcon from '@mui/icons-material/Visibility';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import RestorePageIcon from '@mui/icons-material/RestorePage';
import { format } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface RecordVersion {
  version_number: number;
  content: any;
  created_by: string;
  created_at: string;
  change_description?: string;
}

interface VersionHistoryComponentProps {
  recordId: string;
  versions: RecordVersion[];
  loading?: boolean;
  error?: string;
  onViewVersion: (versionNumber: number) => void;
  onCompareVersions?: (versionNumber1: number, versionNumber2: number) => void;
  onRestoreVersion?: (versionNumber: number) => void;
}

const VersionHistoryComponent: React.FC<VersionHistoryComponentProps> = ({
  recordId,
  versions,
  loading = false,
  error,
  onViewVersion,
  onCompareVersions,
  onRestoreVersion
}) => {
  const [open, setOpen] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<RecordVersion | null>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [versionToCompare, setVersionToCompare] = useState<number | null>(null);
  
  // 格式化日期
  const formatDate = (dateString: string) => {
    try {
      return format(new Date(dateString), 'yyyy年MM月dd日 HH:mm', { locale: zhCN });
    } catch (e) {
      return dateString;
    }
  };
  
  const handleOpen = () => {
    setOpen(true);
  };
  
  const handleClose = () => {
    setOpen(false);
    setCompareMode(false);
    setVersionToCompare(null);
  };
  
  const handleViewVersion = (versionNumber: number) => {
    if (compareMode && versionToCompare !== null && versionToCompare !== versionNumber) {
      // 在比较模式下选择了第二个版本，触发比较
      if (onCompareVersions) {
        onCompareVersions(versionToCompare, versionNumber);
      }
      setCompareMode(false);
      setVersionToCompare(null);
    } else if (compareMode) {
      // 在比较模式下选择了同一个版本，切换选择
      setVersionToCompare(versionNumber);
    } else {
      // 正常模式下查看版本
      onViewVersion(versionNumber);
      handleClose();
    }
  };
  
  const handleEnterCompareMode = () => {
    setCompareMode(true);
    setVersionToCompare(null);
  };
  
  const handleCancelCompareMode = () => {
    setCompareMode(false);
    setVersionToCompare(null);
  };
  
  const handleRestoreVersion = (versionNumber: number) => {
    if (onRestoreVersion) {
      onRestoreVersion(versionNumber);
      handleClose();
    }
  };
  
  const sortedVersions = [...versions].sort((a, b) => b.version_number - a.version_number);
  
  return (
    <>
      <IconButton onClick={handleOpen} color="primary" title="查看版本历史">
        <HistoryIcon />
      </IconButton>
      
      <Dialog 
        open={open} 
        onClose={handleClose}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">版本历史</Typography>
            {!compareMode ? (
              <Button 
                startIcon={<CompareArrowsIcon />} 
                onClick={handleEnterCompareMode}
                disabled={versions.length < 2}
              >
                比较版本
              </Button>
            ) : (
              <Button 
                color="secondary" 
                onClick={handleCancelCompareMode}
              >
                取消比较
              </Button>
            )}
          </Box>
        </DialogTitle>
        
        <DialogContent>
          {loading ? (
            <Box display="flex" justifyContent="center" my={3}>
              <CircularProgress />
            </Box>
          ) : error ? (
            <Typography color="error">{error}</Typography>
          ) : (
            <>
              {compareMode && (
                <Box mb={2} p={2} bgcolor="background.default" borderRadius={1}>
                  <Typography variant="body2">
                    {versionToCompare === null 
                      ? "请选择第一个要比较的版本" 
                      : `已选择版本 ${versionToCompare}，请选择另一个版本进行比较`}
                  </Typography>
                </Box>
              )}
              
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ width: '10%' }}>版本号</TableCell>
                      <TableCell sx={{ width: '20%' }}>修改时间</TableCell>
                      <TableCell sx={{ width: '20%' }}>修改人</TableCell>
                      <TableCell sx={{ width: '30%' }}>修改说明</TableCell>
                      <TableCell sx={{ width: '20%' }}>操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sortedVersions.map((version) => (
                      <TableRow 
                        key={version.version_number}
                        selected={compareMode && versionToCompare === version.version_number}
                      >
                        <TableCell>
                          <Chip 
                            label={`v${version.version_number}`}
                            color={version.version_number === Math.max(...versions.map(v => v.version_number)) ? "primary" : "default"}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>{formatDate(version.created_at)}</TableCell>
                        <TableCell>{version.created_by}</TableCell>
                        <TableCell>{version.change_description || '无修改说明'}</TableCell>
                        <TableCell>
                          <Tooltip title="查看此版本">
                            <IconButton 
                              size="small" 
                              onClick={() => handleViewVersion(version.version_number)}
                              color={compareMode && versionToCompare === version.version_number ? "primary" : "default"}
                            >
                              <VisibilityIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          
                          {onRestoreVersion && version.version_number !== Math.max(...versions.map(v => v.version_number)) && (
                            <Tooltip title="恢复到此版本">
                              <IconButton 
                                size="small"
                                onClick={() => handleRestoreVersion(version.version_number)}
                              >
                                <RestorePageIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              
              {versions.length === 0 && (
                <Box textAlign="center" my={3}>
                  <Typography color="textSecondary">暂无版本历史记录</Typography>
                </Box>
              )}
            </>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={handleClose} color="primary">
            关闭
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default VersionHistoryComponent; 