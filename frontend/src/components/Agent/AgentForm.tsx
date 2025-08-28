。、import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Divider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Stack,
  Grid,
  IconButton,
  CircularProgress,
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon } from '@mui/icons-material';
import { Formik, Form, FieldArray, useFormikContext } from 'formik';
import * as Yup from 'yup';

import { RootState, AppDispatch } from '../../store';
import { createAgent, updateAgent, Agent, Tool } from '../../store/slices/agentSlice';

// LLM models available
const AVAILABLE_MODELS = [
  { value: 'gpt-4-turbo', label: 'GPT-4 Turbo' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet' },
  { value: 'claude-3-haiku', label: 'Claude 3 Haiku' },
];

// Default system prompts for different agent types
const DEFAULT_SYSTEM_PROMPTS = {
  rehabilitation: 
    'You are a medical rehabilitation assistant. Help patients with their rehabilitation journey by providing exercise recommendations, answering questions about their rehabilitation plan, and offering encouragement. Always prioritize patient safety and refer to healthcare professionals for medical advice.',
  general:
    'You are a helpful assistant. Provide clear and concise information to help users with their queries.',
};

interface AgentFormProps {
  initialValues?: Partial<Agent>;
  mode: 'create' | 'edit';
}

// Validation schema
const AgentSchema = Yup.object().shape({
  name: Yup.string().required('Name is required'),
  description: Yup.string().required('Description is required'),
  model: Yup.string().required('Model selection is required'),
  system_prompt: Yup.string().required('System prompt is required'),
  tools: Yup.array().of(
    Yup.object().shape({
      name: Yup.string().required('Tool name is required'),
      description: Yup.string().required('Tool description is required'),
      parameters: Yup.object().required('Parameters are required'),
      required_parameters: Yup.array().of(Yup.string()),
    })
  ),
});

// Initial values for new agent
const defaultInitialValues = {
  name: '',
  description: '',
  model: 'gpt-4-turbo',
  system_prompt: DEFAULT_SYSTEM_PROMPTS.rehabilitation,
  tools: [] as Tool[],
  metadata: {},
};

const AgentForm: React.FC<AgentFormProps> = ({ initialValues, mode }) => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { isLoading, error } = useSelector((state: RootState) => state.agent);
  
  const formInitialValues = {
    ...defaultInitialValues,
    ...(initialValues || {}),
  };

  const handleSubmit = async (values: typeof formInitialValues) => {
    try {
      if (mode === 'create') {
        const result = await dispatch(createAgent(values)).unwrap();
        navigate(`/app/agents/${result._id}`);
      } else if (mode === 'edit' && initialValues?._id) {
        await dispatch(updateAgent({ 
          agentId: initialValues._id, 
          agentData: values 
        })).unwrap();
        navigate(`/app/agents/${initialValues._id}`);
      }
    } catch (err) {
      // Error is handled by Redux
      console.error('Failed to save agent:', err);
    }
  };
  
  // Component to handle prompt templates
  const PromptTemplateSelector = () => {
    const { values, setFieldValue } = useFormikContext<typeof formInitialValues>();
    
    const handleSelectPromptTemplate = (template: string) => {
      setFieldValue('system_prompt', DEFAULT_SYSTEM_PROMPTS[template as keyof typeof DEFAULT_SYSTEM_PROMPTS]);
    };
    
    return (
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Select a prompt template:
        </Typography>
        <Stack direction="row" spacing={1}>
          <Chip 
            label="Rehabilitation" 
            color={values.system_prompt === DEFAULT_SYSTEM_PROMPTS.rehabilitation ? 'primary' : 'default'} 
            onClick={() => handleSelectPromptTemplate('rehabilitation')} 
          />
          <Chip 
            label="General Assistant" 
            color={values.system_prompt === DEFAULT_SYSTEM_PROMPTS.general ? 'primary' : 'default'} 
            onClick={() => handleSelectPromptTemplate('general')} 
          />
        </Stack>
      </Box>
    );
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h5" gutterBottom>
          {mode === 'create' ? 'Create New Agent' : 'Edit Agent'}
        </Typography>
        
        <Formik
          initialValues={formInitialValues}
          validationSchema={AgentSchema}
          onSubmit={handleSubmit}
        >
          {({ values, errors, touched, handleChange, handleBlur, setFieldValue }) => (
            <Form>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    id="name"
                    name="name"
                    label="Agent Name"
                    value={values.name}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    error={touched.name && Boolean(errors.name)}
                    helperText={touched.name && errors.name}
                    margin="normal"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth margin="normal">
                    <InputLabel id="model-label">Model</InputLabel>
                    <Select
                      labelId="model-label"
                      id="model"
                      name="model"
                      value={values.model}
                      label="Model"
                      onChange={handleChange}
                      onBlur={handleBlur}
                      error={touched.model && Boolean(errors.model)}
                    >
                      {AVAILABLE_MODELS.map((model) => (
                        <MenuItem key={model.value} value={model.value}>
                          {model.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    id="description"
                    name="description"
                    label="Description"
                    value={values.description}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    error={touched.description && Boolean(errors.description)}
                    helperText={touched.description && errors.description}
                    margin="normal"
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="h6">System Prompt</Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    This defines the agent's personality and capabilities.
                  </Typography>
                  
                  <PromptTemplateSelector />
                  
                  <TextField
                    fullWidth
                    id="system_prompt"
                    name="system_prompt"
                    label="System Prompt"
                    multiline
                    rows={6}
                    value={values.system_prompt}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    error={touched.system_prompt && Boolean(errors.system_prompt)}
                    helperText={touched.system_prompt && errors.system_prompt}
                    margin="normal"
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="h6">Tools</Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Add tools to extend the agent's capabilities.
                  </Typography>
                  
                  <FieldArray name="tools">
                    {({ push, remove }) => (
                      <>
                        {values.tools.map((tool, index) => (
                          <Card key={index} variant="outlined" sx={{ mb: 2, p: 2 }}>
                            <Stack direction="row" justifyContent="space-between" alignItems="center" mb={2}>
                              <Typography variant="subtitle1">Tool #{index + 1}</Typography>
                              <IconButton 
                                color="error" 
                                onClick={() => remove(index)}
                                size="small"
                              >
                                <DeleteIcon />
                              </IconButton>
                            </Stack>
                            
                            <TextField
                              fullWidth
                              name={`tools.${index}.name`}
                              label="Tool Name"
                              value={tool.name}
                              onChange={handleChange}
                              margin="dense"
                            />
                            
                            <TextField
                              fullWidth
                              name={`tools.${index}.description`}
                              label="Tool Description"
                              value={tool.description}
                              onChange={handleChange}
                              margin="dense"
                            />
                            
                            {/* Parameters management simplified for this example */}
                            <Typography variant="subtitle2" sx={{ mt: 2 }}>
                              Parameters JSON
                            </Typography>
                            <TextField
                              fullWidth
                              name={`tools.${index}.parameters`}
                              label="Parameters (JSON)"
                              value={JSON.stringify(tool.parameters)}
                              onChange={(e) => {
                                try {
                                  const parsed = JSON.parse(e.target.value);
                                  setFieldValue(`tools.${index}.parameters`, parsed);
                                } catch (err) {
                                  // Let user continue typing even if JSON is invalid
                                }
                              }}
                              multiline
                              rows={3}
                              margin="dense"
                            />
                          </Card>
                        ))}
                        
                        <Button
                          variant="outlined"
                          startIcon={<AddIcon />}
                          onClick={() => push({
                            name: '',
                            description: '',
                            parameters: {},
                            required_parameters: [],
                          })}
                          sx={{ mt: 2 }}
                        >
                          Add Tool
                        </Button>
                      </>
                    )}
                  </FieldArray>
                </Grid>
                
                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
                    <Button 
                      variant="outlined" 
                      onClick={() => navigate(-1)}
                      disabled={isLoading}
                    >
                      Cancel
                    </Button>
                    <Button 
                      type="submit" 
                      variant="contained" 
                      disabled={isLoading}
                      startIcon={isLoading ? <CircularProgress size={20} /> : null}
                    >
                      {isLoading ? 'Saving...' : mode === 'create' ? 'Create Agent' : 'Update Agent'}
                    </Button>
                  </Box>
                  
                  {error && (
                    <Typography color="error" sx={{ mt: 2 }}>
                      {error}
                    </Typography>
                  )}
                </Grid>
              </Grid>
            </Form>
          )}
        </Formik>
      </CardContent>
    </Card>
  );
};

export default AgentForm; 