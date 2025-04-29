import React from 'react';
import { 
  Container, 
  Paper, 
  Typography, 
  Box, 
  Button, 
  Grid, 
  Divider
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import ConstructionIcon from '@mui/icons-material/Construction';
import EngineeringIcon from '@mui/icons-material/Engineering';
import BuildIcon from '@mui/icons-material/Build';
import AccessTimeIcon from '@mui/icons-material/AccessTime';

interface FeatureUnderDevelopmentProps {
  /**
   * 功能名称
   */
  featureName: string;
  
  /**
   * 功能描述
   */
  description?: string;
  
  /**
   * 预计完成时间（可选）
   */
  estimatedCompletion?: string;
  
  /**
   * 返回路径
   */
  returnPath?: string;
  
  /**
   * 返回按钮文本
   */
  returnButtonText?: string;
  
  /**
   * 附加信息（可选）
   */
  additionalInfo?: string;
  
  /**
   * 是否显示进度指示（默认为true）
   */
  showProgress?: boolean;
  
  /**
   * 进度值（0-100）
   */
  progressValue?: number;
}

/**
 * 功能开发中提示组件
 * 
 * 用于显示当前功能正在开发中的友好提示界面，提供返回按钮
 */
const FeatureUnderDevelopment: React.FC<FeatureUnderDevelopmentProps> = ({
  featureName,
  description = '该功能正在紧张开发中，请稍后再访问。',
  estimatedCompletion,
  returnPath = '/',
  returnButtonText = '返回',
  additionalInfo,
  showProgress = false,
  progressValue = 60
}) => {
  const navigate = useNavigate();
  
  // 随机选择一个图标
  const icons = [
    <ConstructionIcon key="construction" sx={{ fontSize: 80, color: '#f59e0b' }} />,
    <EngineeringIcon key="engineering" sx={{ fontSize: 80, color: '#f59e0b' }} />,
    <BuildIcon key="build" sx={{ fontSize: 80, color: '#f59e0b' }} />
  ];
  
  // 使用随机图标
  const randomIcon = React.useMemo(() => {
    const index = Math.floor(Math.random() * icons.length);
    return icons[index];
  }, []);

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper 
        elevation={3} 
        sx={{ 
          p: { xs: 3, md: 5 }, 
          borderRadius: 2,
          textAlign: 'center',
          backgroundColor: '#f8f9fa',
          border: '1px solid #e0e0e0'
        }}
      >
        <Box sx={{ mb: 4 }}>
          {randomIcon}
          
          <Typography 
            variant="h4" 
            component="h1" 
            gutterBottom 
            sx={{ 
              fontWeight: 'bold',
              color: '#333'
            }}
          >
            功能开发中
          </Typography>
          
          <Typography 
            variant="h5" 
            sx={{ 
              color: '#1976d2', 
              mb: 2,
              fontWeight: 'medium'
            }}
          >
            {featureName}
          </Typography>
          
          <Typography 
            variant="body1" 
            color="text.secondary" 
            paragraph
            sx={{ maxWidth: '80%', mx: 'auto' }}
          >
            {description}
          </Typography>
          
          {estimatedCompletion && (
            <Box 
              sx={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                my: 2,
                p: 1,
                bgcolor: 'rgba(0, 0, 0, 0.05)',
                borderRadius: 1,
                maxWidth: '60%',
                mx: 'auto'
              }}
            >
              <AccessTimeIcon sx={{ mr: 1, color: '#0288d1' }} />
              <Typography variant="body2" color="text.secondary">
                预计完成时间: <Box component="span" sx={{ fontWeight: 'medium', color: '#0288d1' }}>{estimatedCompletion}</Box>
              </Typography>
            </Box>
          )}
        </Box>
        
        {additionalInfo && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography 
              variant="body2" 
              sx={{ 
                mb: 3, 
                fontStyle: 'italic',
                color: 'text.secondary'
              }}
            >
              {additionalInfo}
            </Typography>
          </>
        )}
        
        <Button 
          variant="contained" 
          color="primary" 
          size="large"
          onClick={() => navigate(returnPath)}
          sx={{ 
            px: 4,
            py: 1,
            borderRadius: 2,
            boxShadow: 2
          }}
        >
          {returnButtonText}
        </Button>
      </Paper>
    </Container>
  );
};

export default FeatureUnderDevelopment; 