"""
全局配置文件
"""
import os
import sys
from pathlib import Path

# 应用信息
APP_NAME = "FastSearch"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Your Name"

# 获取程序运行目录（支持 EXE 和源码两种模式）
if getattr(sys, 'frozen', False):
    # 如果是打包后的 EXE
    BASE_DIR = Path(sys.executable).parent
else:
    # 如果是源码运行
    BASE_DIR = Path(__file__).parent

# 目录配置
DATA_DIR = BASE_DIR / "data"
INDEX_DIR = DATA_DIR / "index"
LOG_DIR = DATA_DIR / "logs"
CONFIG_DIR = DATA_DIR / "config"

# 确保目录存在
for dir_path in [DATA_DIR, INDEX_DIR, LOG_DIR, CONFIG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 索引配置
INDEX_PATH = INDEX_DIR / "fulltext_index"
DB_PATH = DATA_DIR / "metadata.db"

# 性能配置
MAX_FILE_SIZE = 50 * 1024 * 1024  # 最大文件 50MB
BATCH_SIZE = 100  # 批量索引文件数
MEMORY_LIMIT = 512 * 1024 * 1024  # 内存限制 512MB
SHARD_SIZE = 10000  # 每个索引分片的最大文件数

# 支持的文件格式
SUPPORTED_EXTENSIONS = {
    # 文本文件
    '.txt', '.md', '.rst', '.html', '.htm', '.xml', '.json', '.yaml', '.yml',
    '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.cs', '.php', '.rb', '.go',
    '.log', '.ini', '.cfg', '.conf',
    
    # Office 文档
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    
    # PDF
    '.pdf',
    
    # 电子书
    '.epub', '.mobi', '.chm',
    
    # 压缩文件
    '.zip', '.rar', '.7z',
    
    # 其他
    '.rtf', '.odt', '.ods', '.odp',
}

# 默认排除的目录
EXCLUDED_DIRS = {
    '$Recycle.Bin',
    'System Volume Information',
    'Windows',
    'Program Files',
    'Program Files (x86)',
    'node_modules',
    '.git',
    '__pycache__',
    'venv',
    '.venv',
    'env',
    '.env',
}

# 日志配置
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# UI 配置
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 800
SEARCH_HISTORY_MAX = 50
