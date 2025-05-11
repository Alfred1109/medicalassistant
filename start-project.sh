#!/bin/bash

# 医疗康复助手 - 项目启动脚本 (优化版)
# 此脚本用于自动启动前端和后端服务，以及必要的依赖服务
# =========================================================

# 显示彩色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 记录当前脚本运行的PID，便于其他脚本引用
echo $$ > .start_script_pid

# 定义项目目录结构
PROJECT_ROOT=$(pwd)
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOGS_DIR="$PROJECT_ROOT/logs"
DATA_DIR="$PROJECT_ROOT/data"
VENV_DIR="$BACKEND_DIR/venv"

# 创建日志目录
mkdir -p "$LOGS_DIR"
mkdir -p "$DATA_DIR"
FRONTEND_LOG="$LOGS_DIR/frontend.log"
BACKEND_LOG="$LOGS_DIR/backend.log"
MONGODB_LOG="$LOGS_DIR/mongodb.log"

# 清空旧日志
> "$FRONTEND_LOG"
> "$BACKEND_LOG"
> "$MONGODB_LOG"

# 打印标题
echo -e "${BLUE}${BOLD}医疗康复助手 - 项目启动脚本${NC}"
echo -e "${BLUE}=======================================${NC}"

# 检查操作系统类型
OS_TYPE=$(uname)
echo -e "${YELLOW}检测到操作系统类型: ${OS_TYPE}${NC}"

# 检查必要工具
check_prerequisite() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${RED}错误: 未找到必要工具 '$1'${NC}"
        echo -e "${YELLOW}请安装 $1 后再继续${NC}"
        if [ "$2" == "critical" ]; then
            exit 1
        fi
    else
        echo -e "${GREEN}✓ $1 已安装${NC}"
    fi
}

echo -e "\n${BLUE}检查必要工具...${NC}"
check_prerequisite node critical
check_prerequisite npm critical
check_prerequisite python3 critical
if [ "$OS_TYPE" == "Darwin" ]; then
    check_prerequisite brew
fi

# 自动启动MongoDB服务
start_mongodb() {
    echo -e "\n${BLUE}检查并启动MongoDB服务...${NC}"
    
    # 检查MongoDB是否已在运行
    if pgrep mongod > /dev/null; then
        echo -e "${GREEN}✓ 发现运行中的MongoDB进程${NC}"
        return 0
    fi
    
    # MongoDB未运行，尝试启动
    echo -e "${YELLOW}未检测到运行中的MongoDB进程，尝试启动...${NC}"
    
    if [ "$OS_TYPE" == "Darwin" ]; then
        # macOS - 尝试通过Homebrew启动
        if command -v brew &> /dev/null && brew services list | grep -q mongodb-community; then
            echo -e "${YELLOW}通过Homebrew启动MongoDB...${NC}"
            brew services start mongodb-community >> "$MONGODB_LOG" 2>&1
            sleep 2
            if pgrep mongod > /dev/null; then
                echo -e "${GREEN}✓ MongoDB服务已通过Homebrew成功启动${NC}"
                return 0
            fi
        fi
        
        # 如果Homebrew启动失败或者没有通过Homebrew安装，尝试直接启动
        echo -e "${YELLOW}尝试直接启动MongoDB...${NC}"
        mongod --dbpath="$DATA_DIR" --fork --logpath="$MONGODB_LOG" >> "$MONGODB_LOG" 2>&1
        sleep 2
        if pgrep mongod > /dev/null; then
            echo -e "${GREEN}✓ MongoDB服务已成功启动${NC}"
            return 0
        fi
    else
        # Linux - 尝试通过systemd启动
        if command -v systemctl &> /dev/null; then
            echo -e "${YELLOW}通过systemd启动MongoDB...${NC}"
            sudo systemctl start mongod >> "$MONGODB_LOG" 2>&1
            sleep 2
            if systemctl is-active --quiet mongod || pgrep mongod > /dev/null; then
                echo -e "${GREEN}✓ MongoDB服务已通过systemd成功启动${NC}"
                return 0
            fi
        fi
        
        # 如果systemd启动失败，尝试直接启动
        echo -e "${YELLOW}尝试直接启动MongoDB...${NC}"
        mongod --dbpath="$DATA_DIR" --fork --logpath="$MONGODB_LOG" >> "$MONGODB_LOG" 2>&1
        sleep 2
        if pgrep mongod > /dev/null; then
            echo -e "${GREEN}✓ MongoDB服务已成功启动${NC}"
            return 0
        fi
    fi
    
    # 所有尝试都失败了
    echo -e "${RED}无法启动MongoDB服务${NC}"
    echo -e "${RED}项目部分功能可能无法使用${NC}"
    echo -e "${YELLOW}将继续启动前端和后端服务...${NC}"
    return 1
}

# 清理之前的项目进程
cleanup_processes() {
    echo -e "\n${BLUE}清理之前的项目进程...${NC}"
    
    # 手动清理进程的逻辑
    local FRONTEND_PIDS=$(pgrep -f "node.*vite" | grep -v $$)
    local BACKEND_PIDS=$(pgrep -f "python.*app.py" | grep -v $$)
    local UVICORN_PIDS=$(pgrep -f "uvicorn.*app:app" | grep -v $$)
    
    if [ -n "$FRONTEND_PIDS" ]; then
        echo -e "${YELLOW}发现前端进程，正在终止...${NC}"
        for pid in $FRONTEND_PIDS; do
            echo -e "终止前端进程: $pid"
            kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
        done
    else
        echo -e "${GREEN}✓ 未发现其他前端进程${NC}"
    fi
    
    if [ -n "$BACKEND_PIDS" ] || [ -n "$UVICORN_PIDS" ]; then
        echo -e "${YELLOW}发现后端进程，正在终止...${NC}"
        for pid in $BACKEND_PIDS $UVICORN_PIDS; do
            echo -e "终止后端进程: $pid"
            kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
        done
    else
        echo -e "${GREEN}✓ 未发现其他后端进程${NC}"
    fi
    
    # 清理PID文件
    [ -f .frontend_pid ] && rm .frontend_pid
    [ -f "$BACKEND_DIR/.backend_pid" ] && rm "$BACKEND_DIR/.backend_pid"
    
    # 等待进程结束
    sleep 2
    
    # 检查端口占用
    echo -e "\n${BLUE}检查端口占用情况...${NC}"
    local port_5501_free=true
    local port_5502_free=true
    
    # 检查前端端口
    if [ "$OS_TYPE" == "Darwin" ]; then
        if lsof -i :5501 | grep -q LISTEN; then
            port_5501_free=false
            local pid=$(lsof -i :5501 | grep LISTEN | awk '{print $2}' | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${YELLOW}端口5501被进程 $pid ($pname) 占用，尝试强制终止...${NC}"
            kill -9 $pid 2>/dev/null
            sleep 1
            if ! lsof -i :5501 | grep -q LISTEN; then
                port_5501_free=true
                echo -e "${GREEN}✓ 端口5501已释放${NC}"
            else
                echo -e "${RED}无法释放端口5501${NC}"
            fi
        else
            echo -e "${GREEN}✓ 端口5501可用${NC}"
        fi
        
        # 检查后端端口
        if lsof -i :5502 | grep -q LISTEN; then
            port_5502_free=false
            local pid=$(lsof -i :5502 | grep LISTEN | awk '{print $2}' | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${YELLOW}端口5502被进程 $pid ($pname) 占用，尝试强制终止...${NC}"
            kill -9 $pid 2>/dev/null
            sleep 1
            if ! lsof -i :5502 | grep -q LISTEN; then
                port_5502_free=true
                echo -e "${GREEN}✓ 端口5502已释放${NC}"
            else
                echo -e "${RED}无法释放端口5502${NC}"
            fi
        else
            echo -e "${GREEN}✓ 端口5502可用${NC}"
        fi
    else
        # Linux
        if netstat -tuln | grep -q ":5501 "; then
            port_5501_free=false
            local pid=$(netstat -tulnp 2>/dev/null | grep ":5501 " | awk '{print $7}' | cut -d'/' -f1 | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${YELLOW}端口5501被进程 $pid ($pname) 占用，尝试强制终止...${NC}"
            kill -9 $pid 2>/dev/null
            sleep 1
            if ! netstat -tuln | grep -q ":5501 "; then
                port_5501_free=true
                echo -e "${GREEN}✓ 端口5501已释放${NC}"
            else
                echo -e "${RED}无法释放端口5501${NC}"
            fi
        else
            echo -e "${GREEN}✓ 端口5501可用${NC}"
        fi
        
        # 检查后端端口
        if netstat -tuln | grep -q ":5502 "; then
            port_5502_free=false
            local pid=$(netstat -tulnp 2>/dev/null | grep ":5502 " | awk '{print $7}' | cut -d'/' -f1 | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${YELLOW}端口5502被进程 $pid ($pname) 占用，尝试强制终止...${NC}"
            kill -9 $pid 2>/dev/null
            sleep 1
            if ! netstat -tuln | grep -q ":5502 "; then
                port_5502_free=true
                echo -e "${GREEN}✓ 端口5502已释放${NC}"
            else
                echo -e "${RED}无法释放端口5502${NC}"
            fi
        else
            echo -e "${GREEN}✓ 端口5502可用${NC}"
        fi
    fi
    
    # 如果端口仍然被占用，返回失败
    if [ "$port_5501_free" = false ] || [ "$port_5502_free" = false ]; then
        echo -e "${RED}无法释放所需端口，启动可能失败${NC}"
        echo -e "${YELLOW}将尝试继续启动服务...${NC}"
    else
        echo -e "${GREEN}✓ 所有必要端口检查通过${NC}"
    fi
    
    return 0
}

# 启动前端服务
start_frontend() {
    echo -e "\n${BLUE}启动前端服务...${NC}"
    
    cd "$FRONTEND_DIR" || {
        echo -e "${RED}错误: 无法进入前端目录 $FRONTEND_DIR${NC}"
        return 1
    }
    
    # 检查node_modules是否存在
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}前端依赖不存在，正在安装...${NC}"
        npm install --legacy-peer-deps >> "$FRONTEND_LOG" 2>&1
        if [ $? -ne 0 ]; then
            echo -e "${RED}前端依赖安装失败，请检查日志: $FRONTEND_LOG${NC}"
            echo -e "${YELLOW}尝试继续启动...${NC}"
        fi
    fi
    
    # 清理缓存
    echo -e "${YELLOW}清理前端缓存...${NC}"
    rm -rf node_modules/.vite 2>/dev/null
    
    # 启动前端服务
    echo -e "${YELLOW}正在启动前端服务(端口5501)...${NC}"
    npm run dev >> "$FRONTEND_LOG" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > .frontend_pid
    
    # 等待服务启动
    echo -e "${YELLOW}等待前端服务启动...${NC}"
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if grep -q "ready in" "$FRONTEND_LOG" || grep -q "Local:" "$FRONTEND_LOG"; then
            echo -e "${GREEN}✓ 前端服务已成功启动 (PID: $FRONTEND_PID)${NC}"
            echo -e "${GREEN}✓ 前端地址: http://localhost:5501${NC}"
            return 0
        fi
        
        # 检查进程是否仍在运行
        if ! kill -0 $FRONTEND_PID 2>/dev/null; then
            echo -e "${RED}前端服务启动失败，进程已退出${NC}"
            echo -e "${YELLOW}请检查日志: $FRONTEND_LOG${NC}"
            cat "$FRONTEND_LOG" | tail -n 20
            return 1
        fi
        
        sleep 1
        attempt=$((attempt + 1))
        echo -n "."
    done
    
    echo -e "\n${RED}前端服务启动超时${NC}"
    echo -e "${YELLOW}请检查日志: $FRONTEND_LOG${NC}"
    return 1
}

# 启动后端服务
start_backend() {
    echo -e "\n${BLUE}启动后端服务...${NC}"
    
    # 进入后端目录
    cd "$BACKEND_DIR" || {
        echo -e "${RED}错误: 无法进入后端目录 $BACKEND_DIR${NC}"
        return 1
    }
    
    # 检查并激活虚拟环境
    echo -e "${BLUE}检查虚拟环境...${NC}"
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}虚拟环境不存在，创建新的虚拟环境...${NC}"
        python3 -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            echo -e "${RED}创建虚拟环境失败${NC}"
            return 1
        fi
    fi
    
    # 激活虚拟环境
    echo -e "${BLUE}激活虚拟环境...${NC}"
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    else
        echo -e "${RED}无法找到虚拟环境激活脚本${NC}"
        return 1
    fi
    
    # 检查虚拟环境是否成功激活
    if [ -z "$VIRTUAL_ENV" ]; then
        echo -e "${RED}虚拟环境激活失败${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
    
    # 安装依赖
    echo -e "${BLUE}检查并安装依赖...${NC}"
    
    # 升级pip
    echo -e "${YELLOW}升级pip...${NC}"
    pip install --upgrade pip > /dev/null 2>&1
    
    # 检查requirements.txt是否存在
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}缺少requirements.txt文件${NC}"
        return 1
    fi
    
    # 安装依赖
    echo -e "${YELLOW}安装项目依赖...${NC}"
    pip install -r requirements.txt > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${RED}依赖安装失败${NC}"
        echo -e "${YELLOW}尝试修复依赖冲突...${NC}"
        
        # 特别处理bson和pymongo的版本冲突
        pip uninstall -y bson pymongo > /dev/null 2>&1
        pip install pymongo==4.5.0 > /dev/null 2>&1
        
        # 再次尝试安装所有依赖
        pip install -r requirements.txt > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo -e "${RED}依赖安装仍然失败，但将继续尝试启动服务...${NC}"
        fi
    fi
    echo -e "${GREEN}✓ 依赖安装完成${NC}"
    
    # 删除旧的PID文件(如果存在)
    if [ -f ".backend_pid" ]; then
        rm -f ".backend_pid"
    fi
    
    # 启动服务
    echo -e "${YELLOW}启动FastAPI应用(端口5502)...${NC}"
    python -m uvicorn app.main:app --host 0.0.0.0 --port 5502 --reload > "$BACKEND_LOG" 2>&1 &
    
    # 保存PID
    BACKEND_PID=$!
    echo $BACKEND_PID > .backend_pid
    
    # 等待服务启动
    echo -e "${YELLOW}等待后端服务启动...${NC}"
    sleep 10
    
    # 检查服务是否成功启动
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${GREEN}✓ 后端服务已成功启动 (PID: $BACKEND_PID)${NC}"
        echo -e "${GREEN}✓ 后端API地址: http://localhost:5502/api${NC}"
        
        # 回到项目根目录
        cd "$PROJECT_ROOT"
        return 0
    else
        echo -e "${RED}后端服务启动失败${NC}"
        echo -e "${YELLOW}请检查日志: $BACKEND_LOG${NC}"
        
        # 回到项目根目录
        cd "$PROJECT_ROOT"
        return 1
    fi
}

# 主流程
main() {
    # 清理之前的进程
    cleanup_processes
    
    # 启动MongoDB
    start_mongodb
    
    # 启动后端服务
    start_backend
    
    # 启动前端
    start_frontend
    
    # 所有服务启动完成
    echo -e "\n${GREEN}${BOLD}服务启动完成!${NC}"
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${GREEN}前端地址: ${BOLD}http://localhost:5501${NC}"
    echo -e "${GREEN}后端API地址: ${BOLD}http://localhost:5502/api${NC}"
    echo -e "${YELLOW}日志文件:${NC}"
    echo -e "  - 前端日志: $FRONTEND_LOG"
    echo -e "  - 后端日志: $BACKEND_LOG"
    echo -e "  - MongoDB日志: $MONGODB_LOG"
    echo -e "${YELLOW}提示: 使用 stop-project.sh 脚本停止所有服务${NC}"
    echo -e "${BLUE}=======================================${NC}"
    
    # 返回项目根目录
    cd "$PROJECT_ROOT"
    return 0
}

# 执行主函数
main 