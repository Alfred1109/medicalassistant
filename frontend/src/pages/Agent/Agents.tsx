import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import { Box, Button, Container, Grid, Paper, Typography } from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { createSelector } from 'reselect';

import { RootState } from '../../store';
import { fetchAgents } from '../../store/slices/agentSlice';

// 创建记忆化选择器
const selectAgents = createSelector(
  [(state: RootState) => state.agents?.agents || []],
  (agents) => agents
);

const Agents = () => {
  const dispatch = useDispatch();
  
  // 使用记忆化选择器
  const agents = useSelector(selectAgents);
  
  React.useEffect(() => {
    // 加载代理列表
    dispatch(fetchAgents());
  }, [dispatch]);

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <Typography variant="h4" component="h1">
          智能助手
        </Typography>
        <Button
          variant="contained"
          color="primary"
          startIcon={<AddIcon />}
          component={Link}
          to="/app/agents/new"
        >
          新建助手
        </Button>
      </Box>

      {agents.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1">
            您目前还没有智能助手。点击"新建助手"按钮开始创建。
          </Typography>
        </Paper>
      ) : (
        <Grid container spacing={3}>
          {agents.map((agent: any, index: number) => (
            <Grid item xs={12} md={6} lg={4} key={agent._id || `agent-${index}`}>
              <Paper sx={{ p: 3, height: '100%' }}>
                <Typography variant="h6">{agent.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {agent.description}
                </Typography>
                <Box mt={2}>
                  <Button 
                    component={Link} 
                    to={`/app/agents/${agent._id}`}
                    variant="outlined" 
                    size="small"
                  >
                    查看详情
                  </Button>
                </Box>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
    </Container>
  );
};

export default Agents; 