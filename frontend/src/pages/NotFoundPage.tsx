import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Paper,
  Container,
} from '@mui/material';
import {
  SentimentDissatisfied as SentimentDissatisfiedIcon,
  ArrowBack as ArrowBackIcon,
} from '@mui/icons-material';

const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  const handleGoBack = () => {
    navigate(-1);
  };

  const handleGoHome = () => {
    navigate('/');
  };

  return (
    <Container maxWidth="md">
      <Box
        sx={{
          py: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <Paper
          elevation={3}
          sx={{
            p: 5,
            borderRadius: 3,
            maxWidth: 600,
            width: '100%',
          }}
        >
          <SentimentDissatisfiedIcon
            sx={{
              fontSize: 100,
              color: 'primary.main',
              mb: 3,
            }}
          />

          <Typography variant="h3" component="h1" gutterBottom>
            404
          </Typography>

          <Typography variant="h5" component="h2" gutterBottom>
            Page Not Found
          </Typography>

          <Typography variant="body1" color="text.secondary" paragraph sx={{ mb: 4 }}>
            The page you're looking for doesn't exist or has been moved.
          </Typography>

          <Box
            sx={{
              display: 'flex',
              justifyContent: 'center',
              gap: 2,
              flexWrap: 'wrap',
            }}
          >
            <Button
              variant="outlined"
              startIcon={<ArrowBackIcon />}
              onClick={handleGoBack}
            >
              Go Back
            </Button>
            <Button
              variant="contained"
              onClick={handleGoHome}
            >
              Go Home
            </Button>
          </Box>
        </Paper>
      </Box>
    </Container>
  );
};

export default NotFoundPage; 