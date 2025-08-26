import React from 'react';
import { Box, Typography, Container, Paper, Button, Grid } from '@mui/material';
import FeatureUnderDevelopment from '../../components/common/FeatureUnderDevelopment';

/**
 * 功能开发中组件示例页面
 */
const FeatureDemoPage: React.FC = () => {
  const [showDemo1, setShowDemo1] = React.useState(false);
  const [showDemo2, setShowDemo2] = React.useState(false);
  const [showDemo3, setShowDemo3] = React.useState(false);

  // 重置所有演示
  const resetAll = () => {
    setShowDemo1(false);
    setShowDemo2(false);
    setShowDemo3(false);
  };

  // 如果正在显示演示，则展示相应的组件
  if (showDemo1) {
    return (
      <FeatureUnderDevelopment 
        featureName="智能患者管理" 
        returnButtonText="返回演示页" 
        returnPath="/app/feature-demo"
        estimatedCompletion="2023年12月30日"
      />
    );
  }

  if (showDemo2) {
    return (
      <FeatureUnderDevelopment 
        featureName="远程康复训练" 
        description="远程康复训练功能将允许医生通过视频连接指导患者完成康复训练。这一功能正在开发中，我们正在优化视频流传输和实时反馈系统。"
        returnButtonText="返回演示页" 
        returnPath="/app/feature-demo"
        additionalInfo="我们正在测试多种视频编解码器，以确保在不同网络条件下的最佳性能。"
      />
    );
  }

  if (showDemo3) {
    return (
      <FeatureUnderDevelopment 
        featureName="AI辅助诊断" 
        description="AI辅助诊断功能将使用人工智能分析患者数据，提供诊断建议和治疗方案推荐。"
        returnButtonText="返回演示页" 
        returnPath="/app/feature-demo"
        estimatedCompletion="2024年第一季度"
        additionalInfo="该功能将支持多种常见康复疾病的诊断，并与电子病历系统集成。"
      />
    );
  }

  // 主页面
  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Paper sx={{ p: 4, mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          功能开发中组件演示
        </Typography>
        <Typography variant="body1" paragraph>
          这个页面展示了"功能开发中"组件的不同配置和使用方式。点击下面的按钮查看不同的示例。
        </Typography>

        <Grid container spacing={3} sx={{ mt: 2 }}>
          <Grid item xs={12} md={4}>
            <Paper 
              elevation={2} 
              sx={{ 
                p: 3, 
                height: '100%', 
                display: 'flex', 
                flexDirection: 'column',
                border: '1px solid #e0e0e0'
              }}
            >
              <Typography variant="h6" gutterBottom>
                基础示例
              </Typography>
              <Typography variant="body2" sx={{ mb: 2, flex: 1 }}>
                基本的"功能开发中"组件，包含功能名称和预计完成时间。
              </Typography>
              <Button 
                variant="contained" 
                color="primary" 
                onClick={() => setShowDemo1(true)}
              >
                查看示例
              </Button>
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={4}>
            <Paper 
              elevation={2} 
              sx={{ 
                p: 3, 
                height: '100%', 
                display: 'flex', 
                flexDirection: 'column',
                border: '1px solid #e0e0e0'
              }}
            >
              <Typography variant="h6" gutterBottom>
                详细描述示例
              </Typography>
              <Typography variant="body2" sx={{ mb: 2, flex: 1 }}>
                包含详细功能描述和附加信息的"功能开发中"组件。
              </Typography>
              <Button 
                variant="contained" 
                color="primary" 
                onClick={() => setShowDemo2(true)}
              >
                查看示例
              </Button>
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={4}>
            <Paper 
              elevation={2} 
              sx={{ 
                p: 3, 
                height: '100%', 
                display: 'flex', 
                flexDirection: 'column',
                border: '1px solid #e0e0e0'
              }}
            >
              <Typography variant="h6" gutterBottom>
                综合示例
              </Typography>
              <Typography variant="body2" sx={{ mb: 2, flex: 1 }}>
                综合使用所有可选属性的"功能开发中"组件。
              </Typography>
              <Button 
                variant="contained" 
                color="primary" 
                onClick={() => setShowDemo3(true)}
              >
                查看示例
              </Button>
            </Paper>
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 4 }}>
        <Typography variant="h5" gutterBottom>
          组件参数说明
        </Typography>
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle1" fontWeight="bold">必填参数：</Typography>
          <ul>
            <li><Typography variant="body2">featureName: 功能名称（必填）</Typography></li>
          </ul>

          <Typography variant="subtitle1" fontWeight="bold" sx={{ mt: 2 }}>可选参数：</Typography>
          <ul>
            <li><Typography variant="body2">description: 功能描述，默认为"该功能正在紧张开发中，请稍后再访问。"</Typography></li>
            <li><Typography variant="body2">estimatedCompletion: 预计完成时间，如不提供则不显示</Typography></li>
            <li><Typography variant="body2">returnPath: 返回按钮的跳转路径，默认为"/"</Typography></li>
            <li><Typography variant="body2">returnButtonText: 返回按钮文本，默认为"返回"</Typography></li>
            <li><Typography variant="body2">additionalInfo: 附加信息，如不提供则不显示</Typography></li>
          </ul>
        </Box>

        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            使用示例代码：
          </Typography>
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 2, 
              backgroundColor: '#f5f5f5',
              fontFamily: 'monospace',
              fontSize: '0.9rem',
              overflow: 'auto'
            }}
          >
            {`
<FeatureUnderDevelopment 
  featureName="智能患者管理" 
  description="自定义描述文本..."
  estimatedCompletion="2023年12月30日"
  returnPath="/dashboard"
  returnButtonText="返回首页"
  additionalInfo="附加说明信息..."
/>
            `}
          </Paper>
        </Box>
      </Paper>
    </Container>
  );
};

export default FeatureDemoPage; 