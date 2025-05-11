import React from 'react';
import {
  Box,
  Typography,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Chip,
  TextField,
  InputAdornment,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Drawer,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Tabs,
  Tab,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import BusinessIcon from '@mui/icons-material/Business';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import PeopleIcon from '@mui/icons-material/People';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import TreeView from '@mui/lab/TreeView';
import TreeItem from '@mui/lab/TreeItem';

// 模拟数据
const mockOrganizations = [
  { 
    id: '1', 
    name: '仁爱医院', 
    type: '医院', 
    address: '北京市海淀区中关村南大街甲12号', 
    contactPerson: '张院长',
    contactPhone: '010-12345678',
    departments: 15,
    doctors: 120,
    patients: 5600,
    status: '正常'
  },
  { 
    id: '2', 
    name: '康复中心', 
    type: '专科机构', 
    address: '上海市浦东新区张江高科技园区', 
    contactPerson: '李主任',
    contactPhone: '021-87654321',
    departments: 8,
    doctors: 45,
    patients: 1200,
    status: '正常'
  },
  { 
    id: '3', 
    name: '社区医疗服务中心', 
    type: '社区医疗', 
    address: '广州市天河区车陂路123号', 
    contactPerson: '王经理',
    contactPhone: '020-98765432',
    departments: 5,
    doctors: 20,
    patients: 3500,
    status: '停用'
  },
];

// 模拟组织结构树
const orgTree = {
  id: 'root',
  name: '医疗系统组织结构',
  children: [
    {
      id: '1',
      name: '仁爱医院',
      children: [
        { id: '1-1', name: '内科部门' },
        { id: '1-2', name: '外科部门' },
        { id: '1-3', name: '康复科部门' },
        { id: '1-4', name: '医技部门' },
      ]
    },
    {
      id: '2',
      name: '康复中心',
      children: [
        { id: '2-1', name: '运动康复部' },
        { id: '2-2', name: '理疗康复部' },
      ]
    },
    {
      id: '3',
      name: '社区医疗服务中心',
      children: [
        { id: '3-1', name: '全科医疗部' },
        { id: '3-2', name: '家庭医生部' },
      ]
    }
  ]
};

const renderTree = (nodes: any) => (
  <TreeItem key={nodes.id} nodeId={nodes.id} label={nodes.name} icon={nodes.id === 'root' ? <BusinessIcon /> : null}>
    {Array.isArray(nodes.children)
      ? nodes.children.map((node: any) => renderTree(node))
      : null}
  </TreeItem>
);

// 模拟组织结构数据
const organizationData = {
  id: 'org-1',
  name: '智能康复医疗中心',
  type: 'organization',
  children: [
    {
      id: 'dept-1',
      name: '康复医学科',
      type: 'department',
      children: [
        {
          id: 'team-1',
          name: '骨科康复团队',
          type: 'team',
          members: 12,
          leader: '王医生'
        },
        {
          id: 'team-2',
          name: '神经康复团队',
          type: 'team',
          members: 8,
          leader: '李医生'
        }
      ]
    },
    {
      id: 'dept-2',
      name: '物理治疗科',
      type: 'department',
      children: [
        {
          id: 'team-3',
          name: '运动治疗团队',
          type: 'team',
          members: 6,
          leader: '张医生'
        }
      ]
    },
    {
      id: 'dept-3',
      name: '健康管理部',
      type: 'department',
      children: [
        {
          id: 'team-4',
          name: '慢病管理团队',
          type: 'team',
          members: 5,
          leader: '刘管理师'
        },
        {
          id: 'team-5',
          name: '营养指导团队',
          type: 'team',
          members: 3,
          leader: '赵管理师'
        }
      ]
    }
  ]
};

// 模拟部门类型
const departmentTypes = [
  '康复医学科',
  '物理治疗科',
  '作业治疗科',
  '言语治疗科',
  '健康管理部',
  '康复评定科',
  '中医康复科',
  '心理康复科',
];

// 模拟团队类型
const teamTypes = [
  '骨科康复团队',
  '神经康复团队',
  '运动治疗团队',
  '慢病管理团队',
  '营养指导团队',
  '言语治疗团队',
  '心理康复团队',
];

const OrganizationManagement: React.FC = () => {
  const [organizations, setOrganizations] = React.useState(mockOrganizations);
  const [searchTerm, setSearchTerm] = React.useState('');
  const [openDialog, setOpenDialog] = React.useState(false);
  const [editMode, setEditMode] = React.useState(false);
  const [selectedOrg, setSelectedOrg] = React.useState<any>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [expanded, setExpanded] = React.useState<string[]>(['org-1']);
  const [selected, setSelected] = React.useState<string>('');
  const [tabValue, setTabValue] = React.useState(0);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const [selectedNodeDetails, setSelectedNodeDetails] = React.useState<any>(null);
  const [dialogType, setDialogType] = React.useState<'department' | 'team' | ''>('');
  const [parentId, setParentId] = React.useState<string>('');

  const handleSearch = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(event.target.value);
    if (event.target.value === '') {
      setOrganizations(mockOrganizations);
    } else {
      const filtered = mockOrganizations.filter(org => 
        org.name.toLowerCase().includes(event.target.value.toLowerCase()) || 
        org.type.toLowerCase().includes(event.target.value.toLowerCase())
      );
      setOrganizations(filtered);
    }
  };

  const handleOpenDialog = (org?: any) => {
    if (org) {
      setEditMode(true);
      setSelectedOrg(org);
    } else {
      setEditMode(false);
      setSelectedOrg(null);
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setDetailsOpen(false);
    setDialogType('');
    setParentId('');
  };

  const handleDeleteOrg = (orgId: string) => {
    setOrganizations(organizations.filter(org => org.id !== orgId));
  };

  const toggleDrawer = () => {
    setDrawerOpen(!drawerOpen);
  };

  const handleTreeNodeToggle = (event: React.SyntheticEvent, nodeIds: string[]) => {
    setExpanded(nodeIds);
  };

  const handleTreeNodeSelect = (event: React.SyntheticEvent, nodeId: string) => {
    setSelected(nodeId);
    
    // 查找选中的节点详情
    const findNode = (nodes: any[], id: string): any => {
      for (const node of nodes) {
        if (node.id === id) return node;
        if (node.children) {
          const found = findNode(node.children, id);
          if (found) return found;
        }
      }
      return null;
    };
    
    // 处理组织根节点
    if (nodeId === organizationData.id) {
      setSelectedNodeDetails(organizationData);
      setDetailsOpen(true);
      return;
    }
    
    // 处理部门和团队节点
    const node = findNode(organizationData.children, nodeId);
    if (node) {
      setSelectedNodeDetails(node);
      setDetailsOpen(true);
    }
  };

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleAddDepartment = () => {
    setDialogType('department');
    setParentId('org-1');
    setOpenDialog(true);
  };

  const handleAddTeam = () => {
    setDialogType('team');
    setParentId(selected);
    setOpenDialog(true);
  };

  const handleSave = () => {
    // 保存添加/编辑的部门或团队
    handleCloseDialog();
  };

  const renderTree = (nodes: any) => (
    <TreeItem 
      key={nodes.id} 
      nodeId={nodes.id} 
      label={
        <Box display="flex" alignItems="center">
          {nodes.type === 'organization' && <BusinessIcon sx={{ mr: 1 }} />}
          {nodes.type === 'department' && <LocalHospitalIcon sx={{ mr: 1 }} />}
          {nodes.type === 'team' && <PeopleIcon sx={{ mr: 1 }} />}
          <Typography>{nodes.name}</Typography>
          {nodes.type === 'team' && (
            <Chip 
              label={`${nodes.members}人`} 
              size="small" 
              color="primary"
              sx={{ ml: 1 }}
            />
          )}
        </Box>
      }
    >
      {Array.isArray(nodes.children)
        ? nodes.children.map((node) => renderTree(node))
        : null}
    </TreeItem>
  );

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" component="h2">
          组织机构管理
        </Typography>
        <Box>
          <Button
            variant="outlined"
            sx={{ mr: 1 }}
            onClick={toggleDrawer}
          >
            组织结构树
          </Button>
          <Button
            variant="contained"
            color="primary"
            startIcon={<AddIcon />}
            onClick={() => handleOpenDialog()}
          >
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
              <TableCell>机构名称</TableCell>
              <TableCell>类型</TableCell>
              <TableCell>联系人</TableCell>
              <TableCell>部门数</TableCell>
              <TableCell>医生数</TableCell>
              <TableCell>患者数</TableCell>
              <TableCell>状态</TableCell>
              <TableCell align="center">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {organizations.map((org) => (
              <TableRow key={org.id}>
                <TableCell>{org.name}</TableCell>
                <TableCell>{org.type}</TableCell>
                <TableCell>{`${org.contactPerson} (${org.contactPhone})`}</TableCell>
                <TableCell>{org.departments}</TableCell>
                <TableCell>{org.doctors}</TableCell>
                <TableCell>{org.patients}</TableCell>
                <TableCell>
                  <Chip 
                    label={org.status} 
                    color={org.status === '正常' ? 'success' : 'error'} 
                    size="small" 
                  />
                </TableCell>
                <TableCell align="center">
                  <IconButton
                    color="primary"
                    onClick={() => handleOpenDialog(org)}
                  >
                    <EditIcon />
                  </IconButton>
                  <IconButton
                    color="error"
                    onClick={() => handleDeleteOrg(org.id)}
                  >
                    <DeleteIcon />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 编辑/添加机构对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>{editMode ? '编辑机构' : '添加机构'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="机构名称"
                variant="outlined"
                defaultValue={selectedOrg?.name || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>机构类型</InputLabel>
                <Select
                  label="机构类型"
                  defaultValue={selectedOrg?.type || ''}
                >
                  <MenuItem value="医院">医院</MenuItem>
                  <MenuItem value="专科机构">专科机构</MenuItem>
                  <MenuItem value="社区医疗">社区医疗</MenuItem>
                  <MenuItem value="康复中心">康复中心</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="地址"
                variant="outlined"
                defaultValue={selectedOrg?.address || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="联系人"
                variant="outlined"
                defaultValue={selectedOrg?.contactPerson || ''}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="联系电话"
                variant="outlined"
                defaultValue={selectedOrg?.contactPhone || ''}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="部门数量"
                type="number"
                variant="outlined"
                defaultValue={selectedOrg?.departments || ''}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="医生数量"
                type="number"
                variant="outlined"
                defaultValue={selectedOrg?.doctors || ''}
              />
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField
                fullWidth
                label="患者数量"
                type="number"
                variant="outlined"
                defaultValue={selectedOrg?.patients || ''}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>状态</InputLabel>
                <Select
                  label="状态"
                  defaultValue={selectedOrg?.status || '正常'}
                >
                  <MenuItem value="正常">正常</MenuItem>
                  <MenuItem value="停用">停用</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button 
            onClick={handleCloseDialog} 
            variant="contained" 
            color="primary"
          >
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 组织结构树抽屉 */}
      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={toggleDrawer}
        sx={{ width: 350 }}
      >
        <Box sx={{ width: 350, p: 2 }}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">组织结构</Typography>
            <Button onClick={toggleDrawer}>关闭</Button>
          </Box>
          <Divider sx={{ mb: 2 }} />
          <TreeView
            defaultCollapseIcon={<ExpandMoreIcon />}
            defaultExpandIcon={<ChevronRightIcon />}
            expanded={expanded}
            selected={selected}
            onNodeToggle={handleTreeNodeToggle}
            onNodeSelect={handleTreeNodeSelect}
          >
            {renderTree(organizationData)}
          </TreeView>
        </Box>
      </Drawer>

      <Grid container spacing={3}>
        <Grid item xs={12} md={5} lg={4}>
          <Paper sx={{ p: 2, minHeight: 400 }}>
            <Typography variant="h6" gutterBottom>
              组织结构
            </Typography>
            <Divider sx={{ mb: 2 }} />
            
            <TreeView
              defaultCollapseIcon={<ExpandMoreIcon />}
              defaultExpandIcon={<ChevronRightIcon />}
              expanded={expanded}
              selected={selected}
              onNodeToggle={handleTreeNodeToggle}
              onNodeSelect={handleTreeNodeSelect}
            >
              {renderTree(organizationData)}
            </TreeView>
          </Paper>
        </Grid>

        <Grid item xs={12} md={7} lg={8}>
          <Paper sx={{ p: 2, minHeight: 400 }}>
            <Tabs value={tabValue} onChange={handleTabChange} sx={{ mb: 2 }}>
              <Tab label="成员管理" />
              <Tab label="详细信息" />
            </Tabs>
            
            {tabValue === 0 ? (
              selected ? (
                <Box>
                  <Typography variant="subtitle1" gutterBottom>
                    {selectedNodeDetails?.name} 成员列表
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    这里将显示所选部门或团队的成员列表和管理功能
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  请在左侧选择一个部门或团队来查看成员
                </Typography>
              )
            ) : (
              selected ? (
                <Box>
                  <Typography variant="subtitle1" gutterBottom>
                    {selectedNodeDetails?.name} 详细信息
                  </Typography>
                  {selectedNodeDetails?.type === 'organization' && (
                    <Box>
                      <Typography variant="body2" gutterBottom>
                        <strong>组织名称:</strong> {selectedNodeDetails.name}
                      </Typography>
                      <Typography variant="body2" gutterBottom>
                        <strong>部门数量:</strong> {selectedNodeDetails.children.length}
                      </Typography>
                      <Typography variant="body2" gutterBottom>
                        <strong>团队总数:</strong> {selectedNodeDetails.children.reduce((acc: number, dept: any) => acc + (dept.children ? dept.children.length : 0), 0)}
                      </Typography>
                    </Box>
                  )}
                  {selectedNodeDetails?.type === 'department' && (
                    <Box>
                      <Typography variant="body2" gutterBottom>
                        <strong>部门名称:</strong> {selectedNodeDetails.name}
                      </Typography>
                      <Typography variant="body2" gutterBottom>
                        <strong>团队数量:</strong> {selectedNodeDetails.children ? selectedNodeDetails.children.length : 0}
                      </Typography>
                    </Box>
                  )}
                  {selectedNodeDetails?.type === 'team' && (
                    <Box>
                      <Typography variant="body2" gutterBottom>
                        <strong>团队名称:</strong> {selectedNodeDetails.name}
                      </Typography>
                      <Typography variant="body2" gutterBottom>
                        <strong>团队成员:</strong> {selectedNodeDetails.members}人
                      </Typography>
                      <Typography variant="body2" gutterBottom>
                        <strong>团队负责人:</strong> {selectedNodeDetails.leader}
                      </Typography>
                    </Box>
                  )}
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  请在左侧选择一个部门或团队来查看详细信息
                </Typography>
              )
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* 添加部门/团队对话框 */}
      <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {dialogType === 'department' ? '添加部门' : '添加团队'}
        </DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                label="名称"
                fullWidth
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>类型</InputLabel>
                <Select
                  label="类型"
                  defaultValue=""
                >
                  {dialogType === 'department'
                    ? departmentTypes.map(type => (
                        <MenuItem key={type} value={type}>{type}</MenuItem>
                      ))
                    : teamTypes.map(type => (
                        <MenuItem key={type} value={type}>{type}</MenuItem>
                      ))
                  }
                </Select>
              </FormControl>
            </Grid>
            {dialogType === 'team' && (
              <>
                <Grid item xs={12}>
                  <TextField
                    label="团队负责人"
                    fullWidth
                  />
                </Grid>
                <Grid item xs={12}>
                  <TextField
                    label="成员数量"
                    type="number"
                    fullWidth
                  />
                </Grid>
              </>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>取消</Button>
          <Button onClick={handleSave} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>

      {/* 详细信息对话框 */}
      <Dialog open={detailsOpen} onClose={handleCloseDialog} maxWidth="md" fullWidth>
        <DialogTitle>
          {selectedNodeDetails?.name}
        </DialogTitle>
        <DialogContent>
          {selectedNodeDetails && (
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Typography variant="subtitle1" gutterBottom>
                  基本信息
                </Typography>
                <Divider sx={{ mb: 2 }} />
                {selectedNodeDetails.type === 'organization' && (
                  <Box>
                    <Typography variant="body1" gutterBottom>
                      <strong>组织名称:</strong> {selectedNodeDetails.name}
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>部门数量:</strong> {selectedNodeDetails.children.length}
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>团队总数:</strong> {selectedNodeDetails.children.reduce((acc: number, dept: any) => acc + (dept.children ? dept.children.length : 0), 0)}
                    </Typography>
                  </Box>
                )}
                {selectedNodeDetails.type === 'department' && (
                  <Box>
                    <Typography variant="body1" gutterBottom>
                      <strong>部门名称:</strong> {selectedNodeDetails.name}
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>团队数量:</strong> {selectedNodeDetails.children ? selectedNodeDetails.children.length : 0}
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>下属团队:</strong>
                    </Typography>
                    {selectedNodeDetails.children && selectedNodeDetails.children.map((team: any) => (
                      <Chip 
                        key={team.id}
                        label={team.name}
                        sx={{ mr: 1, mb: 1 }}
                      />
                    ))}
                  </Box>
                )}
                {selectedNodeDetails.type === 'team' && (
                  <Box>
                    <Typography variant="body1" gutterBottom>
                      <strong>团队名称:</strong> {selectedNodeDetails.name}
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>团队成员:</strong> {selectedNodeDetails.members}人
                    </Typography>
                    <Typography variant="body1" gutterBottom>
                      <strong>团队负责人:</strong> {selectedNodeDetails.leader}
                    </Typography>
                  </Box>
                )}
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>关闭</Button>
          <Button 
            variant="outlined" 
            color="primary"
            startIcon={<EditIcon />}
          >
            编辑
          </Button>
          {selectedNodeDetails && selectedNodeDetails.type !== 'organization' && (
            <Button 
              variant="outlined" 
              color="error"
              startIcon={<DeleteIcon />}
            >
              删除
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default OrganizationManagement; 