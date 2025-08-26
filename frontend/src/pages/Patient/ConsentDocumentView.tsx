import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, 
  Paper, 
  Typography, 
  Button, 
  Stepper, 
  Step, 
  StepLabel, 
  Divider, 
  CircularProgress,
  Alert,
  Container,
  Grid,
  Card,
  CardContent,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Checkbox,
  IconButton,
  Tooltip
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import PrintIcon from '@mui/icons-material/Print';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ArticleIcon from '@mui/icons-material/Article';
import AssignmentIcon from '@mui/icons-material/Assignment';

// 导入电子签名组件
import ElectronicSignature from '../../components/Patient/ElectronicSignature';
// 导入API服务
import * as consentApi from '../../services/consentService';

// 界面状态类型
type DocumentStatus = 'loading' | 'loaded' | 'signing' | 'signed' | 'error' | 'submitted';

// 知情同意文档类型
interface ConsentDocument {
  id: string;
  title: string;
  content: string;
  provider: string;
  createdAt: string;
  requirePatientSignature: boolean;
  requireGuardianSignature: boolean;
  requireWitnessSignature: boolean;
  patientName: string;
  patientId: string;
  specialClauses?: string;
  attachments?: Array<{
    id: string;
    name: string;
    url: string;
  }>;
}

// 签名记录类型
interface SignatureRecord {
  patientSignature?: string;
  guardianSignature?: string;
  witnessSignature?: string;
  patientSignedAt?: string;
  guardianSignedAt?: string;
  witnessSignedAt?: string;
  patientAcknowledgements: string[];
}

const ConsentDocumentView: React.FC = () => {
  // 获取文档ID参数
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  
  // 状态定义
  const [document, setDocument] = useState<ConsentDocument | null>(null);
  const [status, setStatus] = useState<DocumentStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [signatures, setSignatures] = useState<SignatureRecord>({
    patientSignature: undefined,
    guardianSignature: undefined,
    witnessSignature: undefined,
    patientSignedAt: undefined,
    guardianSignedAt: undefined,
    witnessSignedAt: undefined,
    patientAcknowledgements: []
  });
  const [patientConfirmations, setPatientConfirmations] = useState<string[]>([]);
  const [printDialogOpen, setPrintDialogOpen] = useState(false);
  const [guardianName, setGuardianName] = useState('');
  const [witnessName, setWitnessName] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 页面加载时获取文档
  useEffect(() => {
    const loadDocument = async () => {
      if (!documentId) {
        setError('未提供文档ID');
        setStatus('error');
        return;
      }
      
      try {
        setStatus('loading');
        // 调用API获取知情同意文档
        const response = await consentApi.getConsentDocument(documentId);
        setDocument(response);
        setStatus('loaded');
        
        // 初始化需要的确认项
        const defaultConfirmations = [
          '我已阅读并理解本知情同意书的所有内容',
          '我理解所描述的治疗/手术及其相关风险',
          '我已有机会提问并获得了满意的答复',
          '我同意接受本文件所述的治疗/手术'
        ];
        setPatientConfirmations(defaultConfirmations);
      } catch (err) {
        console.error('获取知情同意文档失败:', err);
        setError('获取文档数据失败，请稍后重试');
        setStatus('error');
      }
    };
    
    loadDocument();
  }, [documentId]);

  // 处理步骤导航
  const handleNext = () => {
    setActiveStep(prevStep => prevStep + 1);
  };

  const handleBack = () => {
    setActiveStep(prevStep => prevStep - 1);
  };

  // 处理患者签名保存
  const handlePatientSignatureSave = (signatureDataUrl: string) => {
    setSignatures({
      ...signatures,
      patientSignature: signatureDataUrl,
      patientSignedAt: new Date().toISOString()
    });
  };

  // 处理监护人签名保存
  const handleGuardianSignatureSave = (signatureDataUrl: string) => {
    setSignatures({
      ...signatures,
      guardianSignature: signatureDataUrl,
      guardianSignedAt: new Date().toISOString()
    });
  };

  // 处理见证人签名保存
  const handleWitnessSignatureSave = (signatureDataUrl: string) => {
    setSignatures({
      ...signatures,
      witnessSignature: signatureDataUrl,
      witnessSignedAt: new Date().toISOString()
    });
  };

  // 处理确认项切换
  const handleConfirmationToggle = (confirmation: string) => {
    setSignatures(prev => {
      const currentAcknowledgements = [...prev.patientAcknowledgements];
      
      if (currentAcknowledgements.includes(confirmation)) {
        return {
          ...prev,
          patientAcknowledgements: currentAcknowledgements.filter(item => item !== confirmation)
        };
      } else {
        return {
          ...prev,
          patientAcknowledgements: [...currentAcknowledgements, confirmation]
        };
      }
    });
  };

  // 检查当前步骤是否完成
  const isStepComplete = (step: number) => {
    if (step === 0) {
      // 阅读文档步骤 - 只需要浏览过就可以
      return true;
    } else if (step === 1) {
      // 确认理解步骤 - 需要勾选所有确认项
      return signatures.patientAcknowledgements.length === patientConfirmations.length;
    } else if (step === 2) {
      // 签名步骤 - 需要所有必需的签名
      let complete = !!signatures.patientSignature;
      
      if (document?.requireGuardianSignature) {
        complete = complete && !!signatures.guardianSignature && !!guardianName;
      }
      
      if (document?.requireWitnessSignature) {
        complete = complete && !!signatures.witnessSignature && !!witnessName;
      }
      
      return complete;
    }
    
    return false;
  };

  // 提交签名和同意记录
  const handleSubmit = async () => {
    if (!document || !signatures.patientSignature) return;
    
    setSubmitting(true);
    
    try {
      // 准备提交数据
      const submitData = {
        documentId: document.id,
        patientId: document.patientId,
        patientSignature: signatures.patientSignature,
        patientAcknowledgements: signatures.patientAcknowledgements,
        guardianSignature: signatures.guardianSignature,
        guardianName: guardianName,
        witnessSignature: signatures.witnessSignature,
        witnessName: witnessName,
        signedAt: new Date().toISOString()
      };
      
      // 调用API提交签名记录
      await consentApi.submitConsentSignature(submitData);
      
      setStatus('submitted');
      setActiveStep(3); // 移动到完成步骤
    } catch (err) {
      console.error('提交签名失败:', err);
      setError('提交签名记录失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  // 打印文档
  const handlePrint = () => {
    setPrintDialogOpen(false);
    
    // 准备打印内容
    setTimeout(() => {
      window.print();
    }, 500);
  };

  // 下载文档
  const handleDownload = async () => {
    if (!document) return;
    
    try {
      // 调用API下载PDF
      await consentApi.downloadConsentPdf(document.id);
    } catch (err) {
      console.error('下载文档失败:', err);
      setError('下载文档失败，请稍后重试');
    }
  };

  // 渲染步骤内容
  const getStepContent = (step: number) => {
    switch (step) {
      case 0:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              请仔细阅读以下知情同意书内容
            </Typography>
            
            <Paper 
              variant="outlined" 
              sx={{ 
                p: 3, 
                mb: 3,
                maxHeight: '60vh',
                overflowY: 'auto',
                bgcolor: '#fafafa'
              }}
            >
              <Typography variant="h5" gutterBottom align="center">
                {document?.title}
              </Typography>
              
              <Divider sx={{ my: 2 }} />
              
              <Typography variant="body1" paragraph sx={{ whiteSpace: 'pre-line' }}>
                {document?.content}
              </Typography>
              
              {document?.specialClauses && (
                <>
                  <Typography variant="subtitle1" gutterBottom sx={{ mt: 3, fontWeight: 'bold' }}>
                    特殊条款
                  </Typography>
                  <Typography variant="body1" paragraph sx={{ whiteSpace: 'pre-line' }}>
                    {document.specialClauses}
                  </Typography>
                </>
              )}
              
              {document?.attachments && document.attachments.length > 0 && (
                <>
                  <Typography variant="subtitle1" gutterBottom sx={{ mt: 3, fontWeight: 'bold' }}>
                    附件
                  </Typography>
                  <List>
                    {document.attachments.map(attachment => (
                      <ListItem key={attachment.id}>
                        <ListItemIcon>
                          <ArticleIcon />
                        </ListItemIcon>
                        <ListItemText 
                          primary={attachment.name}
                          secondary={
                            <Button
                              size="small"
                              href={attachment.url}
                              target="_blank"
                              rel="noopener"
                            >
                              查看附件
                            </Button>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </>
              )}
              
              <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="textSecondary">
                  提供方: {document?.provider}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  创建日期: {document?.createdAt ? new Date(document.createdAt).toLocaleDateString() : ''}
                </Typography>
              </Box>
            </Paper>
            
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
              <Button
                variant="outlined"
                startIcon={<PrintIcon />}
                onClick={() => setPrintDialogOpen(true)}
              >
                打印文档
              </Button>
              <Button
                variant="outlined"
                startIcon={<DownloadIcon />}
                onClick={handleDownload}
              >
                下载PDF
              </Button>
            </Box>
          </Box>
        );
      
      case 1:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              请确认您已理解并同意以下内容
            </Typography>
            
            <Paper sx={{ p: 3, mb: 3 }}>
              <List>
                {patientConfirmations.map((confirmation, index) => (
                  <ListItem key={index} sx={{ py: 1 }}>
                    <ListItemIcon>
                      <Checkbox
                        edge="start"
                        checked={signatures.patientAcknowledgements.includes(confirmation)}
                        onChange={() => handleConfirmationToggle(confirmation)}
                        color="primary"
                      />
                    </ListItemIcon>
                    <ListItemText primary={confirmation} />
                  </ListItem>
                ))}
              </List>
              
              <Alert 
                severity="info" 
                sx={{ mt: 2 }}
              >
                请确认所有内容后才能继续下一步
              </Alert>
            </Paper>
          </Box>
        );
      
      case 2:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              请在下方签名
            </Typography>
            
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="subtitle1" gutterBottom>
                      患者签名 <span style={{ color: 'red' }}>*</span>
                    </Typography>
                    <ElectronicSignature
                      onSave={handlePatientSignatureSave}
                      initialSignature={signatures.patientSignature}
                      width={450}
                      height={150}
                      label="患者签名"
                    />
                  </CardContent>
                </Card>
              </Grid>
              
              {document?.requireGuardianSignature && (
                <Grid item xs={12}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" gutterBottom>
                        监护人签名 <span style={{ color: 'red' }}>*</span>
                      </Typography>
                      <TextField
                        label="监护人姓名"
                        fullWidth
                        margin="normal"
                        value={guardianName}
                        onChange={(e) => setGuardianName(e.target.value)}
                        required
                        sx={{ mb: 2 }}
                      />
                      <ElectronicSignature
                        onSave={handleGuardianSignatureSave}
                        initialSignature={signatures.guardianSignature}
                        width={450}
                        height={150}
                        label="监护人签名"
                      />
                    </CardContent>
                  </Card>
                </Grid>
              )}
              
              {document?.requireWitnessSignature && (
                <Grid item xs={12}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" gutterBottom>
                        见证人签名 <span style={{ color: 'red' }}>*</span>
                      </Typography>
                      <TextField
                        label="见证人姓名"
                        fullWidth
                        margin="normal"
                        value={witnessName}
                        onChange={(e) => setWitnessName(e.target.value)}
                        required
                        sx={{ mb: 2 }}
                      />
                      <ElectronicSignature
                        onSave={handleWitnessSignatureSave}
                        initialSignature={signatures.witnessSignature}
                        width={450}
                        height={150}
                        label="见证人签名"
                      />
                    </CardContent>
                  </Card>
                </Grid>
              )}
            </Grid>
            
            <Alert 
              severity="warning" 
              sx={{ mt: 3 }}
            >
              请注意：您的电子签名具有法律效力，一旦签署将被永久保存。
            </Alert>
          </Box>
        );
      
      case 3:
        return (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircleIcon sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
            <Typography variant="h5" gutterBottom>
              知情同意书已成功签署
            </Typography>
            <Typography variant="body1" color="textSecondary" paragraph>
              感谢您完成知情同意书的签署。您的签名已被记录并保存，您可以随时查看签署的文档。
            </Typography>
            <Box sx={{ mt: 4 }}>
              <Button
                variant="contained"
                onClick={() => navigate('/patient/documents')}
              >
                返回文档列表
              </Button>
            </Box>
          </Box>
        );
      
      default:
        return '未知步骤';
    }
  };

  // 渲染加载状态
  if (status === 'loading') {
    return (
      <Container maxWidth="md" sx={{ py: 8, textAlign: 'center' }}>
        <CircularProgress sx={{ mb: 2 }} />
        <Typography variant="h6">
          加载知情同意文档...
        </Typography>
      </Container>
    );
  }

  // 渲染错误状态
  if (status === 'error') {
    return (
      <Container maxWidth="md" sx={{ py: 8 }}>
        <Alert severity="error" sx={{ mb: 4 }}>
          {error || '加载文档时发生错误'}
        </Alert>
        <Button
          variant="outlined"
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate(-1)}
        >
          返回
        </Button>
      </Container>
    );
  }

  // 步骤定义
  const steps = ['阅读文档', '确认理解', '签署同意', '完成'];

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper sx={{ p: 3, mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <IconButton
            edge="start"
            onClick={() => navigate(-1)}
            sx={{ mr: 2 }}
            aria-label="返回"
          >
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h5" component="h1">
            知情同意书
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <AssignmentIcon color="primary" />
        </Box>
        
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {steps.map((label, index) => (
            <Step key={label} completed={index < activeStep}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        
        <Divider sx={{ mb: 4 }} />
        
        {getStepContent(activeStep)}
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
          <Button
            variant="outlined"
            onClick={handleBack}
            disabled={activeStep === 0 || activeStep === 3}
          >
            上一步
          </Button>
          
          <div>
            {activeStep === steps.length - 2 ? (
              <Button
                variant="contained"
                color="primary"
                onClick={handleSubmit}
                disabled={!isStepComplete(activeStep) || submitting}
                sx={{ minWidth: 120 }}
              >
                {submitting ? <CircularProgress size={24} /> : '提交签名'}
              </Button>
            ) : activeStep < steps.length - 1 && (
              <Button
                variant="contained"
                color="primary"
                onClick={handleNext}
                disabled={!isStepComplete(activeStep)}
              >
                下一步
              </Button>
            )}
          </div>
        </Box>
      </Paper>
      
      {/* 打印对话框 */}
      <Dialog
        open={printDialogOpen}
        onClose={() => setPrintDialogOpen(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>打印文档</DialogTitle>
        <DialogContent>
          <Typography variant="body1">
            确定要打印此知情同意书吗？
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPrintDialogOpen(false)}>取消</Button>
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handlePrint}
          >
            打印
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ConsentDocumentView; 