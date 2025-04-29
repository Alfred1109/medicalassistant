import React from 'react';
const { useState, useRef } = React;
import {
  Box,
  Paper,
  Alert,
  CircularProgress,
  Typography,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Button
} from '@mui/material';

// 导入子组件
import ReportHeader from './ReportHeader';
import BasicInfo from './BasicInfo';
import PersonalInfo from './PersonalInfo';
import AssessmentMetrics from './AssessmentMetrics';
import TrainingProgress from './TrainingProgress';
import RecommendationSection from './RecommendationSection';

// 类型定义
export interface Patient {
  id: string;
  name: string;
  age: number;
  gender: string;
  medicalId: string;
  contact: string;
}

export interface Doctor {
  id: string;
  name: string;
  department: string;
  title: string;
  contact: string;
}

export interface RehabPlan {
  id: string;
  title: string;
  description: string;
  startDate: string;
  endDate?: string;
  status: 'active' | 'completed' | 'canceled' | 'paused';
  createdBy: string;
  exercises: RehabExercise[];
  targetConditions: string[];
}

export interface RehabExercise {
  id: string;
  name: string;
  description?: string;
  sets: number;
  repetitions: number;
  duration?: number;
  frequency: string[];
  completed: boolean;
  completionDate?: string;
  progress: number;
}

export interface AssessmentMetric {
  name: string;
  initialValue: number;
  currentValue: number;
  targetValue: number;
  unit: string;
  improvement: number;
  improvementPercentage: number;
  trend: 'up' | 'down' | 'flat';
  isPositiveTrend: boolean;
}

export interface RehabAssessmentReportProps {
  patient: Patient;
  doctor: Doctor;
  plan: RehabPlan;
  assessmentDate: string;
  metrics: AssessmentMetric[];
  loading?: boolean;
  error?: string;
}

/**
 * 康复评估报告组件
 * 提供详细的康复计划进展评估，包括患者信息、计划信息、评估指标、进展趋势和建议
 */
const RehabAssessmentReport: React.FC<RehabAssessmentReportProps> = ({
  patient,
  doctor,
  plan,
  assessmentDate,
  metrics,
  loading = false,
  error
}) => {
  const reportRef = useRef<HTMLDivElement>(null);
  const [isPrintDialogOpen, setIsPrintDialogOpen] = useState(false);
  
  // 处理打印功能
  const handlePrint = () => {
    setIsPrintDialogOpen(true);
  };
  
  // 处理导出PDF功能
  const handleExport = () => {
    // 实际开发中需要集成PDF导出库，这里仅作为示例
    alert('导出PDF功能待实现');
  };
  
  // 处理分享功能
  const handleShare = () => {
    // 分享功能实现
    alert('分享功能待实现');
  };
  
  // 如果正在加载，显示加载指示器
  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '300px' }}>
        <CircularProgress />
        <Typography variant="h6" sx={{ ml: 2 }}>
          正在生成评估报告...
        </Typography>
      </Box>
    );
  }
  
  // 如果有错误，显示错误信息
  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        {error}
      </Alert>
    );
  }
  
  return (
    <Paper 
      ref={reportRef}
      elevation={0} 
      variant="outlined" 
      sx={{ 
        p: 3, 
        mb: 3,
        position: 'relative',
        borderRadius: 2,
        overflow: 'hidden'
      }}
    >
      {/* 报告头部 */}
      <ReportHeader 
        onPrint={handlePrint} 
        onExport={handleExport} 
        onShare={handleShare} 
      />
      
      {/* 报告基本信息 */}
      <BasicInfo 
        plan={plan} 
        assessmentDate={assessmentDate} 
      />
      
      {/* 患者和医生信息 */}
      <PersonalInfo 
        patient={patient} 
        doctor={doctor} 
      />
      
      {/* 评估指标 */}
      <AssessmentMetrics 
        metrics={metrics} 
        assessmentDate={assessmentDate} 
      />
      
      {/* 康复训练完成情况 */}
      <TrainingProgress 
        plan={plan} 
      />
      
      {/* 评估建议 */}
      <RecommendationSection 
        patient={patient} 
        plan={plan} 
        metrics={metrics} 
      />
      
      {/* 打印确认对话框 */}
      <Dialog
        open={isPrintDialogOpen}
        onClose={() => setIsPrintDialogOpen(false)}
      >
        <DialogTitle>打印确认</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            确定要打印康复评估报告吗？
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            报告将以PDF格式生成，并打开打印对话框。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIsPrintDialogOpen(false)}>
            取消
          </Button>
          <Button 
            variant="contained" 
            onClick={() => {
              setIsPrintDialogOpen(false);
              window.print();
            }}
          >
            确认打印
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default RehabAssessmentReport; 