#!/bin/bash

# 智能康复助手 - 后端启动脚本
# 此脚本专门用于启动后端服务，提供更精确的环境控制

# 显示彩色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 定义目录结构
PROJECT_ROOT=$(pwd)
BACKEND_DIR="$PROJECT_ROOT/backend"
LOGS_DIR="$PROJECT_ROOT/logs"
BACKEND_LOG="$LOGS_DIR/backend.log"

# 确保日志目录存在
mkdir -p "$LOGS_DIR"
# 清空旧日志
> "$BACKEND_LOG"

echo -e "${BLUE}${BOLD}智能康复助手 - 后端启动脚本${NC}"
echo -e "${BLUE}=======================================${NC}"

# 进入后端目录
cd "$BACKEND_DIR" || {
    echo -e "${RED}错误: 无法进入后端目录 $BACKEND_DIR${NC}"
    exit 1
}

# 激活虚拟环境
if [ -d "venv" ]; then
    echo -e "${YELLOW}激活Python虚拟环境...${NC}"
    source venv/bin/activate || {
        echo -e "${RED}无法激活虚拟环境${NC}"
        exit 1
    }
else
    echo -e "${RED}错误: 虚拟环境不存在${NC}"
    exit 1
fi

# 检查并关闭现有的后端进程
echo -e "${YELLOW}检查并关闭现有的后端进程...${NC}"
BACKEND_PIDS=$(pgrep -f "uvicorn app.main:app" | tr '\n' ' ')
if [ -n "$BACKEND_PIDS" ]; then
    echo -e "${YELLOW}发现运行中的后端进程 ($BACKEND_PIDS)，正在关闭...${NC}"
    kill -15 $BACKEND_PIDS 2>/dev/null
    sleep 2
    # 强制终止仍在运行的进程
    kill -9 $BACKEND_PIDS 2>/dev/null
    echo -e "${GREEN}✓ 已关闭旧进程${NC}"
else
    echo -e "${GREEN}✓ 未发现运行中的后端进程${NC}"
fi

# 直接使用uvicorn启动
echo -e "${YELLOW}正在启动后端服务(端口5502)...${NC}"
echo -e "${YELLOW}使用环境: PYTHONPATH=$BACKEND_DIR${NC}"
PYTHONPATH="$BACKEND_DIR" uvicorn app.main:app --host 0.0.0.0 --port 5502 --reload > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > .backend_pid

echo -e "${GREEN}✓ 后端服务已启动 (PID: $BACKEND_PID)${NC}"
echo -e "${GREEN}✓ 后端API地址: http://localhost:5502/api${NC}"
echo -e "${YELLOW}日志文件: $BACKEND_LOG${NC}"
echo -e "${BLUE}=======================================${NC}"

# 显示日志（可选，取消注释下面行以启用）
# tail -f "$BACKEND_LOG" 