"""
日志模块
提供统一的日志配置和使用接口
"""
import logging
import sys
from typing import List, Dict, Any
from loguru import logger
import json
import os
from app.core.config import settings

# 日志级别映射
LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

# 获取配置的日志级别
LOG_LEVEL = LEVEL_MAP.get(settings.LOG_LEVEL, logging.INFO)

# 格式化配置
FORMAT_CONSOLE = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
FORMAT_FILE = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"

# JSON格式化配置
class JsonSink:
    """JSON格式日志写入接口"""
    def __init__(self, file_path):
        self.file_path = file_path
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
    def write(self, message):
        """写入日志"""
        record = message.record
        data = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "level": record["level"].name,
            "message": record["message"],
            "name": record["name"],
            "line": record["line"]
        }
        
        # 附加额外字段
        if "extra" in record and record["extra"]:
            for key, value in record["extra"].items():
                data[key] = value
                
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


class InterceptHandler(logging.Handler):
    """拦截标准库日志并转为loguru格式"""
    
    def emit(self, record):
        """转换并发送日志"""
        # 获取对应的loguru级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
            
        # 查找调用者
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
            
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_path: str = "logs"):
    """配置日志系统"""
    # 确保日志目录存在
    os.makedirs(log_path, exist_ok=True)
    
    # 获取根日志记录器
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(LOG_LEVEL)
    
    # 移除现有的loguru处理器
    logger.remove()
    
    # 添加控制台处理器
    logger.add(
        sys.stderr, 
        format=FORMAT_CONSOLE, 
        level=LOG_LEVEL,
        colorize=True
    )
    
    # 添加常规文件处理器(按天分割日志)
    logger.add(
        f"{log_path}/app_{{time:YYYY-MM-DD}}.log",
        rotation="00:00",  # 每天午夜轮换
        format=FORMAT_FILE,
        level=LOG_LEVEL,
        retention="30 days",  # 保留30天
        compression="zip"  # 压缩旧文件
    )
    
    # 错误日志单独记录
    logger.add(
        f"{log_path}/error_{{time:YYYY-MM-DD}}.log",
        rotation="00:00", 
        format=FORMAT_FILE,
        level="ERROR",
        retention="60 days",  # 错误日志保留更长时间
        compression="zip"
    )
    
    # 添加JSON格式日志
    json_sink = JsonSink(f"{log_path}/app.json")
    logger.add(
        json_sink.write,
        level=LOG_LEVEL
    )
    
    # 配置第三方库的日志
    for _log in ["uvicorn", "uvicorn.error", "fastapi"]:
        _logger = logging.getLogger(_log)
        _logger.handlers = [InterceptHandler()]
        _logger.propagate = False
        
    # 返回配置好的logger
    return logger


# 导出配置好的logger
app_logger = setup_logging() 