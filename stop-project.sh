#!/bin/bash

# 医疗康复助手 - 项目停止脚本
# 此脚本用于停止前端和后端服务
# =========================================================

# 显示彩色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 打印标题
echo -e "${RED}${BOLD}医疗康复助手 - 项目停止脚本${NC}"
echo -e "${RED}=======================================${NC}"

# 定义项目目录结构
PROJECT_ROOT=$(pwd)
FRONTEND_DIR="$PROJECT_ROOT/frontend"
BACKEND_DIR="$PROJECT_ROOT/backend"
LOGS_DIR="$PROJECT_ROOT/logs"

# 检查操作系统类型
OS_TYPE=$(uname)
echo -e "${YELLOW}检测到操作系统类型: ${OS_TYPE}${NC}"

# 停止前端服务
stop_frontend() {
    echo -e "\n${BLUE}停止前端服务...${NC}"
    
    # 获取前端PID
    local pid_file="$FRONTEND_DIR/.frontend_pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}发现前端进程(PID: $pid)，正在停止...${NC}"
            kill -15 "$pid" 2>/dev/null
            
            # 等待进程终止
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 0.5
                count=$((count+1))
            done
            
            # 如果进程仍在运行，强制终止
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}前端进程未响应，强制终止...${NC}"
                kill -9 "$pid" 2>/dev/null
            fi
            
            # 验证进程已终止
            if ! kill -0 "$pid" 2>/dev/null; then
                echo -e "${GREEN}✓ 前端服务已停止${NC}"
                rm -f "$pid_file"
            else
                echo -e "${RED}无法停止前端服务${NC}"
            fi
        else
            echo -e "${YELLOW}找不到运行中的前端进程或PID文件无效${NC}"
        fi
    else
        echo -e "${YELLOW}未找到前端PID文件，尝试通过进程名查找...${NC}"
    fi
    
    # 查找并终止所有相关前端进程
    if [ "$OS_TYPE" == "Darwin" ]; then
        # macOS
        FRONTEND_PIDS=$(pgrep -f "node.*vite" | grep -v $$)
    else
        # Linux
        FRONTEND_PIDS=$(pgrep -f "node.*vite" | grep -v $$)
    fi
    
    if [ -n "$FRONTEND_PIDS" ]; then
        echo -e "${YELLOW}发现额外的前端进程，正在终止...${NC}"
        for pid in $FRONTEND_PIDS; do
            echo -e "终止前端进程: $pid"
            kill -15 $pid 2>/dev/null
            sleep 0.5
            kill -9 $pid 2>/dev/null
        done
        echo -e "${GREEN}✓ 所有前端进程已终止${NC}"
    else
        echo -e "${GREEN}✓ 未发现其他前端进程${NC}"
    fi
    
    # 确认端口释放
    if [ "$OS_TYPE" == "Darwin" ]; then
        if lsof -i :5501 | grep -q LISTEN; then
            echo -e "${RED}警告: 端口5501仍被占用${NC}"
        else
            echo -e "${GREEN}✓ 端口5501已释放${NC}"
        fi
    else
        if netstat -tuln 2>/dev/null | grep -q ":5501 "; then
            echo -e "${RED}警告: 端口5501仍被占用${NC}"
        else
            echo -e "${GREEN}✓ 端口5501已释放${NC}"
        fi
    fi
}

# 停止后端服务
stop_backend() {
    echo -e "\n${BLUE}停止后端服务...${NC}"
    
    # 获取后端PID
    local pid_file="$BACKEND_DIR/.backend_pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}发现后端进程(PID: $pid)，正在停止...${NC}"
            kill -15 "$pid" 2>/dev/null
            
            # 等待进程终止
            local count=0
            while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
                sleep 0.5
                count=$((count+1))
            done
            
            # 如果进程仍在运行，强制终止
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}后端进程未响应，强制终止...${NC}"
                kill -9 "$pid" 2>/dev/null
            fi
            
            # 验证进程已终止
            if ! kill -0 "$pid" 2>/dev/null; then
                echo -e "${GREEN}✓ 后端服务已停止${NC}"
                rm -f "$pid_file"
            else
                echo -e "${RED}无法停止后端服务${NC}"
            fi
        else
            echo -e "${YELLOW}找不到运行中的后端进程或PID文件无效${NC}"
        fi
    else
        echo -e "${YELLOW}未找到后端PID文件，尝试通过进程名查找...${NC}"
    fi
    
    # 查找并终止所有相关后端进程
    if [ "$OS_TYPE" == "Darwin" ]; then
        # macOS
        BACKEND_PIDS=$(pgrep -f "python.*app.py" | grep -v $$)
    else
        # Linux
        BACKEND_PIDS=$(pgrep -f "python.*app.py" | grep -v $$)
    fi
    
    if [ -n "$BACKEND_PIDS" ]; then
        echo -e "${YELLOW}发现额外的后端进程，正在终止...${NC}"
        for pid in $BACKEND_PIDS; do
            echo -e "终止后端进程: $pid"
            kill -15 $pid 2>/dev/null
            sleep 0.5
            kill -9 $pid 2>/dev/null
        done
        echo -e "${GREEN}✓ 所有后端进程已终止${NC}"
    else
        echo -e "${GREEN}✓ 未发现其他后端进程${NC}"
    fi
    
    # 确认端口释放
    if [ "$OS_TYPE" == "Darwin" ]; then
        if lsof -i :5502 | grep -q LISTEN; then
            echo -e "${RED}警告: 端口5502仍被占用${NC}"
        else
            echo -e "${GREEN}✓ 端口5502已释放${NC}"
        fi
    else
        if netstat -tuln 2>/dev/null | grep -q ":5502 "; then
            echo -e "${RED}警告: 端口5502仍被占用${NC}"
        else
            echo -e "${GREEN}✓ 端口5502已释放${NC}"
        fi
    fi
}

# 停止MongoDB服务（可选）
stop_mongodb() {
    echo -e "\n${BLUE}是否停止MongoDB服务? (y/n) ${NC}"
    read -r stop_mongo
    
    if [ "$stop_mongo" == "y" ] || [ "$stop_mongo" == "Y" ]; then
        echo -e "${YELLOW}尝试停止MongoDB服务...${NC}"
        
        if [ "$OS_TYPE" == "Darwin" ]; then
            # macOS
            if brew services list | grep mongodb-community | grep -q started; then
                echo -e "${YELLOW}正在停止MongoDB服务...${NC}"
                brew services stop mongodb-community
                if brew services list | grep mongodb-community | grep -q stopped; then
                    echo -e "${GREEN}✓ MongoDB服务已停止${NC}"
                else
                    echo -e "${RED}MongoDB服务停止失败${NC}"
                fi
            else
                echo -e "${YELLOW}未检测到通过Homebrew启动的MongoDB服务${NC}"
                
                # 检查直接启动的MongoDB进程
                MONGO_PIDS=$(pgrep mongod)
                if [ -n "$MONGO_PIDS" ]; then
                    echo -e "${YELLOW}发现MongoDB进程，尝试停止...${NC}"
                    for pid in $MONGO_PIDS; do
                        echo -e "终止MongoDB进程: $pid"
                        kill -15 $pid 2>/dev/null
                        sleep 1
                        kill -9 $pid 2>/dev/null
                    done
                    
                    # 验证进程已终止
                    if pgrep mongod > /dev/null; then
                        echo -e "${RED}MongoDB进程停止失败${NC}"
                    else
                        echo -e "${GREEN}✓ MongoDB进程已停止${NC}"
                    fi
                else
                    echo -e "${GREEN}✓ 未检测到运行中的MongoDB进程${NC}"
                fi
            fi
        else
            # Linux
            if command -v systemctl &> /dev/null; then
                if systemctl is-active --quiet mongod; then
                    echo -e "${YELLOW}正在停止MongoDB系统服务...${NC}"
                    sudo systemctl stop mongod
                    if ! systemctl is-active --quiet mongod; then
                        echo -e "${GREEN}✓ MongoDB系统服务已停止${NC}"
                    else
                        echo -e "${RED}MongoDB系统服务停止失败${NC}"
                    fi
                else
                    echo -e "${YELLOW}MongoDB系统服务未运行${NC}"
                fi
            else
                # 检查直接启动的MongoDB进程
                MONGO_PIDS=$(pgrep mongod)
                if [ -n "$MONGO_PIDS" ]; then
                    echo -e "${YELLOW}发现MongoDB进程，尝试停止...${NC}"
                    for pid in $MONGO_PIDS; do
                        echo -e "终止MongoDB进程: $pid"
                        kill -15 $pid 2>/dev/null
                        sleep 1
                        kill -9 $pid 2>/dev/null
                    done
                    
                    # 验证进程已终止
                    if pgrep mongod > /dev/null; then
                        echo -e "${RED}MongoDB进程停止失败${NC}"
                    else
                        echo -e "${GREEN}✓ MongoDB进程已停止${NC}"
                    fi
                else
                    echo -e "${GREEN}✓ 未检测到运行中的MongoDB进程${NC}"
                fi
            fi
        fi
    else
        echo -e "${YELLOW}已跳过MongoDB服务停止${NC}"
    fi
}

# 清理PID文件
cleanup_pid_files() {
    echo -e "\n${BLUE}清理PID文件...${NC}"
    
    # 删除启动脚本PID文件
    if [ -f "$PROJECT_ROOT/.start_script_pid" ]; then
        rm -f "$PROJECT_ROOT/.start_script_pid"
        echo -e "${GREEN}✓ 已删除启动脚本PID文件${NC}"
    fi
    
    # 删除前端PID文件
    if [ -f "$FRONTEND_DIR/.frontend_pid" ]; then
        rm -f "$FRONTEND_DIR/.frontend_pid"
        echo -e "${GREEN}✓ 已删除前端PID文件${NC}"
    fi
    
    # 删除后端PID文件
    if [ -f "$BACKEND_DIR/.backend_pid" ]; then
        rm -f "$BACKEND_DIR/.backend_pid"
        echo -e "${GREEN}✓ 已删除后端PID文件${NC}"
    fi
    
    # 删除旧的运行进程文件
    if [ -f "$PROJECT_ROOT/.running_pids" ]; then
        rm -f "$PROJECT_ROOT/.running_pids"
        echo -e "${GREEN}✓ 已删除旧的运行进程文件${NC}"
    fi
}

# 主函数
main() {
    # 停止前端服务
    stop_frontend
    
    # 停止后端服务
    stop_backend
    
    # 询问是否停止MongoDB
    stop_mongodb
    
    # 清理PID文件
    cleanup_pid_files
    
    echo -e "\n${GREEN}${BOLD}所有服务已成功停止!${NC}"
    echo -e "${RED}=======================================${NC}"
}

# 执行主函数
main 