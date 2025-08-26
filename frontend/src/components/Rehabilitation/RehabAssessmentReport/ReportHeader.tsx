import React from 'react';
import { Box, Typography, Button } from '@mui/material';
import PrintIcon from '@mui/icons-material/Print';
import ShareIcon from '@mui/icons-material/Share';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import { styled, Theme } from '@mui/material/styles';

export interface ReportHeaderProps {
  title?: string;
  institutionName?: string;
  logo?: string;
  onPrint?: () => void;
  onShare?: () => void;
  onExport?: () => void;
}

const HeaderContainer = styled(Box)(({ theme }: { theme: Theme }) => ({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  marginBottom: theme.spacing(3),
  paddingBottom: theme.spacing(2),
  borderBottom: `1px solid ${theme.palette.divider}`,
}));

const LogoBox = styled(Box)({
  width: 80,
  height: 80,
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  marginBottom: 8,
});

const Logo = styled('img')({
  maxWidth: '100%',
  maxHeight: '100%',
  objectFit: 'contain',
});

const ActionButtons = styled(Box)(({ theme }: { theme: Theme }) => ({
  display: 'flex',
  gap: theme.spacing(1),
  marginTop: theme.spacing(2),
}));

/**
 * 康复评估报告的头部组件，包含标题、机构名称、图标和操作按钮
 */
const ReportHeader: React.FC<ReportHeaderProps> = ({
  title = '康复评估报告',
  institutionName = '智能康复中心',
  logo,
  onPrint,
  onShare,
  onExport,
}) => {
  return (
    <HeaderContainer>
      {logo && (
        <LogoBox>
          <Logo src={logo} alt={institutionName} />
        </LogoBox>
      )}
      <Typography variant="h4" component="h1" gutterBottom align="center" fontWeight="bold">
        {title}
      </Typography>
      <Typography variant="h6" component="h2" align="center" color="text.secondary">
        {institutionName}
      </Typography>
      <ActionButtons>
        <Button 
          variant="outlined" 
          startIcon={<PrintIcon />} 
          size="small"
          onClick={onPrint}
        >
          打印
        </Button>
        <Button 
          variant="outlined" 
          startIcon={<ShareIcon />} 
          size="small"
          onClick={onShare}
        >
          分享
        </Button>
        <Button 
          variant="outlined" 
          startIcon={<FileDownloadIcon />} 
          size="small"
          onClick={onExport}
        >
          导出PDF
        </Button>
      </ActionButtons>
    </HeaderContainer>
  );
};

export default ReportHeader; 