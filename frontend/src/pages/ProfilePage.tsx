import React, { useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
  Box,
  Paper,
  Grid,
  Typography,
  Avatar,
  Button,
  TextField,
  Divider,
  Alert,
  Snackbar,
  CircularProgress,
  Card,
  CardContent,
  IconButton,
} from '@mui/material';
import {
  Edit as EditIcon,
  Save as SaveIcon,
  Cancel as CancelIcon,
  Person as PersonIcon,
  Lock as LockIcon,
  Logout as LogoutIcon,
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../store';
import { logout, updateUserProfile } from '../store/slices/authSlice';

const ProfilePage: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { user, loading, error } = useSelector((state: RootState) => state.auth);
  
  const [editMode, setEditMode] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [snackbarMessage, setSnackbarMessage] = useState('');
  
  const [formData, setFormData] = useState({
    name: user?.name || '',
    email: user?.email || '',
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
    
    // Clear error when user starts typing
    if (formErrors[name]) {
      setFormErrors({
        ...formErrors,
        [name]: '',
      });
    }
  };
  
  const handleEditToggle = () => {
    setEditMode(!editMode);
    if (!editMode) {
      // Reset form data to current user data when entering edit mode
      setFormData({
        name: user?.name || '',
        email: user?.email || '',
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      });
      setFormErrors({});
    }
  };
  
  const validateForm = () => {
    const errors: Record<string, string> = {};
    
    if (!formData.name.trim()) {
      errors.name = 'Name is required';
    }
    
    if (!formData.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      errors.email = 'Email is invalid';
    }
    
    // Validate password only if the user is trying to change it
    if (formData.newPassword) {
      if (!formData.currentPassword) {
        errors.currentPassword = 'Current password is required to set a new password';
      }
      
      if (formData.newPassword.length < 6) {
        errors.newPassword = 'New password must be at least 6 characters';
      }
      
      if (formData.newPassword !== formData.confirmPassword) {
        errors.confirmPassword = 'Passwords do not match';
      }
    }
    
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    // Prepare update data
    const updateData: any = {
      name: formData.name,
    };
    
    // Only include email if it's changed
    if (formData.email !== user?.email) {
      updateData.email = formData.email;
    }
    
    // Only include password if user is trying to change it
    if (formData.newPassword) {
      updateData.currentPassword = formData.currentPassword;
      updateData.newPassword = formData.newPassword;
    }
    
    try {
      await dispatch(updateUserProfile(updateData)).unwrap();
      setSnackbarMessage('Profile updated successfully');
      setSnackbarOpen(true);
      setEditMode(false);
    } catch (err) {
      // Error is handled by the slice and displayed to the user
      setSnackbarMessage('Failed to update profile');
      setSnackbarOpen(true);
    }
  };
  
  const handleLogout = () => {
    dispatch(logout());
  };
  
  const handleSnackbarClose = () => {
    setSnackbarOpen(false);
  };
  
  // Format date to display
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString();
  };
  
  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        My Profile
      </Typography>
      
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}
      
      <Grid container spacing={4}>
        <Grid item xs={12} md={4}>
          <Card elevation={3} sx={{ borderRadius: 2 }}>
            <CardContent sx={{ textAlign: 'center', py: 5 }}>
              <Avatar
                sx={{
                  width: 120,
                  height: 120,
                  mx: 'auto',
                  mb: 2,
                  bgcolor: 'primary.main',
                  fontSize: '3rem',
                }}
              >
                {user?.name?.charAt(0).toUpperCase() || <PersonIcon fontSize="large" />}
              </Avatar>
              
              <Typography variant="h5" gutterBottom>
                {user?.name || 'User'}
              </Typography>
              
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {user?.email || 'No email specified'}
              </Typography>
              
              <Box 
                sx={{ 
                  display: 'inline-block', 
                  px: 2, 
                  py: 0.5, 
                  borderRadius: 1, 
                  bgcolor: 'primary.light', 
                  color: 'white', 
                  mt: 1 
                }}
              >
                {user?.role === 'practitioner' ? 'Practitioner' : 'Patient'}
              </Box>
              
              <Divider sx={{ my: 3 }} />
              
              <Box sx={{ textAlign: 'left' }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Account created: {formatDate(user?.createdAt)}
                </Typography>
                
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Last updated: {formatDate(user?.updatedAt)}
                </Typography>
              </Box>
              
              <Button
                variant="outlined"
                color="error"
                startIcon={<LogoutIcon />}
                onClick={handleLogout}
                sx={{ mt: 3 }}
                fullWidth
              >
                Sign Out
              </Button>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={8}>
          <Paper elevation={3} sx={{ p: 3, borderRadius: 2 }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6" component="h2">
                {editMode ? 'Edit Profile' : 'Profile Information'}
              </Typography>
              
              <IconButton color={editMode ? 'error' : 'primary'} onClick={handleEditToggle}>
                {editMode ? <CancelIcon /> : <EditIcon />}
              </IconButton>
            </Box>
            
            <Divider sx={{ mb: 3 }} />
            
            <Box component="form" onSubmit={handleSubmit} noValidate>
              <Grid container spacing={3}>
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Name"
                    name="name"
                    value={formData.name}
                    onChange={handleInputChange}
                    disabled={!editMode}
                    error={!!formErrors.name}
                    helperText={formErrors.name}
                    InputProps={{
                      startAdornment: <PersonIcon color="action" sx={{ mr: 1 }} />,
                    }}
                  />
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    disabled={!editMode}
                    error={!!formErrors.email}
                    helperText={formErrors.email}
                  />
                </Grid>
                
                {editMode && (
                  <>
                    <Grid item xs={12}>
                      <Typography variant="subtitle1" sx={{ mt: 2, mb: 1 }}>
                        Change Password (Optional)
                      </Typography>
                      <Divider />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Current Password"
                        name="currentPassword"
                        type="password"
                        value={formData.currentPassword}
                        onChange={handleInputChange}
                        error={!!formErrors.currentPassword}
                        helperText={formErrors.currentPassword}
                        InputProps={{
                          startAdornment: <LockIcon color="action" sx={{ mr: 1 }} />,
                        }}
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="New Password"
                        name="newPassword"
                        type="password"
                        value={formData.newPassword}
                        onChange={handleInputChange}
                        error={!!formErrors.newPassword}
                        helperText={formErrors.newPassword}
                      />
                    </Grid>
                    
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Confirm New Password"
                        name="confirmPassword"
                        type="password"
                        value={formData.confirmPassword}
                        onChange={handleInputChange}
                        error={!!formErrors.confirmPassword}
                        helperText={formErrors.confirmPassword}
                      />
                    </Grid>
                  </>
                )}
                
                {editMode && (
                  <Grid item xs={12} sx={{ mt: 2 }}>
                    <Button
                      type="submit"
                      variant="contained"
                      color="primary"
                      disabled={loading}
                      startIcon={loading ? <CircularProgress size={20} /> : <SaveIcon />}
                    >
                      Save Changes
                    </Button>
                  </Grid>
                )}
              </Grid>
            </Box>
          </Paper>
          
          <Card elevation={3} sx={{ mt: 3, p: 3, borderRadius: 2 }}>
            <Typography variant="h6" gutterBottom>
              Account Preferences
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Typography variant="body2" color="text.secondary">
              Account preferences and additional settings will be available in future updates.
            </Typography>
          </Card>
        </Grid>
      </Grid>
      
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={6000}
        onClose={handleSnackbarClose}
        message={snackbarMessage}
      />
    </Box>
  );
};

export default ProfilePage; 