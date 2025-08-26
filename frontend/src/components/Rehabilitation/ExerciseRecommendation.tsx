import React, { useState, useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Grid,
  Divider,
  Chip,
  CircularProgress,
  Alert,
  TextField,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
} from '@mui/material';
import {
  FitnessCenter as FitnessCenterIcon,
  Add as AddIcon,
  SmartToy as AgentIcon,
} from '@mui/icons-material';

import { RootState, AppDispatch } from '../../store';
import { Exercise, getRecommendations, addExercisesToPlan } from '../../store/slices/rehabSlice';
import { fetchAgents } from '../../store/slices/agentSlice';
import AgentChat from '../Agent/AgentChat';

interface ExerciseRecommendationProps {
  patientId?: string;
  planId?: string;  // Optional - if provided, allows adding to rehab plan
  onClose?: () => void;
}

const ExerciseRecommendation: React.FC<ExerciseRecommendationProps> = ({ patientId = '', planId, onClose }) => {
  const dispatch = useDispatch<AppDispatch>();
  const { recommendedExercises = [], isLoading = false, error = null } = useSelector((state: RootState) => state.rehab || {});
  const { agents = [] } = useSelector((state: RootState) => state.agents || { agents: [] });
  const [selectedExercises, setSelectedExercises] = useState<string[]>([]);
  const [condition, setCondition] = useState('');
  const [goal, setGoal] = useState('');
  const [selectedAgentId, setSelectedAgentId] = useState('');
  const [chatOpen, setChatOpen] = useState(false);

  // Predefined body conditions for medical context
  const bodyConditions = [
    { value: 'shoulder', label: 'Shoulder' },
    { value: 'knee', label: 'Knee' },
    { value: 'back', label: 'Back' },
    { value: 'neck', label: 'Neck' },
    { value: 'ankle', label: 'Ankle' },
    { value: 'wrist', label: 'Wrist' },
    { value: 'hip', label: 'Hip' },
    { value: 'elbow', label: 'Elbow' },
  ];

  // Rehabilitation goals
  const rehabGoals = [
    { value: 'pain_reduction', label: 'Pain Reduction' },
    { value: 'mobility', label: 'Improved Mobility' },
    { value: 'strength', label: 'Build Strength' },
    { value: 'flexibility', label: 'Increase Flexibility' },
    { value: 'balance', label: 'Improve Balance' },
    { value: 'endurance', label: 'Build Endurance' },
    { value: 'post_surgery', label: 'Post-Surgery Recovery' },
  ];

  // Fetch agents on component mount
  useEffect(() => {
    dispatch(fetchAgents());
  }, [dispatch]);

  const handleGetRecommendations = () => {
    dispatch(getRecommendations({
      patient_id: patientId,
      condition,
      goal,
      agent_id: selectedAgentId || undefined
    }));
  };

  const handleAddToPlan = () => {
    if (planId && selectedExercises.length > 0) {
      dispatch(addExercisesToPlan({
        planId,
        exerciseIds: selectedExercises
      }));
      setSelectedExercises([]);
    }
  };

  const handleToggleExerciseSelection = (exerciseId: string) => {
    if (selectedExercises.includes(exerciseId)) {
      setSelectedExercises(selectedExercises.filter(id => id !== exerciseId));
    } else {
      setSelectedExercises([...selectedExercises, exerciseId]);
    }
  };

  const handleOpenChat = () => {
    setChatOpen(true);
  };

  const handleCloseChat = () => {
    setChatOpen(false);
  };

  // Handle recommendations from chat interface
  const handleRecommendationFromChat = (data: any) => {
    // The agent might return recommendation data that we can process
    console.log('Received recommendations from chat:', data);
  };

  return (
    <Box>
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            <AgentIcon color="primary" sx={{ mr: 1, verticalAlign: 'middle' }} />
            Exercise Recommendations
          </Typography>

          <Divider sx={{ my: 2 }} />

          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} md={4}>
              <FormControl fullWidth size="small">
                <InputLabel id="condition-label">Body Part/Condition</InputLabel>
                <Select
                  labelId="condition-label"
                  id="condition"
                  value={condition}
                  label="Body Part/Condition"
                  onChange={(e) => setCondition(e.target.value)}
                >
                  {bodyConditions.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={4}>
              <FormControl fullWidth size="small">
                <InputLabel id="goal-label">Rehabilitation Goal</InputLabel>
                <Select
                  labelId="goal-label"
                  id="goal"
                  value={goal}
                  label="Rehabilitation Goal"
                  onChange={(e) => setGoal(e.target.value)}
                >
                  {rehabGoals.map((option) => (
                    <MenuItem key={option.value} value={option.value}>
                      {option.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={4}>
              <FormControl fullWidth size="small">
                <InputLabel id="agent-label">Agent</InputLabel>
                <Select
                  labelId="agent-label"
                  id="agent"
                  value={selectedAgentId}
                  label="Agent"
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                >
                  <MenuItem value="">
                    <em>Default Recommendation Agent</em>
                  </MenuItem>
                  {agents.map((agent) => (
                    <MenuItem key={agent._id} value={agent._id}>
                      {agent.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          </Grid>

          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
            <Button
              variant="contained"
              onClick={handleGetRecommendations}
              disabled={isLoading || !condition}
              startIcon={isLoading ? <CircularProgress size={20} /> : null}
            >
              {isLoading ? 'Getting Recommendations...' : 'Get Recommendations'}
            </Button>

            <Button
              variant="outlined"
              color="secondary"
              onClick={handleOpenChat}
              startIcon={<AgentIcon />}
            >
              Ask Agent Directly
            </Button>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3 }}>
              {error}
            </Alert>
          )}

          {recommendedExercises.length > 0 && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="subtitle1" gutterBottom>
                Recommended Exercises
              </Typography>
              <Grid container spacing={2}>
                {recommendedExercises.map((exercise) => (
                  <Grid item xs={12} sm={6} md={4} key={exercise._id}>
                    <Card 
                      variant="outlined" 
                      sx={{
                        height: '100%',
                        display: 'flex',
                        flexDirection: 'column',
                        cursor: 'pointer',
                        borderColor: selectedExercises.includes(exercise._id) ? 'primary.main' : 'divider',
                        borderWidth: selectedExercises.includes(exercise._id) ? 2 : 1,
                      }}
                      onClick={() => handleToggleExerciseSelection(exercise._id)}
                    >
                      <CardContent sx={{ flexGrow: 1 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <Typography variant="h6" gutterBottom>
                            {exercise.name}
                          </Typography>
                          <Chip
                            label={exercise.difficulty}
                            color={
                              exercise.difficulty === 'Easy' ? 'success' :
                              exercise.difficulty === 'Medium' ? 'warning' : 'error'
                            }
                            size="small"
                          />
                        </Box>
                        
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          {exercise.description}
                        </Typography>
                        
                        <Box sx={{ mt: 1, display: 'flex', gap: 1 }}>
                          <Chip
                            label={exercise.body_part}
                            size="small"
                            variant="outlined"
                            icon={<FitnessCenterIcon />}
                          />
                          <Chip
                            label={`${exercise.duration_minutes} min`}
                            size="small"
                            variant="outlined"
                          />
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>

              {planId && (
                <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
                  <Button
                    variant="contained"
                    color="primary"
                    startIcon={<AddIcon />}
                    disabled={selectedExercises.length === 0 || isLoading}
                    onClick={handleAddToPlan}
                  >
                    Add Selected to Plan
                  </Button>
                </Box>
              )}
            </>
          )}
          
          {chatOpen && selectedAgentId && (
            <Box sx={{ mt: 3, height: 400 }}>
              <Typography variant="subtitle1" gutterBottom>
                Chat with Agent
              </Typography>
              <AgentChat 
                agentId={selectedAgentId} 
                patientId={patientId}
                contextData={{ condition, goal }}
                onRecommendation={handleRecommendationFromChat}
              />
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  );
};

export default ExerciseRecommendation; 