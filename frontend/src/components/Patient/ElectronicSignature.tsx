import React, { useRef, useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Button, Grid, Divider,
  Dialog, DialogActions, DialogContent, DialogTitle
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import ClearIcon from '@mui/icons-material/Clear';
import UndoIcon from '@mui/icons-material/Undo';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

// 组件属性定义
interface ElectronicSignatureProps {
  onSave?: (signatureDataUrl: string) => void;
  initialSignature?: string;
  width?: number;
  height?: number;
  disabled?: boolean;
  label?: string;
  instructionText?: string;
}

// 签名选项定义
interface SignatureOptions {
  penColor: string;
  penWidth: number;
}

const defaultOptions: SignatureOptions = {
  penColor: '#000000',
  penWidth: 2
};

const ElectronicSignature: React.FC<ElectronicSignatureProps> = ({
  onSave,
  initialSignature,
  width = 500,
  height = 200,
  disabled = false,
  label = '请在下方框内签名',
  instructionText = '使用鼠标或触摸屏在签名区域内签名。点击"保存"完成签名或点击"清除"重新签名。'
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasSignature, setHasSignature] = useState(false);
  const [showInstructions, setShowInstructions] = useState(false);
  const [options, setOptions] = useState<SignatureOptions>(defaultOptions);
  const [undoStack, setUndoStack] = useState<ImageData[]>([]);
  
  // 获取Canvas上下文
  const getContext = () => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    
    // 设置绘制选项
    ctx.strokeStyle = options.penColor;
    ctx.lineWidth = options.penWidth;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    
    return ctx;
  };
  
  // 清除画布
  const clearCanvas = () => {
    const canvas = canvasRef.current;
    const ctx = getContext();
    if (!canvas || !ctx) return;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    setHasSignature(false);
    setUndoStack([]);
  };
  
  // 初始化画布
  const initCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    // 设置Canvas尺寸
    canvas.width = width;
    canvas.height = height;
    
    // 设置Canvas的样式尺寸
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    
    // 清除画布
    clearCanvas();
    
    // 如果有初始签名，则显示初始签名
    if (initialSignature) {
      const img = new Image();
      img.onload = () => {
        const ctx = getContext();
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          setHasSignature(true);
        }
      };
      img.src = initialSignature;
    }
  };
  
  // 保存当前画布状态用于撤销
  const saveState = () => {
    const canvas = canvasRef.current;
    const ctx = getContext();
    if (!canvas || !ctx) return;
    
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    setUndoStack(prev => [...prev, imageData]);
  };
  
  // 撤销上一步
  const handleUndo = () => {
    const canvas = canvasRef.current;
    const ctx = getContext();
    if (!canvas || !ctx || undoStack.length === 0) return;
    
    // 移除最后一个状态
    const newStack = [...undoStack];
    newStack.pop();
    setUndoStack(newStack);
    
    // 清除画布
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 如果还有之前的状态，则恢复到上一个状态
    if (newStack.length > 0) {
      ctx.putImageData(newStack[newStack.length - 1], 0, 0);
    } else {
      setHasSignature(false);
    }
  };
  
  // 保存签名
  const handleSave = () => {
    if (!hasSignature || !canvasRef.current || !onSave) return;
    
    // 获取签名的数据URL
    const dataUrl = canvasRef.current.toDataURL('image/png');
    onSave(dataUrl);
  };
  
  // 处理鼠标/触摸开始
  const handleStart = (e: React.MouseEvent | React.TouchEvent) => {
    if (disabled) return;
    
    const ctx = getContext();
    if (!ctx) return;
    
    setIsDrawing(true);
    
    // 保存当前状态用于撤销
    saveState();
    
    // 获取鼠标/触摸位置
    let clientX, clientY;
    if ('touches' in e) {
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }
    
    // 获取Canvas的位置
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    
    // 开始新的路径
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  
  // 处理鼠标/触摸移动
  const handleMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isDrawing || disabled) return;
    
    const ctx = getContext();
    if (!ctx) return;
    
    // 获取鼠标/触摸位置
    let clientX, clientY;
    if ('touches' in e) {
      e.preventDefault(); // 防止滚动
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }
    
    // 获取Canvas的位置
    const canvas = canvasRef.current;
    if (!canvas) return;
    
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    
    // 绘制路径
    ctx.lineTo(x, y);
    ctx.stroke();
    
    setHasSignature(true);
  };
  
  // 处理鼠标/触摸结束
  const handleEnd = () => {
    setIsDrawing(false);
  };
  
  // 处理笔颜色变化
  const handleColorChange = (color: string) => {
    setOptions({
      ...options,
      penColor: color
    });
  };
  
  // 处理笔宽度变化
  const handleWidthChange = (width: number) => {
    setOptions({
      ...options,
      penWidth: width
    });
  };
  
  // 初始化组件
  useEffect(() => {
    initCanvas();
    
    // 注册全局事件监听器以处理画布外的鼠标松开/触摸结束
    const handleGlobalEnd = () => {
      setIsDrawing(false);
    };
    
    window.addEventListener('mouseup', handleGlobalEnd);
    window.addEventListener('touchend', handleGlobalEnd);
    
    return () => {
      window.removeEventListener('mouseup', handleGlobalEnd);
      window.removeEventListener('touchend', handleGlobalEnd);
    };
  }, []);
  
  // 当选项变化时更新上下文
  useEffect(() => {
    const ctx = getContext();
    if (ctx) {
      ctx.strokeStyle = options.penColor;
      ctx.lineWidth = options.penWidth;
    }
  }, [options]);
  
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="subtitle1">
          {label}
          <InfoOutlinedIcon
            fontSize="small"
            onClick={() => setShowInstructions(true)}
            sx={{ ml: 1, cursor: 'pointer', verticalAlign: 'middle' }}
          />
        </Typography>
        
        <Box>
          {/* 颜色选择按钮 */}
          <Box display="flex" gap={1} mr={2} component="span">
            {['#000000', '#0000FF', '#FF0000'].map(color => (
              <Box
                key={color}
                sx={{
                  width: 20,
                  height: 20,
                  bgcolor: color,
                  border: options.penColor === color ? '2px solid #999' : '1px solid #ccc',
                  cursor: 'pointer',
                  borderRadius: '50%'
                }}
                onClick={() => handleColorChange(color)}
              />
            ))}
          </Box>
          
          {/* 宽度选择按钮 */}
          <Box display="flex" gap={1} component="span">
            {[1, 2, 4].map(width => (
              <Box
                key={width}
                sx={{
                  width: width * 5,
                  height: width * 5,
                  bgcolor: 'black',
                  border: options.penWidth === width ? '2px solid #999' : '1px solid transparent',
                  cursor: 'pointer',
                  borderRadius: '50%'
                }}
                onClick={() => handleWidthChange(width)}
              />
            ))}
          </Box>
        </Box>
      </Box>
      
      <Paper
        variant="outlined"
        sx={{
          position: 'relative',
          width: width,
          height: height,
          cursor: disabled ? 'not-allowed' : 'crosshair',
          mb: 2
        }}
      >
        <canvas
          ref={canvasRef}
          onMouseDown={handleStart}
          onMouseMove={handleMove}
          onMouseUp={handleEnd}
          onMouseLeave={handleEnd}
          onTouchStart={handleStart}
          onTouchMove={handleMove}
          onTouchEnd={handleEnd}
          style={{
            border: '1px dashed #ccc',
            touchAction: 'none',
            opacity: disabled ? 0.5 : 1
          }}
        />
        
        {!hasSignature && (
          <Typography
            variant="body2"
            color="textSecondary"
            sx={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              pointerEvents: 'none',
              userSelect: 'none'
            }}
          >
            在此处签名
          </Typography>
        )}
      </Paper>
      
      <Grid container spacing={2}>
        <Grid item>
          <Button
            variant="outlined"
            startIcon={<ClearIcon />}
            onClick={clearCanvas}
            disabled={!hasSignature || disabled}
          >
            清除
          </Button>
        </Grid>
        <Grid item>
          <Button
            variant="outlined"
            startIcon={<UndoIcon />}
            onClick={handleUndo}
            disabled={undoStack.length === 0 || disabled}
          >
            撤销
          </Button>
        </Grid>
        <Grid item>
          <Button
            variant="contained"
            color="primary"
            startIcon={<SaveIcon />}
            onClick={handleSave}
            disabled={!hasSignature || disabled}
          >
            保存签名
          </Button>
        </Grid>
      </Grid>
      
      {/* 使用说明对话框 */}
      <Dialog open={showInstructions} onClose={() => setShowInstructions(false)}>
        <DialogTitle>电子签名说明</DialogTitle>
        <DialogContent>
          <Typography variant="body1" paragraph>
            {instructionText}
          </Typography>
          <Divider sx={{ my: 2 }} />
          <Typography variant="body2">
            注意：您的电子签名将被安全保存，并具有与手写签名相同的法律效力。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowInstructions(false)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ElectronicSignature; 