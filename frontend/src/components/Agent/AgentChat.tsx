import React, { useState, useEffect, useRef } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  CircularProgress,
  Divider,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
} from '@mui/material';
import { Send as SendIcon, SmartToy as AgentIcon, Person as UserIcon } from '@mui/icons-material';

import { RootState } from '../../store';
import { queryAgent, clearQueryResponse } from '../../store/slices/agentSlice';
import { AppDispatch } from '../../store';

interface AgentChatProps {
  agentId: string;
  patientId?: string;
  contextData?: Record<string, any>;
  onRecommendation?: (data: any) => void;
}

interface Message {
  id: string;
  sender: 'user' | 'agent';
  content: string;
  timestamp: string;
}

const AgentChat: React.FC<AgentChatProps> = ({ agentId, patientId, contextData, onRecommendation }) => {
  const dispatch = useDispatch<AppDispatch>();
  const { currentAgent, queryResponse, isLoading, error } = useSelector((state: RootState) => state.agent);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);

  // Add welcome message when agent is loaded
  useEffect(() => {
    if (currentAgent && messages.length === 0) {
      setMessages([
        {
          id: '0',
          sender: 'agent',
          content: `Hello, I'm ${currentAgent.name}. How can I assist with your rehabilitation today?`,
          timestamp: new Date().toISOString(),
        },
      ]);
    }
  }, [currentAgent, messages.length]);

  // Handle response from agent
  useEffect(() => {
    if (queryResponse) {
      const newMessage: Message = {
        id: Date.now().toString(),
        sender: 'agent',
        content: queryResponse.response,
        timestamp: queryResponse.timestamp,
      };
      
      setMessages((prev) => [...prev, newMessage]);
      
      // Process any recommendations
      if (onRecommendation && queryResponse.metadata?.recommendations) {
        onRecommendation(queryResponse.metadata.recommendations);
      }
      
      // Clear the query response
      dispatch(clearQueryResponse());
    }
  }, [queryResponse, dispatch, onRecommendation]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    
    // Add user message to chat
    const userMessage: Message = {
      id: Date.now().toString(),
      sender: 'user',
      content: input,
      timestamp: new Date().toISOString(),
    };
    
    setMessages((prev) => [...prev, userMessage]);
    
    // Prepare query parameters with context
    const queryParams = {
      query: input,
      parameters: {
        ...(patientId && { patient_id: patientId }),
        ...(contextData && contextData),
      },
    };
    
    // Dispatch query to agent
    dispatch(queryAgent({ agentId, query: queryParams }));
    
    // Clear input
    setInput('');
  };

  return (
    <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', p: 2 }}>
      <Typography variant="h6" gutterBottom>
        {currentAgent?.name || 'Agent Chat'}
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        {currentAgent?.description || 'Interact with the rehabilitation assistant'}
      </Typography>
      
      <Divider sx={{ mb: 2 }} />
      
      {/* Chat messages */}
      <Box sx={{ flexGrow: 1, overflow: 'auto', mb: 2 }}>
        <List>
          {messages.map((message) => (
            <ListItem
              key={message.id}
              alignItems="flex-start"
              sx={{
                flexDirection: message.sender === 'user' ? 'row-reverse' : 'row',
                mb: 1,
              }}
            >
              <ListItemAvatar>
                <Avatar sx={{ bgcolor: message.sender === 'user' ? 'primary.main' : 'secondary.main' }}>
                  {message.sender === 'user' ? <UserIcon /> : <AgentIcon />}
                </Avatar>
              </ListItemAvatar>
              <ListItemText
                primary={message.content}
                secondary={new Date(message.timestamp).toLocaleTimeString()}
                primaryTypographyProps={{
                  component: 'div',
                  sx: {
                    p: 2,
                    borderRadius: 2,
                    bgcolor: message.sender === 'user' ? 'primary.light' : 'grey.100',
                    color: message.sender === 'user' ? 'white' : 'text.primary',
                    maxWidth: '80%',
                    wordBreak: 'break-word',
                  },
                }}
                sx={{
                  textAlign: message.sender === 'user' ? 'right' : 'left',
                }}
              />
            </ListItem>
          ))}
          <div ref={messagesEndRef} />
        </List>
      </Box>
      
      {/* Input area */}
      <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', alignItems: 'center' }}>
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Type your message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoading}
          size="small"
          sx={{ mr: 1 }}
        />
        <Button
          type="submit"
          variant="contained"
          color="primary"
          disabled={isLoading || !input.trim()}
          endIcon={isLoading ? <CircularProgress size={20} /> : <SendIcon />}
        >
          {isLoading ? 'Sending...' : 'Send'}
        </Button>
      </Box>
      
      {error && (
        <Typography color="error" variant="body2" sx={{ mt: 1 }}>
          Error: {error}
        </Typography>
      )}
    </Paper>
  );
};

export default AgentChat; 