#!/bin/bash

# 医疗康复助手 - 项目启动脚本
# 此脚本用于启动前端和后端服务
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

# 创建日志目录
mkdir -p "$LOGS_DIR"
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

# 检查MongoDB服务
check_mongodb() {
    echo -e "\n${BLUE}检查MongoDB服务...${NC}"
    if [ "$OS_TYPE" == "Darwin" ]; then
        # macOS
        if brew services list | grep -q mongodb-community; then
            if brew services list | grep mongodb-community | grep -q started; then
                echo -e "${GREEN}✓ MongoDB服务正在运行${NC}"
                return 0
            else
                echo -e "${YELLOW}MongoDB服务未运行，尝试启动...${NC}"
                brew services start mongodb-community >> "$MONGODB_LOG" 2>&1
                sleep 3
                if brew services list | grep mongodb-community | grep -q started; then
                    echo -e "${GREEN}✓ MongoDB服务已成功启动${NC}"
                    return 0
                else
                    echo -e "${RED}MongoDB服务启动失败${NC}"
                    echo -e "${YELLOW}请尝试运行 mongodb-fix.sh 脚本修复问题${NC}"
                    return 1
                fi
            fi
        else
            echo -e "${YELLOW}未检测到通过Homebrew安装的MongoDB${NC}"
            if pgrep mongod > /dev/null; then
                echo -e "${GREEN}✓ 发现运行中的MongoDB进程${NC}"
                return 0
            else
                echo -e "${RED}未检测到运行中的MongoDB进程${NC}"
                echo -e "${YELLOW}请安装MongoDB或确保MongoDB服务已启动${NC}"
                return 1
            fi
        fi
    else
        # Linux
        if command -v systemctl &> /dev/null; then
            if systemctl is-active --quiet mongod; then
                echo -e "${GREEN}✓ MongoDB服务正在运行${NC}"
                return 0
            else
                echo -e "${YELLOW}MongoDB服务未运行，尝试启动...${NC}"
                sudo systemctl start mongod >> "$MONGODB_LOG" 2>&1
                sleep 3
                if systemctl is-active --quiet mongod; then
                    echo -e "${GREEN}✓ MongoDB服务已成功启动${NC}"
                    return 0
                else
                    echo -e "${RED}MongoDB服务启动失败${NC}"
                    echo -e "${YELLOW}请尝试运行 mongodb-fix.sh 脚本修复问题${NC}"
                    return 1
                fi
            fi
        else
            if pgrep mongod > /dev/null; then
                echo -e "${GREEN}✓ 发现运行中的MongoDB进程${NC}"
                return 0
            else
                echo -e "${RED}未检测到运行中的MongoDB进程${NC}"
                echo -e "${YELLOW}请安装MongoDB或确保MongoDB服务已启动${NC}"
                return 1
            fi
        fi
    fi
}

# 检查端口占用
check_port() {
    local port=$1
    local service=$2
    
    # 检查端口是否被占用
    if [ "$OS_TYPE" == "Darwin" ]; then
        # macOS
        if lsof -i :$port | grep -q LISTEN; then
            local pid=$(lsof -i :$port | grep LISTEN | awk '{print $2}' | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${RED}错误: 端口 $port 已被进程 $pid ($pname) 占用${NC}"
            echo -e "${YELLOW}请停止该进程或修改 $service 服务的端口配置${NC}"
            return 1
        fi
    else
        # Linux
        if netstat -tuln | grep -q ":$port "; then
            local pid=$(netstat -tulnp 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1 | head -n 1)
            local pname=$(ps -p $pid -o comm= 2>/dev/null || echo "未知进程")
            echo -e "${RED}错误: 端口 $port 已被进程 $pid ($pname) 占用${NC}"
            echo -e "${YELLOW}请停止该进程或修改 $service 服务的端口配置${NC}"
            return 1
        fi
    fi
    
    return 0
}

# 清理之前的项目进程
cleanup_processes() {
    echo -e "\n${BLUE}清理之前的项目进程...${NC}"
    
    # 如果存在stop-project.sh脚本，则执行它
    if [ -f "$PROJECT_ROOT/stop-project.sh" ]; then
        echo -e "${YELLOW}执行stop-project.sh脚本...${NC}"
        bash "$PROJECT_ROOT/stop-project.sh"
        sleep 2
    else
        echo -e "${YELLOW}未找到stop-project.sh脚本，尝试手动清理进程...${NC}"
        # 手动清理进程的逻辑
        if [ "$OS_TYPE" == "Darwin" ]; then
            # macOS
            FRONTEND_PIDS=$(pgrep -f "node.*vite" | grep -v $$)
            BACKEND_PIDS=$(pgrep -f "python.*app.py" | grep -v $$)
        else
            # Linux
            FRONTEND_PIDS=$(pgrep -f "node.*vite" | grep -v $$)
            BACKEND_PIDS=$(pgrep -f "python.*app.py" | grep -v $$)
        fi
        
        if [ -n "$FRONTEND_PIDS" ]; then
            echo -e "${YELLOW}发现前端进程，正在终止...${NC}"
            for pid in $FRONTEND_PIDS; do
                echo -e "终止前端进程: $pid"
                kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
            done
        fi
        
        if [ -n "$BACKEND_PIDS" ]; then
            echo -e "${YELLOW}发现后端进程，正在终止...${NC}"
            for pid in $BACKEND_PIDS; do
                echo -e "终止后端进程: $pid"
                kill -15 $pid 2>/dev/null || kill -9 $pid 2>/dev/null
            done
        fi
        
        sleep 2
    fi
    
    # 检查端口占用
    echo -e "\n${BLUE}检查端口占用情况...${NC}"
    check_port 5501 "前端" || return 1
    check_port 5502 "后端" || return 1
    
    echo -e "${GREEN}✓ 端口检查通过${NC}"
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
            return 1
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
    
    cd "$BACKEND_DIR" || {
        echo -e "${RED}错误: 无法进入后端目录 $BACKEND_DIR${NC}"
        return 1
    }
    
    # 检查Python虚拟环境
    if [ -d "venv" ]; then
        echo -e "${YELLOW}激活Python虚拟环境...${NC}"
        source venv/bin/activate 2>/dev/null || {
            echo -e "${RED}无法激活虚拟环境，尝试继续...${NC}"
        }
    fi
    
    # 检查依赖
    if [ ! -f "requirements.txt" ]; then
        echo -e "${RED}错误: 未找到requirements.txt文件${NC}"
        return 1
    fi
    
    # 启动后端服务
    echo -e "${YELLOW}正在启动后端服务(端口5502)...${NC}"
    python3 -m app.main >> "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > .backend_pid
    
    # 等待服务启动
    echo -e "${YELLOW}等待后端服务启动...${NC}"
    local max_attempts=30
    local attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if grep -q "Running on http" "$BACKEND_LOG"; then
            echo -e "${GREEN}✓ 后端服务已成功启动 (PID: $BACKEND_PID)${NC}"
            echo -e "${GREEN}✓ 后端API地址: http://localhost:5502/api${NC}"
            return 0
        fi
        
        # 检查进程是否仍在运行
        if ! kill -0 $BACKEND_PID 2>/dev/null; then
            echo -e "${RED}后端服务启动失败，进程已退出${NC}"
            echo -e "${YELLOW}请检查日志: $BACKEND_LOG${NC}"
            cat "$BACKEND_LOG" | tail -n 20
            return 1
        fi
        
        sleep 1
        attempt=$((attempt + 1))
        echo -n "."
    done
    
    echo -e "\n${RED}后端服务启动超时${NC}"
    echo -e "${YELLOW}请检查日志: $BACKEND_LOG${NC}"
    return 1
}

# 主流程
main() {
    # 检查MongoDB
    check_mongodb || {
        echo -e "${YELLOW}是否继续启动项目? (y/n) ${NC}"
        read -r continue_without_mongo
        if [ "$continue_without_mongo" != "y" ] && [ "$continue_without_mongo" != "Y" ]; then
            echo -e "${RED}项目启动已取消${NC}"
            exit 1
        fi
        echo -e "${YELLOW}警告: 在没有MongoDB的情况下继续启动项目，部分功能可能不可用${NC}"
    }
    
    # 清理之前的进程
    cleanup_processes || {
        echo -e "${YELLOW}是否忽略端口占用问题并继续? (y/n) ${NC}"
        read -r ignore_port_issues
        if [ "$ignore_port_issues" != "y" ] && [ "$ignore_port_issues" != "Y" ]; then
            echo -e "${RED}项目启动已取消${NC}"
            exit 1
        fi
        echo -e "${YELLOW}警告: 忽略端口占用问题继续启动，可能导致服务异常${NC}"
    }
    
    # 启动后端服务
    start_backend || {
        echo -e "${RED}后端服务启动失败${NC}"
        echo -e "${YELLOW}是否继续启动前端? (y/n) ${NC}"
        read -r continue_without_backend
        if [ "$continue_without_backend" != "y" ] && [ "$continue_without_backend" != "Y" ]; then
            echo -e "${RED}项目启动已取消${NC}"
            exit 1
        fi
    }
    
    # 启动前端服务
    start_frontend || {
        echo -e "${RED}前端服务启动失败${NC}"
        exit 1
    }
    
    # 所有服务启动完成
    echo -e "\n${GREEN}${BOLD}所有服务已启动完成!${NC}"
    echo -e "${BLUE}=======================================${NC}"
    echo -e "${GREEN}前端地址: ${BOLD}http://localhost:5501${NC}"
    echo -e "${GREEN}后端API地址: ${BOLD}http://localhost:5502/api${NC}"
    echo -e "${YELLOW}日志文件:${NC}"
    echo -e "  - 前端日志: $FRONTEND_LOG"
    echo -e "  - 后端日志: $BACKEND_LOG"
    echo -e "${YELLOW}提示: 使用 stop-project.sh 脚本停止所有服务${NC}"
    echo -e "${BLUE}=======================================${NC}"
    
    # 返回项目根目录
    cd "$PROJECT_ROOT"
}

# 执行主函数
main 