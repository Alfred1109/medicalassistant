import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  IconButton,
  Divider,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  LinearProgress,
  Alert,
  Tooltip,
  Paper,
  Tab,
  Tabs,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Chat as ChatIcon,
  Settings as SettingsIcon,
  Code as CodeIcon,
  Psychology as PsychologyIcon,
} from '@mui/icons-material';
import { AppDispatch, RootState } from '../store';
import { fetchAgents, deleteAgent } from '../store/slices/agentSlice';
import AgentForm from '../components/Agent/AgentForm';
import AgentChat from '../components/Agent/AgentChat';

// Interface for the TabPanel component
interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

// TabPanel component for tab content
const TabPanel = (props: TabPanelProps) => {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`agent-tabpanel-${index}`}
      aria-labelledby={`agent-tab-${index}`}
      {...other}
      style={{ padding: '20px 0' }}
    >
      {value === index && <Box>{children}</Box>}
    </div>
  );
};

const AgentManagementPage: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { agents, loading, error } = useSelector((state: RootState) => state.agent);
  const { user } = useSelector((state: RootState) => state.auth);

  const [openCreateDialog, setOpenCreateDialog] = useState(false);
  const [openChatDialog, setOpenChatDialog] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<any>(null);
  const [tabValue, setTabValue] = useState(0);

  useEffect(() => {
    dispatch(fetchAgents());
  }, [dispatch]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleOpenCreateDialog = () => {
    setSelectedAgent(null);
    setOpenCreateDialog(true);
  };

  const handleOpenEditDialog = (agent: any) => {
    setSelectedAgent(agent);
    setOpenCreateDialog(true);
  };

  const handleCloseCreateDialog = () => {
    setOpenCreateDialog(false);
    setSelectedAgent(null);
  };

  const handleOpenChatDialog = (agent: any) => {
    setSelectedAgent(agent);
    setOpenChatDialog(true);
  };

  const handleCloseChatDialog = () => {
    setOpenChatDialog(false);
  };

  const handleDeleteAgent = (agentId: string) => {
    if (window.confirm('Are you sure you want to delete this agent?')) {
      dispatch(deleteAgent(agentId));
    }
  };

  const getModelColor = (model: string) => {
    if (model.includes('gpt-4')) return '#10a37f';
    if (model.includes('gpt-3.5')) return '#74aa9c';
    if (model.includes('claude')) return '#7c3aed';
    return '#666666';
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          Agent Management
        </Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={handleOpenCreateDialog}
        >
          Create Agent
        </Button>
      </Box>

      <Paper sx={{ mb: 4 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          variant="fullWidth"
        >
          <Tab
            icon={<PsychologyIcon />}
            label="My Agents"
            id="agent-tab-0"
            aria-controls="agent-tabpanel-0"
          />
          <Tab
            icon={<ChatIcon />}
            label="Conversations"
            id="agent-tab-1"
            aria-controls="agent-tabpanel-1"
            disabled={true}
          />
          <Tab
            icon={<SettingsIcon />}
            label="Settings"
            id="agent-tab-2"
            aria-controls="agent-tabpanel-2"
            disabled={true}
          />
        </Tabs>
      </Paper>

      {loading && <LinearProgress sx={{ mb: 3 }} />}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <TabPanel value={tabValue} index={0}>
        {!loading && agents.length === 0 && (
          <Box textAlign="center" py={5}>
            <PsychologyIcon sx={{ fontSize: 60, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="textSecondary" gutterBottom>
              No agents created yet
            </Typography>
            <Typography variant="body2" color="textSecondary" paragraph sx={{ maxWidth: 500, mx: 'auto', mb: 3 }}>
              Create specialized rehabilitation assistants to help with different aspects of patient care.
              Each agent can be configured with specific knowledge and capabilities.
            </Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleOpenCreateDialog}
              sx={{ mt: 1 }}
            >
              Create Your First Agent
            </Button>
          </Box>
        )}

        <Grid container spacing={3}>
          {agents.map((agent) => (
            <Grid item xs={12} md={6} lg={4} key={agent._id}>
              <Card
                elevation={3}
                sx={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  transition: 'transform 0.2s',
                  '&:hover': {
                    transform: 'translateY(-5px)',
                    boxShadow: 6,
                  },
                }}
              >
                <CardContent sx={{ flexGrow: 1 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="h5" component="h2">
                      {agent.name}
                    </Typography>
                    <Tooltip title={agent.model}>
                      <Chip
                        size="small"
                        label={agent.model.split('-').pop()}
                        sx={{
                          backgroundColor: getModelColor(agent.model),
                          color: 'white',
                          fontWeight: 'bold',
                        }}
                      />
                    </Tooltip>
                  </Box>

                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Created: {formatDate(agent.createdAt)}
                  </Typography>

                  <Typography variant="body1" paragraph sx={{ my: 2 }}>
                    {agent.description}
                  </Typography>

                  <Box my={2}>
                    <Typography variant="subtitle2" gutterBottom>
                      Capabilities
                    </Typography>
                    {agent.tools && agent.tools.length > 0 ? (
                      <Box>
                        {agent.tools.map((tool: any, index: number) => (
                          <Chip
                            key={index}
                            size="small"
                            icon={<CodeIcon />}
                            label={tool.name}
                            sx={{ mr: 1, mb: 1 }}
                          />
                        ))}
                      </Box>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        No specialized tools
                      </Typography>
                    )}
                  </Box>

                  <Divider sx={{ my: 2 }} />

                  <Typography variant="subtitle2" gutterBottom>
                    System Prompt Preview
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      fontFamily: 'monospace',
                      fontSize: '0.8rem',
                      backgroundColor: 'grey.100',
                      p: 1,
                      borderRadius: 1,
                    }}
                  >
                    {agent.system_prompt}
                  </Typography>
                </CardContent>
                <CardActions sx={{ justifyContent: 'space-between', px: 2, pb: 2 }}>
                  <Button
                    size="small"
                    startIcon={<ChatIcon />}
                    variant="contained"
                    onClick={() => handleOpenChatDialog(agent)}
                  >
                    Chat
                  </Button>
                  <Box>
                    <IconButton size="small" onClick={() => handleOpenEditDialog(agent)} sx={{ mr: 1 }}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton size="small" onClick={() => handleDeleteAgent(agent._id)} color="error">
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <Box textAlign="center" py={5}>
          <Typography variant="h6" color="textSecondary">
            Conversation history coming soon
          </Typography>
        </Box>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <Box textAlign="center" py={5}>
          <Typography variant="h6" color="textSecondary">
            Agent settings coming soon
          </Typography>
        </Box>
      </TabPanel>

      {/* Create/Edit Agent Dialog */}
      <Dialog
        open={openCreateDialog}
        onClose={handleCloseCreateDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {selectedAgent ? 'Edit Agent' : 'Create New Agent'}
        </DialogTitle>
        <DialogContent dividers>
          <AgentForm
            agent={selectedAgent}
            onSuccess={handleCloseCreateDialog}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseCreateDialog}>Cancel</Button>
        </DialogActions>
      </Dialog>

      {/* Chat Dialog */}
      <Dialog
        open={openChatDialog}
        onClose={handleCloseChatDialog}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            height: '80vh',
            maxHeight: '900px',
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        <DialogTitle>
          Chat with {selectedAgent?.name || 'Agent'}
        </DialogTitle>
        <DialogContent dividers sx={{ flexGrow: 1, p: 0 }}>
          {selectedAgent && (
            <AgentChat
              agentId={selectedAgent._id}
              agentName={selectedAgent.name}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseChatDialog}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AgentManagementPage; 