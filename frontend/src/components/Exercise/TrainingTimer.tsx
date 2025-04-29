import React from 'react';
import { 
  Box, 
  Typography, 
  Button, 
  Paper, 
  LinearProgress, 
  IconButton, 
  Grid,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Divider,
  Tooltip,
  Alert
} from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import ReplayIcon from '@mui/icons-material/Replay';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import SettingsIcon from '@mui/icons-material/Settings';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';
import FitnessCenterIcon from '@mui/icons-material/FitnessCenter';
import TimerIcon from '@mui/icons-material/Timer';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';

// 训练阶段类型
type TrainingPhase = 'prepare' | 'exercise' | 'rest' | 'complete';

// 训练计时器属性接口
interface TrainingTimerProps {
  exerciseName?: string;
  defaultExerciseTime?: number; // 单位: 秒
  defaultRestTime?: number; // 单位: 秒
  defaultSets?: number;
  onComplete?: (stats: TrainingStats) => void;
  autoStart?: boolean;
}

// 训练统计接口
interface TrainingStats {
  totalTime: number; // 总训练时间（秒）
  completedSets: number; // 完成的组数
  averageSetTime: number; // 平均每组时间（秒）
  restTime: number; // 总休息时间（秒）
  exerciseTime: number; // 总锻炼时间（秒）
}

/**
 * 康复训练计时器组件
 * 支持训练时间倒计时、休息时间、训练组数管理，并提供语音和视觉提示
 */
const TrainingTimer: React.FC<TrainingTimerProps> = ({
  exerciseName = "康复训练",
  defaultExerciseTime = 30,
  defaultRestTime = 15,
  defaultSets = 3,
  onComplete,
  autoStart = false
}) => {
  // 状态定义
  const [exerciseTime, setExerciseTime] = React.useState<number>(defaultExerciseTime);
  const [restTime, setRestTime] = React.useState<number>(defaultRestTime);
  const [sets, setSets] = React.useState<number>(defaultSets);
  const [currentSet, setCurrentSet] = React.useState<number>(1);
  const [secondsLeft, setSecondsLeft] = React.useState<number>(defaultExerciseTime);
  const [phase, setPhase] = React.useState<TrainingPhase>('prepare');
  const [isPaused, setIsPaused] = React.useState<boolean>(!autoStart);
  const [isSettingsOpen, setIsSettingsOpen] = React.useState<boolean>(false);
  const [isMuted, setIsMuted] = React.useState<boolean>(false);
  const [stats, setStats] = React.useState<TrainingStats>({
    totalTime: 0,
    completedSets: 0,
    averageSetTime: 0,
    restTime: 0,
    exerciseTime: 0
  });
  
  // 用于存储定时器ID
  const timerRef = React.useRef<NodeJS.Timeout | null>(null);
  // 用于记录实际训练时间
  const statsRef = React.useRef({
    startTime: 0,
    totalExerciseTime: 0,
    totalRestTime: 0,
    completedSets: 0
  });
  // 音频元素引用
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  
  // 计算进度百分比
  const calculateProgress = (): number => {
    if (phase === 'prepare') return 0;
    if (phase === 'complete') return 100;
    
    const totalTime = phase === 'exercise' ? exerciseTime : restTime;
    return ((totalTime - secondsLeft) / totalTime) * 100;
  };
  
  // 格式化时间显示（分:秒）
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };
  
  // 播放音频提示
  const playSound = (url: string) => {
    if (isMuted) return;
    
    if (audioRef.current) {
      audioRef.current.src = url;
      audioRef.current.play().catch((error: Error) => {
        console.error('播放音频失败:', error);
      });
    }
  };
  
  // 语音提示
  const speakText = (text: string) => {
    if (isMuted || !window.speechSynthesis) return;
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'zh-CN';
    utterance.volume = 1;
    window.speechSynthesis.speak(utterance);
  };
  
  // 获取当前阶段显示文本
  const getPhaseText = (): string => {
    switch (phase) {
      case 'prepare':
        return '准备开始';
      case 'exercise':
        return `训练中 (第 ${currentSet}/${sets} 组)`;
      case 'rest':
        return `休息时间 (${currentSet}/${sets} 组后)`;
      case 'complete':
        return '训练完成！';
      default:
        return '';
    }
  };
  
  // 获取当前阶段提示文本
  const getPhaseInstructionText = (): string => {
    switch (phase) {
      case 'prepare':
        return '点击"开始"按钮开始训练';
      case 'exercise':
        return '保持正确姿势，专注呼吸';
      case 'rest':
        return '放松肌肉，做深呼吸';
      case 'complete':
        return '恭喜您完成了今天的训练！';
      default:
        return '';
    }
  };
  
  // 开始训练
  const startTimer = () => {
    if (phase === 'prepare') {
      setPhase('exercise');
      setSecondsLeft(exerciseTime);
      statsRef.current.startTime = Date.now();
      speakText(`开始第${currentSet}组训练`);
    }
    setIsPaused(false);
  };
  
  // 暂停训练
  const pauseTimer = () => {
    setIsPaused(true);
    // 累计已经训练的时间
    if (phase === 'exercise') {
      statsRef.current.totalExerciseTime += exerciseTime - secondsLeft;
    } else if (phase === 'rest') {
      statsRef.current.totalRestTime += restTime - secondsLeft;
    }
  };
  
  // 重置训练
  const resetTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    
    setPhase('prepare');
    setCurrentSet(1);
    setSecondsLeft(exerciseTime);
    setIsPaused(true);
    
    // 重置统计数据
    statsRef.current = {
      startTime: 0,
      totalExerciseTime: 0,
      totalRestTime: 0,
      completedSets: 0
    };
    
    setStats({
      totalTime: 0,
      completedSets: 0,
      averageSetTime: 0,
      restTime: 0,
      exerciseTime: 0
    });
  };
  
  // 跳过当前阶段
  const skipPhase = () => {
    if (phase === 'exercise') {
      // 累计已经训练的时间
      statsRef.current.totalExerciseTime += exerciseTime - secondsLeft;
      
      if (currentSet < sets) {
        // 进入休息阶段
        setPhase('rest');
        setSecondsLeft(restTime);
        speakText('现在开始休息');
      } else {
        // 完成所有训练
        completeTraining();
      }
    } else if (phase === 'rest') {
      // 累计已经休息的时间
      statsRef.current.totalRestTime += restTime - secondsLeft;
      
      // 进入下一组训练
      setCurrentSet((prev: number) => prev + 1);
      setPhase('exercise');
      setSecondsLeft(exerciseTime);
      speakText(`开始第${currentSet + 1}组训练`);
    }
  };
  
  // 完成训练，计算统计数据
  const completeTraining = () => {
    // 累计最后一组训练时间
    if (phase === 'exercise') {
      statsRef.current.totalExerciseTime += exerciseTime - secondsLeft;
    }
    
    statsRef.current.completedSets = currentSet;
    
    const totalTimeMs = Date.now() - statsRef.current.startTime;
    const totalTimeSec = Math.floor(totalTimeMs / 1000);
    
    const finalStats: TrainingStats = {
      totalTime: totalTimeSec,
      completedSets: statsRef.current.completedSets,
      averageSetTime: statsRef.current.completedSets ? 
        Math.floor(statsRef.current.totalExerciseTime / statsRef.current.completedSets) : 0,
      restTime: statsRef.current.totalRestTime,
      exerciseTime: statsRef.current.totalExerciseTime
    };
    
    setStats(finalStats);
    setPhase('complete');
    setIsPaused(true);
    
    speakText('恭喜您，训练已完成！');
    
    // 调用完成回调
    if (onComplete) {
      onComplete(finalStats);
    }
  };
  
  // 打开设置对话框
  const openSettings = () => {
    setIsSettingsOpen(true);
  };
  
  // 保存设置
  const saveSettings = () => {
    setIsSettingsOpen(false);
    resetTimer();
  };
  
  // 处理设置变更
  const handleSettingChange = (
    setting: 'exerciseTime' | 'restTime' | 'sets',
    value: number
  ) => {
    if (value < 1) return;
    
    switch (setting) {
      case 'exerciseTime':
        setExerciseTime(value);
        if (phase === 'prepare') setSecondsLeft(value);
        break;
      case 'restTime':
        setRestTime(value);
        break;
      case 'sets':
        setSets(value);
        break;
    }
  };
  
  // 切换声音设置
  const toggleMute = () => {
    setIsMuted((prev: boolean) => !prev);
  };
  
  // 计时器逻辑
  React.useEffect(() => {
    if (!isPaused && phase !== 'prepare' && phase !== 'complete') {
      timerRef.current = setInterval(() => {
        setSecondsLeft((prev: number) => {
          if (prev <= 1) {
            // 计时结束
            playSound('/sounds/beep.mp3');
            
            if (phase === 'exercise') {
              // 本组训练结束
              statsRef.current.totalExerciseTime += exerciseTime;
              
              if (currentSet < sets) {
                // 进入休息阶段
                setPhase('rest');
                speakText('休息时间');
                return restTime;
              } else {
                // 完成所有训练
                completeTraining();
                return 0;
              }
            } else if (phase === 'rest') {
              // 休息结束
              statsRef.current.totalRestTime += restTime;
              
              // 进入下一组训练
              setCurrentSet((prev: number) => prev + 1);
              setPhase('exercise');
              speakText(`开始第${currentSet + 1}组训练`);
              return exerciseTime;
            }
          }
          return prev - 1;
        });
      }, 1000);
    }
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isPaused, phase, currentSet, exerciseTime, restTime, sets]);
  
  // 在进入每个新阶段时播放提示音
  React.useEffect(() => {
    if (phase === 'exercise') {
      playSound('/sounds/start.mp3');
    } else if (phase === 'rest') {
      playSound('/sounds/rest.mp3');
    } else if (phase === 'complete') {
      playSound('/sounds/complete.mp3');
    }
  }, [phase]);
  
  // 在倒计时最后3秒播放提示音
  React.useEffect(() => {
    if (!isPaused && secondsLeft <= 3 && secondsLeft > 0) {
      playSound('/sounds/tick.mp3');
    }
  }, [secondsLeft, isPaused]);
  
  // 计算进度
  const progress = calculateProgress();
  
  return (
    <Paper 
      elevation={3} 
      sx={{ 
        p: 3, 
        borderRadius: 2,
        position: 'relative',
        overflow: 'hidden',
        border: phase === 'exercise' ? '1px solid #4caf50' : 
               phase === 'rest' ? '1px solid #2196f3' : 
               phase === 'complete' ? '1px solid #9c27b0' : '1px solid #eeeeee',
      }}
    >
      {/* 音频元素 */}
      <audio ref={audioRef} />
      
      {/* 顶部标题和阶段显示 */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <FitnessCenterIcon sx={{ mr: 1 }} />
          <Typography variant="h6">{exerciseName}</Typography>
        </Box>
        
        <Chip 
          label={getPhaseText()}
          color={
            phase === 'exercise' ? 'success' : 
            phase === 'rest' ? 'primary' : 
            phase === 'complete' ? 'secondary' : 'default'
          }
          variant={phase === 'prepare' ? 'outlined' : 'filled'}
          icon={
            phase === 'exercise' ? <FitnessCenterIcon /> : 
            phase === 'rest' ? <TimerIcon /> : 
            phase === 'complete' ? <NotificationsActiveIcon /> : <TimerIcon />
          }
        />
      </Box>
      
      {/* 进度条 */}
      <LinearProgress 
        variant="determinate" 
        value={progress} 
        color={phase === 'exercise' ? 'success' : phase === 'rest' ? 'primary' : 'secondary'}
        sx={{ 
          height: 8, 
          borderRadius: 4, 
          mb: 2,
          '& .MuiLinearProgress-bar': {
            transition: 'transform 1s linear'
          }
        }} 
      />
      
      {/* 计时显示 */}
      <Box 
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          my: 3,
          position: 'relative'
        }}
      >
        <Typography 
          variant="h1"
          sx={{ 
            fontSize: '5rem', 
            fontWeight: 'bold',
            color: phase === 'exercise' ? '#4caf50' : 
                   phase === 'rest' ? '#2196f3' : 
                   phase === 'complete' ? '#9c27b0' : '#757575'
          }}
        >
          {formatTime(secondsLeft)}
        </Typography>
        
        <Typography 
          variant="subtitle1" 
          sx={{ 
            mt: 1,
            color: phase === 'complete' ? 'success.main' : 'text.secondary'
          }}
        >
          {getPhaseInstructionText()}
        </Typography>
      </Box>
      
      {/* 控制按钮 */}
      <Grid container spacing={2} justifyContent="center" sx={{ mb: 2 }}>
        {phase !== 'complete' ? (
          <>
            <Grid item>
              <Button
                variant="contained"
                color={isPaused ? "primary" : "warning"}
                startIcon={isPaused ? <PlayArrowIcon /> : <PauseIcon />}
                onClick={isPaused ? startTimer : pauseTimer}
                size="large"
              >
                {isPaused ? '开始' : '暂停'}
              </Button>
            </Grid>
            
            <Grid item>
              <Button
                variant="outlined"
                startIcon={<SkipNextIcon />}
                onClick={skipPhase}
                disabled={phase === 'prepare'}
              >
                跳过
              </Button>
            </Grid>
            
            <Grid item>
              <Button
                variant="outlined"
                color="error"
                startIcon={<ReplayIcon />}
                onClick={resetTimer}
              >
                重置
              </Button>
            </Grid>
          </>
        ) : (
          <Grid item>
            <Button
              variant="contained"
              color="success"
              startIcon={<ReplayIcon />}
              onClick={resetTimer}
              size="large"
            >
              再次训练
            </Button>
          </Grid>
        )}
      </Grid>
      
      {/* 训练统计信息 - 仅在完成后显示 */}
      {phase === 'complete' && (
        <Box sx={{ mt: 3 }}>
          <Divider sx={{ mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            训练统计
          </Typography>
          
          <Grid container spacing={2}>
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'grey.100' }}>
                <Typography variant="body2" color="textSecondary">总训练时间</Typography>
                <Typography variant="h6">{formatTime(stats.totalTime)}</Typography>
              </Paper>
            </Grid>
            
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'grey.100' }}>
                <Typography variant="body2" color="textSecondary">完成组数</Typography>
                <Typography variant="h6">{stats.completedSets} / {sets}</Typography>
              </Paper>
            </Grid>
            
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'grey.100' }}>
                <Typography variant="body2" color="textSecondary">训练时间</Typography>
                <Typography variant="h6">{formatTime(stats.exerciseTime)}</Typography>
              </Paper>
            </Grid>
            
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 2, textAlign: 'center', bgcolor: 'grey.100' }}>
                <Typography variant="body2" color="textSecondary">休息时间</Typography>
                <Typography variant="h6">{formatTime(stats.restTime)}</Typography>
              </Paper>
            </Grid>
          </Grid>
          
          <Alert severity="success" sx={{ mt: 2 }}>
            恭喜您完成了今天的训练！坚持定期锻炼能够帮助您更快康复。
          </Alert>
        </Box>
      )}
      
      {/* 设置和静音按钮 */}
      <Box sx={{ position: 'absolute', top: 16, right: 16, display: 'flex' }}>
        <Tooltip title={isMuted ? "开启声音" : "静音"}>
          <IconButton onClick={toggleMute} size="small">
            {isMuted ? <VolumeOffIcon /> : <VolumeUpIcon />}
          </IconButton>
        </Tooltip>
        
        <Tooltip title="设置">
          <IconButton onClick={openSettings} size="small" sx={{ ml: 1 }}>
            <SettingsIcon />
          </IconButton>
        </Tooltip>
      </Box>
      
      {/* 设置对话框 */}
      <Dialog open={isSettingsOpen} onClose={() => setIsSettingsOpen(false)}>
        <DialogTitle>训练计时器设置</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <TextField
                label="训练时间 (秒)"
                type="number"
                fullWidth
                value={exerciseTime}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleSettingChange('exerciseTime', parseInt(e.target.value))}
                InputProps={{ inputProps: { min: 5 } }}
              />
            </Grid>
            
            <Grid item xs={12}>
              <TextField
                label="休息时间 (秒)"
                type="number"
                fullWidth
                value={restTime}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleSettingChange('restTime', parseInt(e.target.value))}
                InputProps={{ inputProps: { min: 3 } }}
              />
            </Grid>
            
            <Grid item xs={12}>
              <TextField
                label="训练组数"
                type="number"
                fullWidth
                value={sets}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => handleSettingChange('sets', parseInt(e.target.value))}
                InputProps={{ inputProps: { min: 1 } }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIsSettingsOpen(false)}>取消</Button>
          <Button onClick={saveSettings} variant="contained" color="primary">
            保存
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default TrainingTimer; 