"""
文件浏览历史记录模块
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from config import CONFIG_DIR

HISTORY_FILE = CONFIG_DIR / "history.json"


class HistoryEntry:
    """历史记录条目"""
    
    def __init__(self, file_path: str, filename: str, viewed_at: str = None):
        self.file_path = file_path
        self.filename = filename
        self.viewed_at = viewed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'file_path': str(self.file_path),
            'filename': self.filename,
            'viewed_at': self.viewed_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistoryEntry':
        return cls(
            file_path=data.get('file_path', ''),
            filename=data.get('filename', ''),
            viewed_at=data.get('viewed_at')
        )


class HistoryManager:
    """历史记录管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_history()
        return cls._instance
    
    def _init_history(self):
        """初始化历史记录"""
        self.entries: List[HistoryEntry] = []
        self.max_entries = 100  # 最多保留 100 条记录
        self.load()
    
    def load(self):
        """从文件加载历史记录"""
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entries = [HistoryEntry.from_dict(e) for e in data.get('entries', [])]
                print(f"已加载 {len(self.entries)} 条历史记录")
        except Exception as e:
            print(f"加载历史记录失败：{e}")
    
    def save(self):
        """保存历史记录到文件"""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'entries': [e.to_dict() for e in self.entries]
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败：{e}")
    
    def add_entry(self, file_path: str, filename: str):
        """添加历史记录"""
        # 检查是否已存在，如果存在则移到最前面
        for i, entry in enumerate(self.entries):
            if entry.file_path == file_path:
                self.entries.pop(i)
                break
        
        # 添加到最前面
        entry = HistoryEntry(file_path, filename)
        self.entries.insert(0, entry)
        
        # 限制记录数量
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[:self.max_entries]
        
        self.save()
    
    def get_entries(self, limit: int = 50) -> List[HistoryEntry]:
        """获取历史记录"""
        return self.entries[:limit]
    
    def clear(self):
        """清空历史记录"""
        self.entries = []
        self.save()
    
    def remove_entry(self, file_path: str):
        """移除单条记录"""
        for i, entry in enumerate(self.entries):
            if entry.file_path == file_path:
                self.entries.pop(i)
                self.save()
                return True
        return False


# 全局历史记录实例
history_manager = HistoryManager()
