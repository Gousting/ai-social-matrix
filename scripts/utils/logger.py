"""
日志工具模块
提供统一的日志记录功能，同时输出到控制台和文件
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from .config_loader import config


def setup_logger(name: str = "ai_matrix") -> logging.Logger:
    """
    设置并返回日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加handler
    if logger.handlers:
        return logger

    log_cfg = config.logging_config
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("log_file", "./logs/ai_matrix.log")
    max_bytes = log_cfg.get("max_bytes", 10485760)
    backup_count = log_cfg.get("backup_count", 5)

    logger.setLevel(level)

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件输出（轮转）
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# 全局默认日志记录器
logger = setup_logger()


if __name__ == "__main__":
    logger.debug("这是一条DEBUG日志")
    logger.info("这是一条INFO日志")
    logger.warning("这是一条WARNING日志")
    logger.error("这是一条ERROR日志")
    print("日志测试完成，请查看 logs/ai_matrix.log")
