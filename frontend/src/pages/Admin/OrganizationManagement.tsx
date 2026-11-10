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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import apiClient from '../../services/api';

// 组织机构管理：数据来自 GET /api/admin/organizations
// 该接口目前为后端占位实现（恒返回 []），创建/编辑/删除接口未持久化，故禁用相关入口
// 原页面的组织结构树为纯前端假数据，已随本轮改造一并移除
interface OrganizationRow {
  id?: string;
  name?: string;
  type?: string;
  address?: string;
  contact_person?: string;
  contact_phone?: string;
  status?: string;
}

const OrganizationManagement: React.FC = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [organizations, setOrganizations] = useState<OrganizationRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [orgName, setOrgName] = useState('');

  useEffect(() => {
    let cancelled = false;

    const fetchOrganizations = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await apiClient.get('/admin/organizations');
        if (!cancelled) {
          setOrganizations(Array.isArray(response.data) ? response.data : []);
        }
      } catch (err: any) {
        if (!cancelled) {
          const errorMessage = err.response
            ? `获取组织机构数据失败: ${err.response.status} ${err.response.statusText || ''}${err.response.data?.detail ? ` (${err.response.data.detail})` : ''}`
            : `获取组织机构数据失败: ${err.message || '未知错误'}`;
          setError(errorMessage);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchOrganizations();
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  // 客户端关键词搜索
  const filteredOrganizations = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) {
      return organizations;
    }
    return organizations.filter(org =>
      [org.name, org.type, org.address, org.contact_person]
        .filter(Boolean)
        .some(field => String(field).toLowerCase().includes(keyword))
    );
  }, [organizations, searchTerm]);

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
  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="300px">
        <CircularProgress />
        <Typography variant="body1" sx={{ ml: 2 }}>
          组织机构数据加载中...
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
        <Typography variant="h5" component="h2">
          组织机构管理
        </Typography>
        <Box textAlign="right">
          <Button variant="contained" color="primary" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            添加机构
          </Button>
        </Box>
      </Box>

      <Box mb={3}>
        <TextField
          fullWidth
          placeholder="搜索机构名称或类型..."
          variant="outlined"
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
      </Box>

      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>机构名称</TableCell>
              <TableCell>类型</TableCell>
              <TableCell>地址</TableCell>
              <TableCell>联系人</TableCell>
              <TableCell>联系电话</TableCell>
              <TableCell>状态</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredOrganizations.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6}>
                  <Box sx={{ p: 4, textAlign: 'center' }}>
                    <Typography variant="body1" color="text.secondary">
                      暂无组织机构数据
                    </Typography>
                    <Typography variant="caption" color="text.disabled" display="block" sx={{ mt: 1 }}>
                      后端管理接口建设中，暂无数据
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filteredOrganizations.map((org, index) => (
                <TableRow key={org.id || `org-${index}`}>
                  <TableCell>{renderText(org.name)}</TableCell>
                  <TableCell>{renderText(org.type)}</TableCell>
                  <TableCell>{renderText(org.address)}</TableCell>
                  <TableCell>{renderText(org.contact_person)}</TableCell>
                  <TableCell>{renderText(org.contact_phone)}</TableCell>
                  <TableCell>
                    {org.status ? (
                      <Chip
                        label={org.status}
                        color={org.status === '正常' ? 'success' : 'default'}
                        size="small"
                      />
                    ) : (
                      '—'
                    )}
                    <Button size="small" onClick={async () => {
                      await apiClient.put(`/admin/organizations/${org.id}/active`, { active: org.status !== 'active' });
                      setReloadKey(key => key + 1);
                    }}>{org.status === 'active' ? '停用' : '恢复'}</Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)}>
        <DialogTitle>添加机构</DialogTitle>
        <DialogContent>
          <TextField fullWidth label="机构名称" value={orgName} onChange={event => setOrgName(event.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>取消</Button>
          <Button variant="contained" onClick={async () => {
            await apiClient.post('/admin/organizations', { name: orgName.trim(), type: 'hospital' });
            setOrgName(''); setCreateOpen(false); setReloadKey(key => key + 1);
          }}>保存</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default OrganizationManagement;
