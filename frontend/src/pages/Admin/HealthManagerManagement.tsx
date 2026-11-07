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
  MenuItem,
  CircularProgress,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import apiClient from '../../services/api';

// 健康管理师管理：数据来自 GET /api/admin/health-managers
// 该接口目前为后端占位实现（恒返回 []），创建/编辑/删除接口未持久化，故禁用相关入口
interface HealthManagerRow {
  id?: string;
  name?: string;
  department?: string;
  title?: string;
  specialty?: string;
  email?: string;
  phone?: string;
  patients?: number;
  status?: string;
  join_date?: string;
}

const HealthManagerManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [managers, setManagers] = useState<HealthManagerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('全部');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const fetchManagers = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get('/admin/health-managers');
        if (!cancelled) {
          setManagers(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取健康管理师数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取健康管理师数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchManagers();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 科室筛选选项从真实数据中提取
  const departmentOptions = useMemo(() => {
    const deps = Array.from(new Set(managers.map(m => m.department).filter(Boolean)));
    return ['全部', ...deps];
  }, [managers]);

  // 客户端筛选：科室 + 关键词搜索
  const filteredManagers = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return managers.filter(manager => {
      if (filterDepartment !== '全部' && manager.department !== filterDepartment) {
        return false;
      }
      if (keyword) {
        const haystack = [manager.name, manager.department, manager.specialty, manager.title]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(keyword)) {
          return false;
        }
      }
      return true;
    });
  }, [managers, filterDepartment, searchTerm]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const handleFilterDepartmentChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilterDepartment(event.target.value);
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
          健康管理师数据加载中...
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
          健康管理师管理
        </Typography>
        <Box textAlign="right">
          <Button variant="contained" color="primary" startIcon={<AddIcon />} disabled>
            添加健康管理师
          </Button>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            后端健康管理师创建/编辑/删除接口尚未实现持久化，功能待开放
          </Typography>
        </Box>
      </Box>

      <Box mb={3} display="flex" alignItems="center">
        <TextField
          fullWidth
          placeholder="搜索管理师姓名、科室或专长..."
          variant="outlined"
          value={searchTerm}
          onChange={handleSearchChange}
          sx={{ mr: 2 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
        <TextField
          select
          label="科室"
          variant="outlined"
          value={filterDepartment}
          onChange={handleFilterDepartmentChange}
          sx={{ minWidth: 140 }}
        >
          {departmentOptions.map((dept) => (
            <MenuItem key={dept} value={dept}>{dept}</MenuItem>
          ))}
        </TextField>
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>姓名</TableCell>
              <TableCell>科室</TableCell>
              <TableCell>职称</TableCell>
              <TableCell>专长</TableCell>
              <TableCell>联系方式</TableCell>
              <TableCell>管理患者数</TableCell>
              <TableCell>状态</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredManagers.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Box sx={{ p: 4, textAlign: 'center' }}>
                    <Typography variant="body1" color="text.secondary">
                      暂无健康管理师数据
                    </Typography>
                    <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
                      后端管理接口建设中，暂无数据
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filteredManagers.map((manager, index) => (
                <TableRow key={manager.id || `manager-${index}`}>
                  <TableCell>{renderText(manager.name)}</TableCell>
                  <TableCell>{renderText(manager.department)}</TableCell>
                  <TableCell>{renderText(manager.title)}</TableCell>
                  <TableCell>{renderText(manager.specialty)}</TableCell>
                  <TableCell>
                    <Typography variant="body2" color="text.secondary">
                      {renderText(manager.phone)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {renderText(manager.email)}
                    </Typography>
                  </TableCell>
                  <TableCell>{manager.patients ?? '暂无'}</TableCell>
                  <TableCell>
                    {manager.status ? (
                      <Chip label={manager.status} size="small" />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default HealthManagerManagement;
