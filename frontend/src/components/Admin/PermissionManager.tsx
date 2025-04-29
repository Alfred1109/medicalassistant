// @ts-nocheck
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Checkbox,
  Button,
  IconButton,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Tabs,
  Tab,
  Tooltip,
  Alert,
  Snackbar,
  LinearProgress,
  InputAdornment,
  List,
  ListItem,
  ListItemButton,
  ListItemAvatar,
  ListItemText,
  FormGroup,
  FormControlLabel,
  Avatar
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Search as SearchIcon,
  FilterList as FilterListIcon,
  Refresh as RefreshIcon,
  Save as SaveIcon,
  ArrowUpward as ArrowUpwardIcon,
  ArrowDownward as ArrowDownwardIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import { styled } from '@mui/material/styles';
import { TabPanel } from '../common/TabPanel';

// 导入API服务
// import { permissionApi } from '../../services/permissionService';

// 资源类型
interface Resource {
  id: string;
  name: string;
  description: string;
  category: string;
}

// 权限类型
interface Permission {
  id: string;
  name: string;
  description: string;
  resourceId: string;
  action: 'read' | 'create' | 'update' | 'delete' | 'manage';
}

// 角色类型
interface Role {
  id: string;
  name: string;
  description: string;
  isSystem: boolean;
  createdAt: Date;
  updatedAt: Date;
}

// 角色权限映射类型
interface RolePermission {
  roleId: string;
  permissionId: string;
}

// 用户角色映射类型
interface UserRole {
  userId: string;
  roleId: string;
}

// 用户类型
interface User {
  id: string;
  username: string;
  fullName: string;
  email: string;
  department?: string;
  position?: string;
  roles: Role[];
}

// 表格列定义
interface Column {
  id: string;
  label: string;
  minWidth?: number;
  align?: 'right' | 'left' | 'center';
  format?: (value: any) => string;
}

// TabPanel 组件属性
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// 样式化的表格头部
const StyledTableHead = styled(TableHead)(({ theme }) => ({
  backgroundColor: theme.palette.primary.light,
  '& .MuiTableCell-head': {
    color: theme.palette.common.white,
    fontWeight: 'bold'
  }
}));

// TabPanel 组件
function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`permission-tabpanel-${index}`}
      aria-labelledby={`permission-tab-${index}`}
      style={{ width: '100%' }}
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

// a11y属性
function a11yProps(index: number) {
  return {
    id: `permission-tab-${index}`,
    'aria-controls': `permission-tabpanel-${index}`,
  };
}

/**
 * 权限管理组件
 * 提供角色和权限的完整管理界面
 */
const PermissionManager: React.FC = () => {
  // 状态管理
  const [tabIndex, setTabIndex] = useState(0);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notification, setNotification] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error' | 'info' | 'warning';
  }>({
    open: false,
    message: '',
    severity: 'info'
  });
  
  // 表格分页
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  
  // 添加新状态用于权限配置
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [rolePermissions, setRolePermissions] = useState<{[roleId: string]: string[]}>({});
  const [permissionMatrix, setPermissionMatrix] = useState<{[resourceId: string]: {[action: string]: boolean}}>({});
  const [resourceCategories, setResourceCategories] = useState<string[]>([]);
  
  // 添加新状态用于资源管理
  const [resourceDialog, setResourceDialog] = useState<{
    open: boolean;
    mode: 'create' | 'edit';
    resource: Resource;
  }>({
    open: false,
    mode: 'create',
    resource: {
      id: '',
      name: '',
      description: '',
      category: resourceCategories[0] || '系统'
    }
  });
  const [categoryDialog, setCategoryDialog] = useState(false);
  const [newCategory, setNewCategory] = useState('');
  const [filteredResources, setFilteredResources] = useState<Resource[]>([]);
  const [resourcePage, setResourcePage] = useState(0);
  
  // 添加新状态用于用户授权
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [filteredUsers, setFilteredUsers] = useState<User[]>([]);
  
  // 添加新状态用于确认对话框
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    title: string;
    message: string;
    confirmText?: string;
    confirmAction: () => void;
  }>({
    open: false,
    title: '',
    message: '',
    confirmAction: () => {}
  });
  
  // 处理分页变更
  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };
  
  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(+event.target.value);
    setPage(0);
  };
  
  // 处理Tab切换
  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabIndex(newValue);
  };
  
  // 加载初始数据
  useEffect(() => {
    // 后续实现，将调用API加载角色、权限等数据
    const loadInitialData = async () => {
      setLoading(true);
      try {
        // 模拟加载数据
        console.log('正在加载初始数据...');
        // 实际使用时替换为API调用
        // const rolesData = await permissionApi.getRoles();
        // const permissionsData = await permissionApi.getPermissions();
        // const resourcesData = await permissionApi.getResources();
        // const usersData = await permissionApi.getUsers();
        
        // 模拟数据
        const mockRoles: Role[] = [
          {
            id: '1',
            name: '系统管理员',
            description: '拥有系统所有权限',
            isSystem: true,
            createdAt: new Date(),
            updatedAt: new Date()
          },
          {
            id: '2',
            name: '医生',
            description: '医生角色，可以查看和管理患者数据',
            isSystem: true,
            createdAt: new Date(),
            updatedAt: new Date()
          },
          {
            id: '3',
            name: '患者',
            description: '患者角色，只能查看自己的数据',
            isSystem: true,
            createdAt: new Date(),
            updatedAt: new Date()
          },
          {
            id: '4',
            name: '健康管理师',
            description: '健康管理师角色，可以查看患者数据并制定康复计划',
            isSystem: true,
            createdAt: new Date(),
            updatedAt: new Date()
          }
        ];
        
        setRoles(mockRoles);
        setPermissions([]);
        setResources([]);
        setUsers([]);
        
      } catch (err) {
        setError('加载数据失败，请重试。');
        setNotification({
          open: true,
          message: '加载数据失败，请重试。',
          severity: 'error'
        });
      } finally {
        setLoading(false);
      }
    };
    
    loadInitialData();
  }, []);
  
  // 关闭通知
  const handleCloseNotification = () => {
    setNotification({
      ...notification,
      open: false
    });
  };
  
  // 对资源按类别分组
  const resourcesByCategory = useCallback(() => {
    const grouped: {[category: string]: Resource[]} = {};
    resources.forEach(resource => {
      if (!grouped[resource.category]) {
        grouped[resource.category] = [];
      }
      grouped[resource.category].push(resource);
    });
    return grouped;
  }, [resources]);
  
  // 添加模拟权限和资源数据
  useEffect(() => {
    // 模拟资源数据
    const mockResources: Resource[] = [
      {
        id: 'health_record',
        name: '健康档案',
        description: '患者健康档案管理',
        category: '患者数据'
      },
      {
        id: 'rehab_plan',
        name: '康复计划',
        description: '康复计划管理',
        category: '患者数据'
      },
      {
        id: 'health_data',
        name: '健康数据',
        description: '健康数据监测',
        category: '患者数据'
      },
      {
        id: 'user_management',
        name: '用户管理',
        description: '用户账户管理',
        category: '系统管理'
      },
      {
        id: 'role_management',
        name: '角色管理',
        description: '角色权限管理',
        category: '系统管理'
      },
      {
        id: 'system_settings',
        name: '系统设置',
        description: '系统参数配置',
        category: '系统管理'
      },
      {
        id: 'chat',
        name: '聊天功能',
        description: '医患沟通功能',
        category: '通信功能'
      },
      {
        id: 'notification',
        name: '通知功能',
        description: '系统通知功能',
        category: '通信功能'
      }
    ];
    
    // 模拟权限数据
    const mockPermissions: Permission[] = [];
    const actions = ['read', 'create', 'update', 'delete', 'manage'];
    
    mockResources.forEach(resource => {
      actions.forEach(action => {
        mockPermissions.push({
          id: `${resource.id}_${action}`,
          name: `${action.charAt(0).toUpperCase() + action.slice(1)} ${resource.name}`,
          description: `${getActionDescription(action as any)} ${resource.name}`,
          resourceId: resource.id,
          action: action as any
        });
      });
    });
    
    // 获取所有资源类别
    const categories = Array.from(new Set(mockResources.map(r => r.category)));
    
    // 设置模拟数据
    setResources(mockResources);
    setPermissions(mockPermissions);
    setResourceCategories(categories);
    
    // 模拟角色权限数据
    const mockRolePermissions: {[roleId: string]: string[]} = {
      '1': mockPermissions.map(p => p.id), // 系统管理员拥有所有权限
      '2': mockPermissions.filter(p => 
        (p.resourceId.includes('health_record') || 
         p.resourceId.includes('rehab_plan') || 
         p.resourceId.includes('health_data') ||
         p.resourceId.includes('chat') ||
         p.resourceId.includes('notification')) && 
        (p.action === 'read' || p.action === 'create' || p.action === 'update')
      ).map(p => p.id), // 医生有患者数据和通信的读写权限
      '3': mockPermissions.filter(p => 
        (p.resourceId.includes('health_record') || 
         p.resourceId.includes('rehab_plan') || 
         p.resourceId.includes('health_data') ||
         p.resourceId.includes('chat') ||
         p.resourceId.includes('notification')) && 
        p.action === 'read'
      ).map(p => p.id), // 患者只有查看权限
      '4': mockPermissions.filter(p => 
        (p.resourceId.includes('health_record') || 
         p.resourceId.includes('rehab_plan') || 
         p.resourceId.includes('health_data') ||
         p.resourceId.includes('chat') ||
         p.resourceId.includes('notification')) && 
        (p.action === 'read' || p.action === 'update')
      ).map(p => p.id) // 健康管理师有读取和更新权限
    };
    
    setRolePermissions(mockRolePermissions);
  }, []);
  
  // 根据操作类型返回描述
  function getActionDescription(action: 'read' | 'create' | 'update' | 'delete' | 'manage'): string {
    switch (action) {
      case 'read': return '查看';
      case 'create': return '创建';
      case 'update': return '更新';
      case 'delete': return '删除';
      case 'manage': return '管理';
      default: return '';
    }
  }
  
  // 选择角色处理
  const handleRoleSelect = (role: Role) => {
    setSelectedRole(role);
    
    // 重置权限矩阵
    const matrix: {[resourceId: string]: {[action: string]: boolean}} = {};
    
    // 初始化矩阵
    resources.forEach(resource => {
      matrix[resource.id] = {
        read: false,
        create: false,
        update: false,
        delete: false,
        manage: false
      };
    });
    
    // 填充角色权限
    const rolePerms = rolePermissions[role.id] || [];
    rolePerms.forEach(permId => {
      const perm = permissions.find(p => p.id === permId);
      if (perm) {
        matrix[perm.resourceId][perm.action] = true;
      }
    });
    
    setPermissionMatrix(matrix);
  };
  
  // 切换权限状态
  const handleTogglePermission = (resourceId: string, action: string) => {
    if (!selectedRole) return;
    
    // 更新权限矩阵
    setPermissionMatrix(prev => ({
      ...prev,
      [resourceId]: {
        ...prev[resourceId],
        [action]: !prev[resourceId][action]
      }
    }));
    
    // 更新角色权限
    const permId = `${resourceId}_${action}`;
    
    setRolePermissions(prev => {
      const currentPerms = [...(prev[selectedRole.id] || [])];
      const permIndex = currentPerms.indexOf(permId);
      
      if (permIndex === -1) {
        // 添加权限
        currentPerms.push(permId);
      } else {
        // 移除权限
        currentPerms.splice(permIndex, 1);
      }
      
      return {
        ...prev,
        [selectedRole.id]: currentPerms
      };
    });
  };
  
  // 批量设置权限
  const handleBatchPermission = (resourceIds: string[], action: string, grant: boolean) => {
    if (!selectedRole) return;
    
    // 更新权限矩阵
    const newMatrix = { ...permissionMatrix };
    
    resourceIds.forEach(resourceId => {
      newMatrix[resourceId] = {
        ...newMatrix[resourceId],
        [action]: grant
      };
    });
    
    setPermissionMatrix(newMatrix);
    
    // 更新角色权限
    setRolePermissions(prev => {
      let currentPerms = [...(prev[selectedRole.id] || [])];
      
      resourceIds.forEach(resourceId => {
        const permId = `${resourceId}_${action}`;
        const permIndex = currentPerms.indexOf(permId);
        
        if (grant && permIndex === -1) {
          // 添加权限
          currentPerms.push(permId);
        } else if (!grant && permIndex !== -1) {
          // 移除权限
          currentPerms = currentPerms.filter(id => id !== permId);
        }
      });
      
      return {
        ...prev,
        [selectedRole.id]: currentPerms
      };
    });
  };
  
  // 保存权限设置
  const handleSavePermissions = () => {
    // 这里应该调用API保存权限设置
    // 实际使用时替换为API调用
    // await permissionApi.saveRolePermissions(selectedRole.id, rolePermissions[selectedRole.id]);
    
    setNotification({
      open: true,
      message: '权限设置已保存',
      severity: 'success'
    });
  };
  
  // 基础布局
  return (
    <Box sx={{ width: '100%' }}>
      <Paper elevation={2} sx={{ width: '100%', mb: 2, p: 2 }}>
        <Typography variant="h5" component="h2" gutterBottom>
          权限管理系统
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          通过这个界面，您可以管理系统的角色、权限和用户授权。
        </Typography>
        
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs 
            value={tabIndex} 
            onChange={handleTabChange} 
            aria-label="permission management tabs"
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label="角色管理" {...a11yProps(0)} />
            <Tab label="权限配置" {...a11yProps(1)} />
            <Tab label="资源管理" {...a11yProps(2)} />
            <Tab label="用户授权" {...a11yProps(3)} />
          </Tabs>
        </Box>
        
        {loading && <LinearProgress />}
        
        <TabPanel value={tabIndex} index={0}>
          {/* 角色管理界面 */}
          <Typography variant="h6" gutterBottom>
            角色列表
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Button 
              variant="contained" 
              startIcon={<AddIcon />}
              sx={{ mr: 1 }}
            >
              新建角色
            </Button>
            <Button 
              variant="outlined" 
              startIcon={<RefreshIcon />}
            >
              刷新
            </Button>
          </Box>
          
          <TableContainer>
            <Table stickyHeader aria-label="角色列表">
              <StyledTableHead>
                <TableRow>
                  <TableCell>角色名称</TableCell>
                  <TableCell>描述</TableCell>
                  <TableCell>系统角色</TableCell>
                  <TableCell>创建时间</TableCell>
                  <TableCell>更新时间</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </StyledTableHead>
              <TableBody>
                {roles.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage).map((role) => (
                  <TableRow hover key={role.id}>
                    <TableCell>{role.name}</TableCell>
                    <TableCell>{role.description}</TableCell>
                    <TableCell>{role.isSystem ? '是' : '否'}</TableCell>
                    <TableCell>{role.createdAt.toLocaleString()}</TableCell>
                    <TableCell>{role.updatedAt.toLocaleString()}</TableCell>
                    <TableCell align="center">
                      <Tooltip title="编辑">
                        <IconButton size="small">
                          <EditIcon />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="删除">
                        <IconButton 
                          size="small" 
                          disabled={role.isSystem}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          
          <TablePagination
            rowsPerPageOptions={[5, 10, 25]}
            component="div"
            count={roles.length}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handleChangePage}
            onRowsPerPageChange={handleChangeRowsPerPage}
            labelRowsPerPage="每页行数:"
            labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
          />
        </TabPanel>
        
        <TabPanel value={tabIndex} index={1}>
          {/* 权限配置界面 */}
          <Typography variant="h6" gutterBottom>
            权限配置
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary" paragraph>
              在此配置角色的权限，为每个角色分配可访问的资源和允许的操作。
            </Typography>
          </Box>
          
          {/* 角色选择区 */}
          <Box sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
            <Typography variant="subtitle1" sx={{ mr: 2 }}>
              选择角色:
            </Typography>
            <FormControl sx={{ minWidth: 200 }}>
              <Select
                value={selectedRole ? selectedRole.id : ''}
                onChange={(e) => {
                  const role = roles.find(r => r.id === e.target.value);
                  if (role) handleRoleSelect(role);
                }}
                displayEmpty
              >
                <MenuItem value="" disabled>
                  请选择角色
                </MenuItem>
                {roles.map((role) => (
                  <MenuItem key={role.id} value={role.id}>
                    {role.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
          
          {selectedRole ? (
            <>
              <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
                <Typography variant="subtitle1" gutterBottom>
                  角色信息
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Typography variant="body2">
                    <strong>名称:</strong> {selectedRole.name}
                  </Typography>
                  <Typography variant="body2">
                    <strong>描述:</strong> {selectedRole.description}
                  </Typography>
                  <Typography variant="body2">
                    <strong>类型:</strong> {selectedRole.isSystem ? '系统角色' : '自定义角色'}
                  </Typography>
                </Box>
              </Paper>
              
              <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="h6">权限矩阵</Typography>
                <Button 
                  variant="contained" 
                  color="primary" 
                  startIcon={<SaveIcon />}
                  onClick={handleSavePermissions}
                >
                  保存权限设置
                </Button>
              </Box>
              
              <Paper sx={{ mb: 3, overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold', minWidth: 180 }}>资源</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>查看</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>创建</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>更新</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>删除</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>管理</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resourceCategories.map((category) => (
                      <React.Fragment key={category}>
                        <TableRow sx={{ bgcolor: 'rgba(0, 0, 0, 0.04)' }}>
                          <TableCell colSpan={6} sx={{ fontWeight: 'bold' }}>
                            {category}
                          </TableCell>
                        </TableRow>
                        {resources
                          .filter(resource => resource.category === category)
                          .map(resource => (
                            <TableRow key={resource.id} hover>
                              <TableCell>
                                <Tooltip title={resource.description} arrow>
                                  <Box component="span">{resource.name}</Box>
                                </Tooltip>
                              </TableCell>
                              <TableCell align="center">
                                <Checkbox
                                  checked={permissionMatrix[resource.id]?.read || false}
                                  onChange={() => handleTogglePermission(resource.id, 'read')}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Checkbox
                                  checked={permissionMatrix[resource.id]?.create || false}
                                  onChange={() => handleTogglePermission(resource.id, 'create')}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Checkbox
                                  checked={permissionMatrix[resource.id]?.update || false}
                                  onChange={() => handleTogglePermission(resource.id, 'update')}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Checkbox
                                  checked={permissionMatrix[resource.id]?.delete || false}
                                  onChange={() => handleTogglePermission(resource.id, 'delete')}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Checkbox
                                  checked={permissionMatrix[resource.id]?.manage || false}
                                  onChange={() => handleTogglePermission(resource.id, 'manage')}
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        {/* 批量操作行 */}
                        <TableRow sx={{ bgcolor: 'rgba(0, 0, 0, 0.02)' }}>
                          <TableCell>
                            <Typography variant="body2" color="textSecondary">
                              批量操作 {category}
                            </Typography>
                          </TableCell>
                          {['read', 'create', 'update', 'delete', 'manage'].map(action => (
                            <TableCell key={action} align="center">
                              <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.5 }}>
                                <Tooltip title={`全部授予${getActionDescription(action as any)}权限`}>
                                  <IconButton 
                                    size="small" 
                                    color="primary"
                                    onClick={() => handleBatchPermission(
                                      resources
                                        .filter(r => r.category === category)
                                        .map(r => r.id),
                                      action,
                                      true
                                    )}
                                  >
                                    <ArrowUpwardIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                                <Tooltip title={`全部移除${getActionDescription(action as any)}权限`}>
                                  <IconButton 
                                    size="small" 
                                    color="error"
                                    onClick={() => handleBatchPermission(
                                      resources
                                        .filter(r => r.category === category)
                                        .map(r => r.id),
                                      action,
                                      false
                                    )}
                                  >
                                    <ArrowDownwardIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </Box>
                            </TableCell>
                          ))}
                        </TableRow>
                      </React.Fragment>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="h6" gutterBottom>
                  权限预览
                </Typography>
                <Paper sx={{ p: 2 }}>
                  <Typography variant="body2" paragraph>
                    角色 <strong>{selectedRole.name}</strong> 拥有以下权限:
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {rolePermissions[selectedRole.id]?.map(permId => {
                      const perm = permissions.find(p => p.id === permId);
                      if (!perm) return null;
                      const resource = resources.find(r => r.id === perm.resourceId);
                      return (
                        <Chip 
                          key={permId}
                          label={`${getActionDescription(perm.action)} ${resource?.name || perm.resourceId}`}
                          color="primary"
                          variant="outlined"
                          size="small"
                        />
                      );
                    })}
                    {(!rolePermissions[selectedRole.id] || rolePermissions[selectedRole.id].length === 0) && (
                      <Typography variant="body2" color="text.secondary">
                        该角色暂无任何权限
                      </Typography>
                    )}
                  </Box>
                </Paper>
              </Box>
            </>
          ) : (
            <Alert severity="info" sx={{ mt: 2 }}>
              请先选择一个角色来配置权限
            </Alert>
          )}
        </TabPanel>
        
        <TabPanel value={tabIndex} index={2}>
          {/* 资源管理界面 */}
          <Typography variant="h6" gutterBottom>
            资源管理
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary" paragraph>
              管理系统中的资源，如模块、页面、API等，作为权限控制的基础。
            </Typography>
          </Box>
          
          {/* 资源管理工具栏 */}
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between' }}>
            <Box>
              <Button 
                variant="contained" 
                startIcon={<AddIcon />} 
                sx={{ mr: 1 }}
                onClick={() => {
                  setResourceDialog({
                    open: true,
                    mode: 'create',
                    resource: {
                      id: '',
                      name: '',
                      description: '',
                      category: resourceCategories[0] || '系统'
                    }
                  });
                }}
              >
                添加资源
              </Button>
              <Button 
                variant="outlined" 
                startIcon={<FilterListIcon />}
                sx={{ mr: 1 }}
                onClick={() => setCategoryDialog(true)}
              >
                管理分类
              </Button>
              <Button 
                variant="outlined" 
                startIcon={<RefreshIcon />}
              >
                刷新
              </Button>
            </Box>
            <TextField
              variant="outlined"
              size="small"
              placeholder="搜索资源..."
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
              onChange={(e) => {
                const searchText = e.target.value.toLowerCase();
                setFilteredResources(
                  searchText 
                    ? resources.filter(r => 
                        r.name.toLowerCase().includes(searchText) || 
                        r.description.toLowerCase().includes(searchText) ||
                        r.category.toLowerCase().includes(searchText)
                      )
                    : resources
                );
              }}
            />
          </Box>
          
          {/* 资源列表 */}
          <Paper sx={{ width: '100%', overflow: 'hidden' }}>
            <TableContainer sx={{ maxHeight: 440 }}>
              <Table stickyHeader aria-label="sticky table">
                <StyledTableHead>
                  <TableRow>
                    <TableCell sx={{ minWidth: 180 }}>资源名称</TableCell>
                    <TableCell sx={{ minWidth: 250 }}>描述</TableCell>
                    <TableCell sx={{ minWidth: 120 }}>分类</TableCell>
                    <TableCell sx={{ minWidth: 100 }}>ID</TableCell>
                    <TableCell sx={{ minWidth: 120 }} align="center">操作</TableCell>
                  </TableRow>
                </StyledTableHead>
                <TableBody>
                  {filteredResources
                    .slice(resourcePage * rowsPerPage, resourcePage * rowsPerPage + rowsPerPage)
                    .map((resource) => (
                      <TableRow hover key={resource.id}>
                        <TableCell>{resource.name}</TableCell>
                        <TableCell>{resource.description}</TableCell>
                        <TableCell>
                          <Chip 
                            label={resource.category} 
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Tooltip title={resource.id}>
                            <Typography variant="body2" noWrap>
                              {resource.id.length > 10 
                                ? `${resource.id.substring(0, 10)}...` 
                                : resource.id}
                            </Typography>
                          </Tooltip>
                        </TableCell>
                        <TableCell align="center">
                          <Tooltip title="编辑">
                            <IconButton 
                              size="small"
                              onClick={() => {
                                setResourceDialog({
                                  open: true,
                                  mode: 'edit',
                                  resource: { ...resource }
                                });
                              }}
                            >
                              <EditIcon />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="删除">
                            <IconButton 
                              size="small"
                              onClick={() => {
                                setConfirmDialog({
                                  open: true,
                                  title: '删除资源',
                                  message: `确定要删除资源 "${resource.name}" 吗？这可能会影响当前使用该资源的所有权限设置。`,
                                  confirmText: '删除',
                                  confirmAction: () => {
                                    // 实际环境中调用删除API
                                    // 模拟删除
                                    setResources(prev => prev.filter(r => r.id !== resource.id));
                                    setNotification({
                                      open: true,
                                      message: '资源已删除',
                                      severity: 'success'
                                    });
                                    setConfirmDialog(prev => ({ ...prev, open: false }));
                                  }
                                });
                              }}
                            >
                              <DeleteIcon />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              rowsPerPageOptions={[5, 10, 25]}
              component="div"
              count={filteredResources.length}
              rowsPerPage={rowsPerPage}
              page={resourcePage}
              onPageChange={(e, newPage) => setResourcePage(newPage)}
              onRowsPerPageChange={handleChangeRowsPerPage}
              labelRowsPerPage="每页行数:"
              labelDisplayedRows={({ from, to, count }) => `${from}-${to} / ${count}`}
            />
          </Paper>
        </TabPanel>
        
        <TabPanel value={tabIndex} index={3}>
          {/* 用户授权界面 */}
          <Typography variant="h6" gutterBottom>
            用户授权
          </Typography>
          <Box sx={{ mb: 2 }}>
            <Typography variant="body2" color="text.secondary" paragraph>
              为用户分配角色，管理用户的权限和访问控制。
            </Typography>
          </Box>
          
          {/* 用户列表与角色分配 */}
          <Box sx={{ display: 'flex', gap: 2 }}>
            {/* 用户列表 */}
            <Paper sx={{ flex: 2, p: 2 }}>
              <Typography variant="subtitle1" gutterBottom>
                用户列表
              </Typography>
              
              <TextField
                variant="outlined"
                size="small"
                placeholder="搜索用户..."
                fullWidth
                sx={{ mb: 2 }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
                onChange={(e) => {
                  const searchText = e.target.value.toLowerCase();
                  setFilteredUsers(
                    searchText 
                      ? users.filter(u => 
                          u.username.toLowerCase().includes(searchText) || 
                          u.fullName.toLowerCase().includes(searchText) ||
                          u.email.toLowerCase().includes(searchText) ||
                          (u.department && u.department.toLowerCase().includes(searchText))
                        )
                      : users
                  );
                }}
              />
              
              <List sx={{ width: '100%', bgcolor: 'background.paper', maxHeight: 400, overflow: 'auto' }}>
                {filteredUsers.map((user) => (
                  <ListItem
                    key={user.id}
                    secondaryAction={
                      <Tooltip title="查看用户详情">
                        <IconButton edge="end" aria-label="查看详情">
                          <InfoIcon />
                        </IconButton>
                      </Tooltip>
                    }
                    disablePadding
                  >
                    <ListItemButton
                      selected={selectedUser?.id === user.id}
                      onClick={() => setSelectedUser(user)}
                    >
                      <ListItemAvatar>
                        <Avatar>
                          {user.fullName.charAt(0).toUpperCase()}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={user.fullName}
                        secondary={
                          <React.Fragment>
                            <Typography
                              component="span"
                              variant="body2"
                              color="text.primary"
                              sx={{ display: 'block' }}
                            >
                              {user.username}
                            </Typography>
                            <Typography
                              component="span"
                              variant="body2"
                              sx={{ display: 'block' }}
                            >
                              {user.email}
                            </Typography>
                            {user.department && (
                              <Typography
                                component="span"
                                variant="body2"
                                sx={{ display: 'block' }}
                              >
                                {user.department} {user.position && `- ${user.position}`}
                              </Typography>
                            )}
                          </React.Fragment>
                        }
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
              </List>
            </Paper>
            
            {/* 角色分配 */}
            <Paper sx={{ flex: 3, p: 2 }}>
              {selectedUser ? (
                <>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="subtitle1">
                      {selectedUser.fullName} 的角色分配
                    </Typography>
                    <Button 
                      variant="contained" 
                      startIcon={<SaveIcon />}
                      onClick={() => {
                        // 实际环境中调用保存API
                        // 模拟保存
                        setNotification({
                          open: true,
                          message: '用户角色分配已保存',
                          severity: 'success'
                        });
                      }}
                    >
                      保存更改
                    </Button>
                  </Box>
                  
                  <FormGroup>
                    {roles.map((role) => (
                      <FormControlLabel
                        key={role.id}
                        control={
                          <Checkbox
                            checked={selectedUserRoles.includes(role.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedUserRoles(prev => [...prev, role.id]);
                              } else {
                                setSelectedUserRoles(prev => prev.filter(id => id !== role.id));
                              }
                            }}
                            disabled={role.isSystem && role.name === 'SuperAdmin'}
                          />
                        }
                        label={
                          <Box>
                            <Typography variant="body1">{role.name}</Typography>
                            <Typography variant="body2" color="text.secondary">
                              {role.description}
                            </Typography>
                          </Box>
                        }
                      />
                    ))}
                  </FormGroup>
                </>
              ) : (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                  <Typography variant="body1" color="text.secondary">
                    请从左侧选择一个用户来分配角色
                  </Typography>
                </Box>
              )}
            </Paper>
          </Box>
        </TabPanel>
      </Paper>
      
      {/* 通知提示 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={6000}
        onClose={handleCloseNotification}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={handleCloseNotification} 
          severity={notification.severity}
          variant="filled"
        >
          {notification.message}
        </Alert>
      </Snackbar>

      {/* 资源对话框 */}
      <Dialog 
        open={resourceDialog.open} 
        onClose={() => setResourceDialog(prev => ({ ...prev, open: false }))}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          {resourceDialog.mode === 'create' ? '创建新资源' : '编辑资源'}
        </DialogTitle>
        <DialogContent>
          <Box component="form" sx={{ mt: 1 }}>
            <TextField
              margin="normal"
              fullWidth
              label="资源名称"
              value={resourceDialog.resource?.name || ''}
              onChange={(e) => setResourceDialog(prev => ({
                ...prev,
                resource: { ...prev.resource!, name: e.target.value }
              }))}
              required
            />
            <TextField
              margin="normal"
              fullWidth
              label="资源描述"
              value={resourceDialog.resource?.description || ''}
              onChange={(e) => setResourceDialog(prev => ({
                ...prev,
                resource: { ...prev.resource!, description: e.target.value }
              }))}
              multiline
              rows={2}
            />
            <FormControl fullWidth margin="normal">
              <InputLabel>资源分类</InputLabel>
              <Select
                value={resourceDialog.resource?.category || ''}
                onChange={(e) => setResourceDialog(prev => ({
                  ...prev,
                  resource: { ...prev.resource!, category: e.target.value }
                }))}
                label="资源分类"
              >
                {resourceCategories.map((category) => (
                  <MenuItem key={category} value={category}>
                    {category}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            {resourceDialog.mode === 'create' && (
              <TextField
                margin="normal"
                fullWidth
                label="资源ID (可选)"
                helperText="如不填写将自动生成ID"
                value={resourceDialog.resource?.id || ''}
                onChange={(e) => setResourceDialog(prev => ({
                  ...prev,
                  resource: { ...prev.resource!, id: e.target.value }
                }))}
              />
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResourceDialog(prev => ({ ...prev, open: false }))}>
            取消
          </Button>
          <Button 
            variant="contained" 
            onClick={() => {
              // 实际环境中调用API
              // 模拟保存
              if (resourceDialog.mode === 'create') {
                const newResource = {
                  ...resourceDialog.resource!,
                  id: resourceDialog.resource!.id || `resource_${Date.now()}`
                };
                setResources(prev => [...prev, newResource]);
                setNotification({
                  open: true,
                  message: '资源创建成功',
                  severity: 'success'
                });
              } else {
                setResources(prev => 
                  prev.map(r => r.id === resourceDialog.resource!.id ? resourceDialog.resource! : r)
                );
                setNotification({
                  open: true,
                  message: '资源更新成功',
                  severity: 'success'
                });
              }
              setResourceDialog(prev => ({ ...prev, open: false }));
            }}
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 分类管理对话框 */}
      <Dialog 
        open={categoryDialog} 
        onClose={() => setCategoryDialog(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>管理资源分类</DialogTitle>
        <DialogContent>
          <List sx={{ width: '100%', bgcolor: 'background.paper' }}>
            {resourceCategories.map((category, index) => (
              <ListItem
                key={index}
                secondaryAction={
                  <IconButton 
                    edge="end" 
                    aria-label="删除"
                    onClick={() => {
                      setResourceCategories(prev => prev.filter(c => c !== category));
                    }}
                    disabled={category === '系统'} // 不允许删除系统分类
                  >
                    <DeleteIcon />
                  </IconButton>
                }
              >
                <ListItemText primary={category} />
              </ListItem>
            ))}
          </List>
          <Box sx={{ display: 'flex', mt: 2 }}>
            <TextField
              fullWidth
              size="small"
              label="新分类名称"
              variant="outlined"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            />
            <Button 
              variant="contained" 
              sx={{ ml: 1 }}
              onClick={() => {
                if (newCategory && !resourceCategories.includes(newCategory)) {
                  setResourceCategories(prev => [...prev, newCategory]);
                  setNewCategory('');
                }
              }}
              disabled={!newCategory || resourceCategories.includes(newCategory)}
            >
              添加
            </Button>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCategoryDialog(false)}>关闭</Button>
        </DialogActions>
      </Dialog>

      {/* 确认对话框 */}
      <Dialog
        open={confirmDialog.open}
        onClose={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
        aria-labelledby="alert-dialog-title"
        aria-describedby="alert-dialog-description"
      >
        <DialogTitle id="alert-dialog-title">
          {confirmDialog.title}
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="alert-dialog-description">
            {confirmDialog.message}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmDialog(prev => ({ ...prev, open: false }))}>
            取消
          </Button>
          <Button 
            variant="contained" 
            color="error" 
            onClick={confirmDialog.confirmAction}
            autoFocus
          >
            {confirmDialog.confirmText || '确认'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default PermissionManager; 