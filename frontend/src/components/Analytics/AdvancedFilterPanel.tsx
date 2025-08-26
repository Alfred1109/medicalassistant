import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  Chip,
  IconButton,
  Divider,
  Switch,
  FormControlLabel,
  Collapse,
  List,
  ListItem,
  ListItemText,
  Slider,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tooltip
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  FilterList as FilterListIcon,
  Save as SaveIcon,
  PlaylistAdd as PlaylistAddIcon,
  ArrowForward as ArrowForwardIcon
} from '@mui/icons-material';

// 过滤条件类型
export interface FilterCondition {
  id: string;
  field: string;
  operator: string;
  value: any;
  type: 'string' | 'number' | 'date' | 'boolean';
  logic?: 'AND' | 'OR';
}

// 预设过滤器类型
export interface SavedFilter {
  id: string;
  name: string;
  description?: string;
  conditions: FilterCondition[];
  createdAt: Date;
  global?: boolean;
}

// 组件属性
interface AdvancedFilterPanelProps {
  availableFields: Array<{
    name: string;
    label: string;
    type: 'string' | 'number' | 'date' | 'boolean';
    options?: any[];
  }>;
  onApplyFilter: (conditions: FilterCondition[]) => void;
  savedFilters?: SavedFilter[];
  onSaveFilter?: (filter: Omit<SavedFilter, 'id' | 'createdAt'>) => Promise<void>;
  defaultExpanded?: boolean;
  maxHeight?: number | string;
  loading?: boolean;
}

/**
 * 高级过滤面板组件
 * 支持多条件过滤、保存过滤器、加载预设过滤器等功能
 */
const AdvancedFilterPanel: React.FC<AdvancedFilterPanelProps> = ({
  availableFields,
  onApplyFilter,
  savedFilters = [],
  onSaveFilter,
  defaultExpanded = false,
  maxHeight = 400,
  loading = false
}) => {
  // 状态
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [conditions, setConditions] = useState<FilterCondition[]>([]);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [filterName, setFilterName] = useState('');
  const [filterDescription, setFilterDescription] = useState('');
  const [isGlobalFilter, setIsGlobalFilter] = useState(false);
  const [activeFilterId, setActiveFilterId] = useState<string | null>(null);

  // 运算符选项
  const getOperators = (type: string) => {
    switch (type) {
      case 'string':
        return [
          { value: 'equals', label: '等于' },
          { value: 'contains', label: '包含' },
          { value: 'startsWith', label: '开头是' },
          { value: 'endsWith', label: '结尾是' },
          { value: 'notEquals', label: '不等于' },
          { value: 'isEmpty', label: '为空' },
          { value: 'isNotEmpty', label: '不为空' }
        ];
      case 'number':
        return [
          { value: 'equals', label: '等于' },
          { value: 'greaterThan', label: '大于' },
          { value: 'lessThan', label: '小于' },
          { value: 'greaterOrEqual', label: '大于等于' },
          { value: 'lessOrEqual', label: '小于等于' },
          { value: 'between', label: '介于' },
          { value: 'notEquals', label: '不等于' }
        ];
      case 'date':
        return [
          { value: 'equals', label: '等于' },
          { value: 'before', label: '早于' },
          { value: 'after', label: '晚于' },
          { value: 'between', label: '介于' },
          { value: 'isEmpty', label: '为空' },
          { value: 'isNotEmpty', label: '不为空' }
        ];
      case 'boolean':
        return [
          { value: 'equals', label: '等于' },
          { value: 'notEquals', label: '不等于' }
        ];
      default:
        return [
          { value: 'equals', label: '等于' },
          { value: 'notEquals', label: '不等于' }
        ];
    }
  };

  // 添加条件
  const handleAddCondition = () => {
    if (availableFields.length === 0) return;
    
    const firstField = availableFields[0];
    const newCondition: FilterCondition = {
      id: `condition-${Date.now()}`,
      field: firstField.name,
      operator: getOperators(firstField.type)[0].value,
      value: '',
      type: firstField.type,
      logic: conditions.length > 0 ? 'AND' : undefined
    };
    
    setConditions([...conditions, newCondition]);
  };

  // 移除条件
  const handleRemoveCondition = (id: string) => {
    const updatedConditions = conditions.filter(c => c.id !== id);
    
    // 处理第一个条件的逻辑运算符
    if (updatedConditions.length > 0) {
      updatedConditions[0].logic = undefined;
    }
    
    setConditions(updatedConditions);
    
    // 如果删除了全部条件，清除活动过滤器
    if (updatedConditions.length === 0) {
      setActiveFilterId(null);
    }
  };

  // 更新条件
  const handleUpdateCondition = (id: string, field: string, value: any) => {
    const updatedConditions = conditions.map(condition => {
      if (condition.id !== id) return condition;
      
      // 如果更改了字段，重置运算符和值
      if (field === 'field') {
        const fieldType = availableFields.find(f => f.name === value)?.type || 'string';
        return {
          ...condition,
          field: value,
          type: fieldType,
          operator: getOperators(fieldType)[0].value,
          value: ''
        };
      }
      
      // 如果更改了操作符，可能需要重置值
      if (field === 'operator') {
        if (['isEmpty', 'isNotEmpty'].includes(value)) {
          return { ...condition, [field]: value, value: '' };
        }
        if (value === 'between' && !Array.isArray(condition.value)) {
          return { ...condition, [field]: value, value: [0, 100] };
        }
        if (value !== 'between' && Array.isArray(condition.value)) {
          return { ...condition, [field]: value, value: '' };
        }
      }
      
      return { ...condition, [field]: value };
    });
    
    setConditions(updatedConditions);
    
    // 如果修改了条件，清除活动过滤器
    setActiveFilterId(null);
  };

  // 应用过滤条件
  const handleApplyFilter = () => {
    onApplyFilter(conditions);
  };

  // 保存过滤器
  const handleSaveFilter = async () => {
    if (!onSaveFilter || !filterName || conditions.length === 0) return;
    
    try {
      await onSaveFilter({
        name: filterName,
        description: filterDescription,
        conditions: conditions,
        global: isGlobalFilter
      });
      
      // 重置表单
      setFilterName('');
      setFilterDescription('');
      setIsGlobalFilter(false);
      setShowSaveDialog(false);
    } catch (error) {
      console.error('保存过滤器失败:', error);
    }
  };

  // 加载保存的过滤器
  const handleLoadFilter = (filter: SavedFilter) => {
    setConditions(filter.conditions);
    setActiveFilterId(filter.id);
  };

  // 清除过滤器
  const handleClearFilter = () => {
    setConditions([]);
    setActiveFilterId(null);
  };

  // 渲染条件值输入
  const renderValueInput = (condition: FilterCondition) => {
    const field = availableFields.find(f => f.name === condition.field);
    
    // 空值操作符不需要值输入
    if (['isEmpty', 'isNotEmpty'].includes(condition.operator)) {
      return null;
    }
    
    // 根据字段类型渲染不同的输入控件
    switch (condition.type) {
      case 'string':
        if (field?.options) {
          return (
            <FormControl fullWidth size="small" sx={{ mt: 1 }}>
              <InputLabel>值</InputLabel>
              <Select
                value={condition.value || ''}
                onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value)}
                label="值"
              >
                {field.options.map(option => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          );
        }
        return (
          <TextField
            fullWidth
            size="small"
            label="值"
            value={condition.value || ''}
            onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value)}
            margin="normal"
          />
        );
      
      case 'number':
        if (condition.operator === 'between') {
          const value = Array.isArray(condition.value) ? condition.value : [0, 100];
          return (
            <Box sx={{ width: '100%', mt: 2, px: 2 }}>
              <Slider
                value={value}
                onChange={(_, newValue) => handleUpdateCondition(condition.id, 'value', newValue)}
                valueLabelDisplay="auto"
                aria-labelledby="range-slider"
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                <TextField
                  size="small"
                  type="number"
                  label="最小值"
                  value={value[0]}
                  onChange={(e) => {
                    const newValue = [...value];
                    newValue[0] = Number(e.target.value);
                    handleUpdateCondition(condition.id, 'value', newValue);
                  }}
                  sx={{ width: '48%' }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="最大值"
                  value={value[1]}
                  onChange={(e) => {
                    const newValue = [...value];
                    newValue[1] = Number(e.target.value);
                    handleUpdateCondition(condition.id, 'value', newValue);
                  }}
                  sx={{ width: '48%' }}
                />
              </Box>
            </Box>
          );
        }
        return (
          <TextField
            fullWidth
            size="small"
            type="number"
            label="值"
            value={condition.value || ''}
            onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value ? Number(e.target.value) : '')}
            margin="normal"
          />
        );
      
      case 'date':
        if (condition.operator === 'between') {
          return (
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              <TextField
                size="small"
                type="date"
                label="起始日期"
                value={(condition.value && condition.value[0]) || ''}
                onChange={(e) => {
                  const newValue = Array.isArray(condition.value) ? [...condition.value] : ['', ''];
                  newValue[0] = e.target.value;
                  handleUpdateCondition(condition.id, 'value', newValue);
                }}
                InputLabelProps={{ shrink: true }}
                sx={{ width: '48%' }}
              />
              <TextField
                size="small"
                type="date"
                label="结束日期"
                value={(condition.value && condition.value[1]) || ''}
                onChange={(e) => {
                  const newValue = Array.isArray(condition.value) ? [...condition.value] : ['', ''];
                  newValue[1] = e.target.value;
                  handleUpdateCondition(condition.id, 'value', newValue);
                }}
                InputLabelProps={{ shrink: true }}
                sx={{ width: '48%' }}
              />
            </Box>
          );
        }
        return (
          <TextField
            fullWidth
            size="small"
            type="date"
            label="日期"
            value={condition.value || ''}
            onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value)}
            margin="normal"
            InputLabelProps={{ shrink: true }}
          />
        );
      
      case 'boolean':
        return (
          <FormControl fullWidth size="small" sx={{ mt: 1 }}>
            <InputLabel>值</InputLabel>
            <Select
              value={condition.value === '' ? '' : Boolean(condition.value)}
              onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value)}
              label="值"
            >
              <MenuItem value={true}>是</MenuItem>
              <MenuItem value={false}>否</MenuItem>
            </Select>
          </FormControl>
        );
      
      default:
        return (
          <TextField
            fullWidth
            size="small"
            label="值"
            value={condition.value || ''}
            onChange={(e) => handleUpdateCondition(condition.id, 'value', e.target.value)}
            margin="normal"
          />
        );
    }
  };

  // 渲染保存的过滤器列表
  const renderSavedFilters = () => {
    if (savedFilters.length === 0) {
      return (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
          没有保存的过滤器
        </Typography>
      );
    }
    
    return (
      <List dense sx={{ maxHeight: 200, overflow: 'auto' }}>
        {savedFilters.map(filter => (
          <ListItem 
            key={filter.id}
            secondaryAction={
              <IconButton 
                edge="end" 
                size="small"
                onClick={() => handleLoadFilter(filter)}
                color={activeFilterId === filter.id ? 'primary' : 'default'}
              >
                <ArrowForwardIcon />
              </IconButton>
            }
            sx={{ 
              bgcolor: activeFilterId === filter.id ? 'action.selected' : 'transparent',
              borderRadius: 1
            }}
          >
            <ListItemText 
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {filter.name}
                  {filter.global && (
                    <Chip label="全局" size="small" sx={{ ml: 1 }} />
                  )}
                </Box>
              }
              secondary={filter.description || `${filter.conditions.length} 个条件`}
            />
          </ListItem>
        ))}
      </List>
    );
  };

  // 渲染条件卡片
  const renderConditionCard = (condition: FilterCondition, index: number) => {
    const fieldOptions = availableFields.map(field => ({
      value: field.name,
      label: field.label
    }));
    
    const operatorOptions = getOperators(condition.type);
    
    return (
      <Paper
        key={condition.id}
        sx={{
          p: 2,
          mt: index > 0 ? 2 : 0,
          position: 'relative',
          border: '1px solid',
          borderColor: 'divider'
        }}
        variant="outlined"
      >
        {/* 逻辑操作符选择 */}
        {index > 0 && (
          <Box sx={{ position: 'absolute', top: -15, left: 16, bgcolor: 'background.paper', px: 1 }}>
            <FormControl size="small">
              <Select
                value={condition.logic || 'AND'}
                onChange={(e) => handleUpdateCondition(condition.id, 'logic', e.target.value)}
                sx={{ minWidth: 80, height: 30, fontSize: '0.75rem' }}
              >
                <MenuItem value="AND">AND</MenuItem>
                <MenuItem value="OR">OR</MenuItem>
              </Select>
            </FormControl>
          </Box>
        )}
        
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>字段</InputLabel>
              <Select
                value={condition.field}
                onChange={(e) => handleUpdateCondition(condition.id, 'field', e.target.value)}
                label="字段"
              >
                {fieldOptions.map(option => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>运算符</InputLabel>
              <Select
                value={condition.operator}
                onChange={(e) => handleUpdateCondition(condition.id, 'operator', e.target.value)}
                label="运算符"
              >
                {operatorOptions.map(option => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          
          <Grid item xs={10} sm={3}>
            {renderValueInput(condition)}
          </Grid>
          
          <Grid item xs={2} sm={1} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <IconButton
              onClick={() => handleRemoveCondition(condition.id)}
              size="small"
              color="error"
            >
              <DeleteIcon />
            </IconButton>
          </Grid>
        </Grid>
      </Paper>
    );
  };

  // 渲染保存过滤器对话框
  const renderSaveDialog = () => (
    <Dialog open={showSaveDialog} onClose={() => setShowSaveDialog(false)} maxWidth="sm" fullWidth>
      <DialogTitle>保存过滤器</DialogTitle>
      <DialogContent>
        <TextField
          fullWidth
          label="过滤器名称"
          value={filterName}
          onChange={(e) => setFilterName(e.target.value)}
          margin="normal"
          required
          error={filterName === ''}
          helperText={filterName === '' ? '请输入名称' : ''}
        />
        <TextField
          fullWidth
          label="描述"
          value={filterDescription}
          onChange={(e) => setFilterDescription(e.target.value)}
          margin="normal"
          multiline
          rows={2}
        />
        <FormControlLabel
          control={
            <Switch
              checked={isGlobalFilter}
              onChange={(e) => setIsGlobalFilter(e.target.checked)}
            />
          }
          label="设为全局过滤器（所有用户可见）"
          sx={{ mt: 1 }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setShowSaveDialog(false)}>取消</Button>
        <Button 
          onClick={handleSaveFilter} 
          variant="contained" 
          disabled={!filterName || conditions.length === 0}
        >
          保存
        </Button>
      </DialogActions>
    </Dialog>
  );

  return (
    <Paper sx={{ mb: 3, overflow: 'hidden' }}>
      {/* 头部 */}
      <Box 
        sx={{ 
          p: 2, 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          borderBottom: expanded ? '1px solid' : 'none',
          borderColor: 'divider'
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <FilterListIcon sx={{ mr: 1 }} />
          <Typography variant="subtitle1" fontWeight="medium">
            高级过滤
          </Typography>
          {conditions.length > 0 && (
            <Chip 
              label={`${conditions.length} 个条件`} 
              size="small" 
              sx={{ ml: 2 }}
              color="primary"
              variant="outlined"
            />
          )}
        </Box>
        <Box>
          <FormControlLabel
            control={
              <Switch
                checked={expanded}
                onChange={() => setExpanded(!expanded)}
                size="small"
              />
            }
            label={expanded ? "收起" : "展开"}
            labelPlacement="start"
          />
        </Box>
      </Box>
      
      {/* 内容 */}
      <Collapse in={expanded}>
        <Box 
          sx={{ 
            p: 2, 
            maxHeight: maxHeight, 
            overflow: 'auto',
            borderBottom: '1px solid',
            borderColor: 'divider'
          }}
        >
          {/* 条件列表 */}
          <Box sx={{ mb: 2 }}>
            {conditions.map((condition, index) => renderConditionCard(condition, index))}
            
            {conditions.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                点击"添加条件"按钮开始创建过滤条件
              </Typography>
            )}
          </Box>
          
          {/* 添加条件按钮 */}
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={handleAddCondition}
              size="small"
            >
              添加条件
            </Button>
          </Box>
          
          {/* 保存的过滤器 */}
          {savedFilters.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="subtitle2" gutterBottom>
                保存的过滤器
              </Typography>
              <Divider sx={{ mb: 1 }} />
              {renderSavedFilters()}
            </Box>
          )}
        </Box>
        
        {/* 底部操作栏 */}
        <Box 
          sx={{ 
            p: 2, 
            display: 'flex', 
            justifyContent: 'space-between',
            bgcolor: 'action.hover'
          }}
        >
          <Box>
            <Button
              variant="outlined"
              color="inherit"
              onClick={handleClearFilter}
              size="small"
              disabled={conditions.length === 0}
              sx={{ mr: 1 }}
            >
              清除
            </Button>
            
            {onSaveFilter && (
              <Button
                variant="outlined"
                startIcon={<SaveIcon />}
                onClick={() => setShowSaveDialog(true)}
                size="small"
                disabled={conditions.length === 0}
              >
                保存过滤器
              </Button>
            )}
          </Box>
          
          <Button
            variant="contained"
            onClick={handleApplyFilter}
            size="small"
            disabled={conditions.length === 0 || loading}
            startIcon={loading ? <CircularProgress size={16} /> : <FilterListIcon />}
          >
            应用过滤器
          </Button>
        </Box>
      </Collapse>
      
      {/* 保存对话框 */}
      {renderSaveDialog()}
    </Paper>
  );
};

export default AdvancedFilterPanel; 