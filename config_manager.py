"""
配置管理模块
负责保存和加载用户配置
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from config import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "settings.json"


class ConfigManager:
    """配置管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance
    
    def _init_config(self):
        """初始化配置"""
        self.config = {
            'index_directories': [],
            'excluded_folders': [],
            'max_file_size': 50 * 1024 * 1024,
            'window_width': 1200,
            'window_height': 800,
            'search_history': [],
            'auto_start_monitoring': True,
        }
        self.load()
    
    def load(self):
        """从文件加载配置"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
                print(f"配置已加载：{CONFIG_FILE}")
        except Exception as e:
            print(f"加载配置失败：{e}")
    
    def save(self):
        """保存配置到文件"""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"配置已保存：{CONFIG_FILE}")
        except Exception as e:
            print(f"保存配置失败：{e}")
    
    def get(self, key: str, default=None):
        """获取配置项"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置项"""
        self.config[key] = value
    
    def get_index_directories(self) -> List[str]:
        """获取索引目录列表"""
        return self.config.get('index_directories', [])
    
    def set_index_directories(self, directories: List[str]):
        """设置索引目录列表"""
        self.config['index_directories'] = directories
        self.save()
    
    def add_index_directory(self, directory: str):
        """添加索引目录（规范化路径）"""
        import os
        # 规范化路径（统一为绝对路径，使用系统分隔符）
        normalized_dir = os.path.normpath(os.path.abspath(directory))
        
        if normalized_dir not in self.config['index_directories']:
            self.config['index_directories'].append(normalized_dir)
            self.save()
    
    def remove_index_directory(self, directory: str):
        """移除索引目录"""
        if directory in self.config['index_directories']:
            self.config['index_directories'].remove(directory)
            self.save()
    
    def get_search_history(self) -> List[str]:
        """获取搜索历史"""
        return self.config.get('search_history', [])
    
    def add_search_history(self, query: str, max_history: int = 50):
        """添加搜索历史"""
        history = self.config.get('search_history', [])
        if query in history:
            history.remove(query)
        history.insert(0, query)
        # 限制历史记录数量
        history = history[:max_history]
        self.config['search_history'] = history
        self.save()
    
    def clear_search_history(self):
        """清空搜索历史"""
        self.config['search_history'] = []
        self.save()
    
    def get_search_file_types(self) -> List[str]:
        """获取搜索文件类型"""
        return self.config.get('search_file_types', [])
    
    def set_search_file_types(self, file_types: List[str]):
        """设置搜索文件类型"""
        self.config['search_file_types'] = file_types
        self.save()
    
    def get_search_mode(self) -> str:
        """获取搜索模式"""
        return self.config.get('search_mode', '精准搜索')
    
    def set_search_mode(self, mode: str):
        """设置搜索模式"""
        self.config['search_mode'] = mode
        self.save()
    
    def get_search_directory(self):
        """获取搜索目录选择"""
        return self.config.get('search_directory', None)
    
    def set_search_directory(self, directory):
        """设置搜索目录（支持单个目录或目录列表）"""
        self.config['search_directory'] = directory
        self.save()
    
    def clear_search_directory(self):
        """清空搜索目录选择（恢复为全选）"""
        if 'search_directory' in self.config:
            del self.config['search_directory']
            self.save()


# 全局配置实例
config = ConfigManager()
