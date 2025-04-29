import React from 'react';
import { Box, Typography, Grid, Paper, Divider, Avatar } from '@mui/material';
import { Patient, Doctor } from './index';
import { formatDate, getObjectValue } from './utils';

interface PersonalInfoProps {
  patient: Patient;
  doctor: Doctor;
}

/**
 * 康复评估报告中的个人信息组件，展示患者和医生的详细信息
 */
const PersonalInfo: React.FC<PersonalInfoProps> = ({
  patient,
  doctor
}) => {
  return (
    <Paper 
      elevation={0} 
      sx={{ 
        p: 3, 
        mb: 3,
        border: '1px solid #eee',
        '@media print': { border: 'none', p: 0, boxShadow: 'none' }
      }}
    >
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>
        个人信息
      </Typography>
      
      <Grid container spacing={3}>
        {/* 患者信息 */}
        <Grid item xs={12} md={6}>
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold', color: 'primary.main' }}>
              患者信息
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Avatar 
                sx={{ 
                  width: 64, 
                  height: 64, 
                  bgcolor: 'primary.main',
                  mr: 2
                }}
              >
                {patient.name ? patient.name.charAt(0) : '?'}
              </Avatar>
              <Box>
                <Typography variant="h6">{patient.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {`ID: ${patient.medicalId}`}
                </Typography>
              </Box>
            </Box>
            
            <Divider sx={{ my: 1 }} />
            
            <Grid container spacing={1}>
              <Grid item xs={6}>
                <InfoItem label="性别" value={patient.gender} />
              </Grid>
              <Grid item xs={6}>
                <InfoItem label="年龄" value={`${patient.age}岁`} />
              </Grid>
              <Grid item xs={12}>
                <InfoItem label="联系方式" value={patient.contact} />
              </Grid>
            </Grid>
          </Box>
        </Grid>
        
        {/* 医生信息 */}
        <Grid item xs={12} md={6}>
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold', color: 'primary.main' }}>
              医生信息
            </Typography>
            
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Avatar 
                sx={{ 
                  width: 64, 
                  height: 64, 
                  bgcolor: 'secondary.main',
                  mr: 2
                }}
              >
                {doctor.name ? doctor.name.charAt(0) : '?'}
              </Avatar>
              <Box>
                <Typography variant="h6">{doctor.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {`${doctor.title} | ${doctor.department}`}
                </Typography>
              </Box>
            </Box>
            
            <Divider sx={{ my: 1 }} />
            
            <Grid container spacing={1}>
              <Grid item xs={12}>
                <InfoItem label="科室" value={doctor.department} />
              </Grid>
              <Grid item xs={12}>
                <InfoItem label="职称" value={doctor.title} />
              </Grid>
              <Grid item xs={12}>
                <InfoItem label="联系方式" value={doctor.contact} />
              </Grid>
            </Grid>
          </Box>
        </Grid>
      </Grid>
    </Paper>
  );
};

// 信息项组件
const InfoItem: React.FC<{ label: string; value: string | number }> = ({ label, value }) => (
  <Box sx={{ display: 'flex', mb: 1 }}>
    <Typography 
      variant="body2" 
      sx={{ 
        color: 'text.secondary', 
        width: '80px', 
        flexShrink: 0 
      }}
    >
      {label}:
    </Typography>
    <Typography variant="body2" sx={{ fontWeight: 500 }}>
      {value || '--'}
    </Typography>
  </Box>
);

export default PersonalInfo; 