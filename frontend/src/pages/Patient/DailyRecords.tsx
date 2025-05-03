import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  TextField,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Divider,
  CircularProgress,
  Alert,
} from '@mui/material';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import { apiService } from '../../services/api';

interface DailyRecord {
  id: number;
  date: Date;
  painLevel: number;
  mood: string;
  sleep: string;
  exerciseCompleted: boolean;
  note: string;
}

const DailyRecords: React.FC = () => {
  const [selectedDate, setSelectedDate] = useState<Date | null>(new Date());
  const [records, setRecords] = useState<DailyRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  
  const [newRecord, setNewRecord] = useState<Partial<DailyRecord>>({
    date: new Date(),
    painLevel: 0,
    mood: '',
    sleep: '',
    exerciseCompleted: false,
    note: ''
  });
  
  const [isAdding, setIsAdding] = useState(false);
  
  // 从API获取数据
  useEffect(() => {
    const fetchRecords = async () => {
      try {
        setLoading(true);
        const response = await apiService.patient.getDailyRecords();
        
        // 将API返回的数据转换为组件所需格式
        const formattedRecords = response.data.map((record: any) => ({
          id: record.id || record._id,
          date: new Date(record.date),
          painLevel: record.pain_level || 0,
          mood: record.mood || '',
          sleep: record.sleep || '',
          exerciseCompleted: record.exercise_completed || false,
          note: record.note || ''
        }));
        
        setRecords(formattedRecords);
      } catch (err) {
        console.error('获取日常记录失败:', err);
        setError('获取日常记录时出错，请稍后再试');
        // 使用示例数据作为备用
        setRecords([
          {
            id: 1,
            date: new Date(2023, 5, 1),
            painLevel: 3,
            mood: '良好',
            sleep: '6小时',
            exerciseCompleted: true,
            note: '今天完成了所有康复训练，感觉腿部力量有所恢复。'
          },
          {
            id: 2,
            date: new Date(2023, 5, 2),
            painLevel: 2,
            mood: '很好',
            sleep: '7小时',
            exerciseCompleted: true,
            note: '今天继续训练，疼痛感有所减轻。'
          },
          {
            id: 3,
            date: new Date(2023, 5, 3),
            painLevel: 4,
            mood: '一般',
            sleep: '5小时',
            exerciseCompleted: false,
            note: '今天感觉有些疲惫，没有完成所有训练。'
          }
        ]);
      } finally {
        setLoading(false);
      }
    };
    
    fetchRecords();
  }, []);
  
  const handleAddRecord = async () => {
    if (newRecord.mood && newRecord.sleep && newRecord.note) {
      try {
        // 准备API请求数据
        const recordData = {
          date: newRecord.date?.toISOString(),
          pain_level: newRecord.painLevel,
          mood: newRecord.mood,
          sleep: newRecord.sleep,
          exercise_completed: newRecord.exerciseCompleted,
          note: newRecord.note
        };
        
        // 发送API请求
        const response = await apiService.patient.createDailyRecord(recordData);
        
        // 将新记录添加到列表
        const createdRecord: DailyRecord = {
          id: response.data.id || Date.now(),
          date: newRecord.date || new Date(),
          painLevel: newRecord.painLevel || 0,
          mood: newRecord.mood,
          sleep: newRecord.sleep,
          exerciseCompleted: newRecord.exerciseCompleted || false,
          note: newRecord.note
        };
        
        setRecords([...records, createdRecord]);
        
        // 重置表单
        setNewRecord({
          date: new Date(),
          painLevel: 0,
          mood: '',
          sleep: '',
          exerciseCompleted: false,
          note: ''
        });
        setIsAdding(false);
      } catch (err) {
        console.error('创建日常记录失败:', err);
        setError('创建记录时出错，请稍后再试');
      }
    }
  };
  
  const handleDeleteRecord = async (id: number) => {
    try {
      // 发送API请求删除记录
      await apiService.patient.deleteDailyRecord(id.toString());
      
      // 从列表中移除该记录
      setRecords(records.filter(record => record.id !== id));
    } catch (err) {
      console.error('删除日常记录失败:', err);
      setError('删除记录时出错，请稍后再试');
    }
  };
  
  const filteredRecords = selectedDate 
    ? records.filter(record => 
        record.date.getDate() === selectedDate.getDate() &&
        record.date.getMonth() === selectedDate.getMonth() &&
        record.date.getFullYear() === selectedDate.getFullYear()
      )
    : records;
  
  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" height="80vh">
        <CircularProgress />
        <Typography variant="h6" sx={{ ml: 2 }}>加载日常记录...</Typography>
      </Box>
    );
  }
  
  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Box>
        <Typography variant="h5" component="h1" gutterBottom>
          日常康复记录
        </Typography>
        
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}
        
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">我的记录</Typography>
                <Box>
                  <DatePicker
                    label="选择日期"
                    value={selectedDate}
                    onChange={(newValue) => setSelectedDate(newValue)}
                  />
                  <Button 
                    variant="contained" 
                    startIcon={<AddIcon />} 
                    sx={{ ml: 2 }}
                    onClick={() => setIsAdding(true)}
                  >
                    添加记录
                  </Button>
                </Box>
              </Box>
              
              {filteredRecords.length > 0 ? (
                <List>
                  {filteredRecords.map((record) => (
                    <React.Fragment key={record.id}>
                      <ListItem
                        secondaryAction={
                          <Box>
                            <IconButton edge="end" aria-label="edit">
                              <EditIcon />
                            </IconButton>
                            <IconButton edge="end" aria-label="delete" onClick={() => handleDeleteRecord(record.id)}>
                              <DeleteIcon />
                            </IconButton>
                          </Box>
                        }
                      >
                        <ListItemText
                          primary={`${record.date.toLocaleDateString()} 记录`}
                          secondary={
                            <Box>
                              <Typography component="span" variant="body2">
                                疼痛程度: {record.painLevel}/10 | 
                                心情: {record.mood} | 
                                睡眠: {record.sleep} | 
                                完成训练: {record.exerciseCompleted ? '是' : '否'}
                              </Typography>
                              <Typography component="p" variant="body2" sx={{ mt: 1 }}>
                                {record.note}
                              </Typography>
                            </Box>
                          }
                        />
                      </ListItem>
                      <Divider />
                    </React.Fragment>
                  ))}
                </List>
              ) : (
                <Typography>该日期没有记录</Typography>
              )}
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  记录情况
                </Typography>
                <Typography variant="body2">
                  本月已记录: {records.filter(r => r.date.getMonth() === new Date().getMonth()).length} 天
                </Typography>
                <Typography variant="body2">
                  连续记录: {records.length > 0 ? Math.min(records.length, 30) : 0} 天
                </Typography>
                <Typography variant="body2">
                  完成训练天数: {records.filter(r => r.exerciseCompleted).length} 天
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
        
        {isAdding && (
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              添加新记录
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <DatePicker
                  label="日期"
                  value={newRecord.date}
                  onChange={(newValue) => setNewRecord({...newRecord, date: newValue})}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  label="疼痛程度 (0-10)"
                  type="number"
                  InputProps={{ inputProps: { min: 0, max: 10 } }}
                  fullWidth
                  value={newRecord.painLevel}
                  onChange={(e) => setNewRecord({...newRecord, painLevel: parseInt(e.target.value)})}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  label="心情"
                  fullWidth
                  value={newRecord.mood}
                  onChange={(e) => setNewRecord({...newRecord, mood: e.target.value})}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  label="睡眠时间"
                  fullWidth
                  value={newRecord.sleep}
                  onChange={(e) => setNewRecord({...newRecord, sleep: e.target.value})}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  label="是否完成训练"
                  select
                  fullWidth
                  value={newRecord.exerciseCompleted ? "true" : "false"}
                  onChange={(e) => setNewRecord({...newRecord, exerciseCompleted: e.target.value === "true"})}
                  SelectProps={{
                    native: true
                  }}
                >
                  <option value="true">是</option>
                  <option value="false">否</option>
                </TextField>
              </Grid>
              <Grid item xs={12}>
                <TextField
                  label="备注"
                  multiline
                  rows={4}
                  fullWidth
                  value={newRecord.note}
                  onChange={(e) => setNewRecord({...newRecord, note: e.target.value})}
                />
              </Grid>
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
                  <Button 
                    variant="outlined" 
                    onClick={() => setIsAdding(false)}
                  >
                    取消
                  </Button>
                  <Button 
                    variant="contained"
                    onClick={handleAddRecord}
                    disabled={!newRecord.mood || !newRecord.sleep || !newRecord.note}
                  >
                    保存记录
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </Paper>
        )}
      </Box>
    </LocalizationProvider>
  );
};

export default DailyRecords; 