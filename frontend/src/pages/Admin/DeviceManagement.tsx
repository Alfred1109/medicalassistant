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
import apiClient from '../../services/api';

// 设备管理：数据来自真实接口 GET /api/devices（admin 在设备读取角色白名单内）
// 设备生命周期由绑定/解绑流程管理，后端不存在管理员侧设备增删接口，故不提供添加/删除入口
// 字段对齐后端 DeviceResponse（device_router.py）
interface DeviceRow {
  id: string;
  device_type: string;
  name: string;
  manufacturer?: string | null;
  model?: string | null;
  connection_type?: string | null;
  patient_id?: string | null;
  status: string;
  last_connected?: string | null;
  battery_level?: number | null;
}

const DeviceManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [devices, setDevices] = useState<DeviceRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const fetchDevices = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get('/devices');
        if (!cancelled) {
          setDevices(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取设备数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取设备数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchDevices();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 客户端关键词搜索（名称/类型/型号）
  const filteredDevices = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) {
      return devices;
    }
    return devices.filter(device =>
      [device.name, device.device_type, device.model]
        .filter(Boolean)
        .some(field => String(field).toLowerCase().includes(keyword))
    );
  }, [devices, searchTerm]);

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
  };

  const renderText = (value: unknown) => {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    return String(value);
  };

  const formatDateTime = (value?: string | null) => {
    if (!value) {
      return '—';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return date.toLocaleString();
  };

  const getStatusColor = (status: string): any => {
    switch (status) {
      case 'online':
      case 'active':
      case '正常':
        return 'success';
      case 'offline':
      case 'inactive':
      case '离线':
        return 'default';
      case 'error':
      case 'fault':
      case '故障':
        return 'error';
      case 'maintenance':
      case '维修中':
        return 'warning';
      default:
        return 'default';
    }
  };

  // 加载中
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <CircularProgress />
        <Typography variant="body1" sx={{ ml: 2 }}>
          设备数据加载中...
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
          设备管理
        </Typography>
        <Typography variant="caption" color="text.secondary">
          设备通过患者端绑定/解绑流程管理，后端无管理员侧设备增删接口
        </Typography>
      </Box>

      <Box mb={3}>
        <TextField
          placeholder="搜索设备名称、类型或型号..."
          variant="outlined"
          size="small"
          value={searchTerm}
          onChange={handleSearchChange}
          sx={{ width: 320 }}
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
              <TableCell>设备名称</TableCell>
              <TableCell>类型</TableCell>
              <TableCell>型号</TableCell>
              <TableCell>制造商</TableCell>
              <TableCell>绑定患者</TableCell>
              <TableCell>电量</TableCell>
              <TableCell>最后连接时间</TableCell>
              <TableCell>状态</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredDevices.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8}>
                  <Box sx={{ p: 4, textAlign: 'center' }}>
                    <Typography variant="body1" color="text.secondary">
                      暂无设备数据
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filteredDevices.map(device => (
                <TableRow key={device.id}>
                  <TableCell>{renderText(device.name)}</TableCell>
                  <TableCell>{renderText(device.device_type)}</TableCell>
                  <TableCell>{renderText(device.model)}</TableCell>
                  <TableCell>{renderText(device.manufacturer)}</TableCell>
                  <TableCell>{device.patient_id ? device.patient_id : '未绑定'}</TableCell>
                  <TableCell>
                    {device.battery_level !== null && device.battery_level !== undefined
                      ? `${device.battery_level}%`
                      : '—'}
                  </TableCell>
                  <TableCell>{formatDateTime(device.last_connected)}</TableCell>
                  <TableCell>
                    <Chip
                      label={device.status || '未知'}
                      color={getStatusColor(device.status)}
                      size="small"
                    />
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

export default DeviceManagement;
