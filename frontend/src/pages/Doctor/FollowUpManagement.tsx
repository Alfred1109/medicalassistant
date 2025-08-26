import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Divider,
  Snackbar,
  Alert
} from '@mui/material';

// 导入组件
import FollowUpList from '../../components/HealthManager/FollowUpList';
import FollowUpForm from '../../components/HealthManager/FollowUpForm';

// 模拟数据
const mockFollowUps = [
  {
    id: '1',
    patient_id: '1001',
    patient_name: '张三',
    follow_up_type: 'onsite',
    scheduled_date: '2023-05-15T10:00:00Z',
    actual_date: null,
    status: 'scheduled',
    notes: '检查康复进展，评估治疗效果',
    created_by: 'doctor1',
    created_at: '2023-04-20T14:30:00Z',
    updated_at: '2023-04-20T14:30:00Z'
  },
  {
    id: '2',
    patient_id: '1002',
    patient_name: '李四',
    follow_up_type: 'phone',
    scheduled_date: '2023-04-25T15:30:00Z',
    actual_date: '2023-04-25T15:35:00Z',
    status: 'completed',
    notes: '电话随访，了解患者恢复情况',
    created_by: 'doctor1',
    created_at: '2023-04-10T09:15:00Z',
    updated_at: '2023-04-25T16:00:00Z'
  },
  {
    id: '3',
    patient_id: '1003',
    patient_name: '王五',
    follow_up_type: 'online',
    scheduled_date: '2023-04-28T14:00:00Z',
    actual_date: null,
    status: 'canceled',
    notes: '患者因个人原因取消',
    created_by: 'doctor1',
    created_at: '2023-04-15T11:20:00Z',
    updated_at: '2023-04-26T10:10:00Z'
  },
  {
    id: '4',
    patient_id: '1004',
    patient_name: '赵六',
    follow_up_type: 'home_visit',
    scheduled_date: '2023-05-20T09:00:00Z',
    actual_date: null,
    status: 'scheduled',
    notes: '家庭访视，评估家庭康复环境',
    created_by: 'doctor1',
    created_at: '2023-04-22T16:45:00Z',
    updated_at: '2023-04-22T16:45:00Z'
  },
  {
    id: '5',
    patient_id: '1005',
    patient_name: '孙七',
    follow_up_type: 'remote_monitoring',
    scheduled_date: '2023-04-10T10:00:00Z',
    actual_date: null,
    status: 'scheduled',
    notes: '远程监测患者血压、血糖指标',
    created_by: 'doctor1',
    created_at: '2023-04-05T13:30:00Z',
    updated_at: '2023-04-05T13:30:00Z'
  }
];

const FollowUpManagement: React.FC = () => {
  const navigate = useNavigate();
  
  // 状态
  const [followUps, setFollowUps] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [totalCount, setTotalCount] = useState(0);
  const [filters, setFilters] = useState({});
  const [showForm, setShowForm] = useState(false);
  const [currentFollowUp, setCurrentFollowUp] = useState<any>(null);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: '',
    severity: 'success' as 'success' | 'error' | 'info' | 'warning'
  });
  
  // 加载随访记录
  useEffect(() => {
    loadFollowUps();
  }, [page, pageSize, filters]);
  
  // 加载随访记录（模拟API调用）
  const loadFollowUps = async () => {
    try {
      setLoading(true);
      
      // 模拟API延迟
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 模拟过滤和分页
      let filteredData = [...mockFollowUps];
      
      // 按状态过滤
      if (filters.status) {
        filteredData = filteredData.filter(item => item.status === filters.status);
      }
      
      // 按类型过滤
      if (filters.follow_up_type) {
        filteredData = filteredData.filter(item => item.follow_up_type === filters.follow_up_type);
      }
      
      // 按患者名称过滤
      if (filters.patient_name) {
        filteredData = filteredData.filter(item => 
          item.patient_name.toLowerCase().includes(filters.patient_name.toLowerCase())
        );
      }
      
      // 计算总数
      setTotalCount(filteredData.length);
      
      // 分页
      const paginatedData = filteredData.slice(
        page * pageSize,
        (page + 1) * pageSize
      );
      
      setFollowUps(paginatedData);
      setError(null);
    } catch (err) {
      setError('加载随访记录失败');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理添加随访
  const handleAddFollowUp = () => {
    setCurrentFollowUp(null);
    setFormMode('create');
    setShowForm(true);
  };
  
  // 处理编辑随访
  const handleEditFollowUp = (id: string) => {
    const followUp = followUps.find(item => item.id === id);
    if (followUp) {
      setCurrentFollowUp(followUp);
      setFormMode('edit');
      setShowForm(true);
    }
  };
  
  // 处理完成随访
  const handleCompleteFollowUp = async (id: string) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 更新本地数据
      setFollowUps(prevFollowUps => 
        prevFollowUps.map(item => 
          item.id === id 
            ? { 
                ...item, 
                status: 'completed',
                actual_date: new Date().toISOString(),
                updated_at: new Date().toISOString()
              } 
            : item
        )
      );
      
      // 显示成功消息
      setSnackbar({
        open: true,
        message: '随访已标记为完成',
        severity: 'success'
      });
    } catch (err) {
      setSnackbar({
        open: true,
        message: '操作失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理取消随访
  const handleCancelFollowUp = async (id: string) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 更新本地数据
      setFollowUps(prevFollowUps => 
        prevFollowUps.map(item => 
          item.id === id 
            ? { 
                ...item, 
                status: 'canceled',
                updated_at: new Date().toISOString()
              } 
            : item
        )
      );
      
      // 显示成功消息
      setSnackbar({
        open: true,
        message: '随访已取消',
        severity: 'success'
      });
    } catch (err) {
      setSnackbar({
        open: true,
        message: '操作失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理重新安排随访
  const handleRescheduleFollowUp = (id: string) => {
    // 在实际应用中，这里会打开一个重新安排日期的对话框
    // 简化起见，我们直接导航到编辑页面
    handleEditFollowUp(id);
  };
  
  // 处理删除随访
  const handleDeleteFollowUp = async (id: string) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // 更新本地数据
      setFollowUps(prevFollowUps => 
        prevFollowUps.filter(item => item.id !== id)
      );
      
      // 显示成功消息
      setSnackbar({
        open: true,
        message: '随访已删除',
        severity: 'success'
      });
    } catch (err) {
      setSnackbar({
        open: true,
        message: '操作失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 处理表单提交
  const handleFormSubmit = async (data: any) => {
    try {
      setLoading(true);
      
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 500));
      
      if (formMode === 'create') {
        // 创建新随访
        const newFollowUp = {
          id: `${Date.now()}`, // 模拟ID生成
          ...data,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          status: 'scheduled'
        };
        
        // 更新本地数据
        setFollowUps(prevFollowUps => [newFollowUp, ...prevFollowUps]);
        
        // 显示成功消息
        setSnackbar({
          open: true,
          message: '随访创建成功',
          severity: 'success'
        });
      } else {
        // 更新随访
        setFollowUps(prevFollowUps => 
          prevFollowUps.map(item => 
            item.id === currentFollowUp.id 
              ? { 
                  ...item, 
                  ...data,
                  updated_at: new Date().toISOString()
                } 
              : item
          )
        );
        
        // 显示成功消息
        setSnackbar({
          open: true,
          message: '随访更新成功',
          severity: 'success'
        });
      }
      
      // 关闭表单
      setShowForm(false);
    } catch (err) {
      setSnackbar({
        open: true,
        message: '操作失败',
        severity: 'error'
      });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };
  
  // 关闭提示消息
  const handleCloseSnackbar = () => {
    setSnackbar({ ...snackbar, open: false });
  };
  
  return (
    <Box>
      <Typography variant="h5" gutterBottom>
        随访管理
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        管理患者随访计划，查看、编辑和安排新的随访。
      </Typography>
      <Divider sx={{ mb: 3 }} />
      
      {showForm ? (
        <FollowUpForm
          followUp={currentFollowUp}
          onSave={handleFormSubmit}
          onCancel={() => setShowForm(false)}
          mode={formMode}
          loading={loading}
        />
      ) : (
        <FollowUpList
          records={followUps}
          loading={loading}
          error={error || undefined}
          totalCount={totalCount}
          page={page}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
          onAdd={handleAddFollowUp}
          onEdit={handleEditFollowUp}
          onComplete={handleCompleteFollowUp}
          onCancel={handleCancelFollowUp}
          onReschedule={handleRescheduleFollowUp}
          onDelete={handleDeleteFollowUp}
          onFilterChange={setFilters}
          onRefresh={loadFollowUps}
          currentFilters={filters}
        />
      )}
      
      {/* 提示消息 */}
      <Snackbar 
        open={snackbar.open} 
        autoHideDuration={5000} 
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={handleCloseSnackbar} 
          severity={snackbar.severity}
          variant="filled"
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default FollowUpManagement; 