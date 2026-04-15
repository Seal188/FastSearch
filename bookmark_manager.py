"""
书签管理模块
"""
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from config import CONFIG_DIR
from config_manager import config

BOOKMARKS_FILE = CONFIG_DIR / "bookmarks.json"


class Bookmark:
    """书签类"""
    
    def __init__(self, name: str, path: str, group: str = "默认分组", created_at: str = None):
        self.name = name
        self.path = path
        self.group = group
        self.created_at = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'path': self.path,
            'group': self.group,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Bookmark':
        return cls(
            name=data.get('name', ''),
            path=data.get('path', ''),
            group=data.get('group', '默认分组'),
            created_at=data.get('created_at')
        )


class BookmarkManager:
    """书签管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_bookmarks()
        return cls._instance
    
    def _init_bookmarks(self):
        """初始化书签"""
        self.bookmarks: List[Bookmark] = []
        self.groups: List[str] = ["默认分组"]
        self.load()
    
    def load(self):
        """从文件加载书签"""
        try:
            if BOOKMARKS_FILE.exists():
                with open(BOOKMARKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.bookmarks = [Bookmark.from_dict(b) for b in data.get('bookmarks', [])]
                    self.groups = data.get('groups', ["默认分组"])
                print(f"已加载 {len(self.bookmarks)} 个书签")
        except Exception as e:
            print(f"加载书签失败：{e}")
    
    def save(self):
        """保存书签到文件"""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'bookmarks': [b.to_dict() for b in self.bookmarks],
                    'groups': self.groups
                }, f, ensure_ascii=False, indent=2)
            print(f"已保存 {len(self.bookmarks)} 个书签")
        except Exception as e:
            print(f"保存书签失败：{e}")
    
    def add_bookmark(self, name: str, path: str, group: str = "默认分组"):
        """添加书签"""
        # 检查是否已存在
        for bookmark in self.bookmarks:
            if bookmark.path == path:
                print(f"书签已存在：{path}")
                return False
        
        bookmark = Bookmark(name, path, group)
        self.bookmarks.append(bookmark)
        
        # 如果分组不存在，自动添加
        if group not in self.groups:
            self.groups.append(group)
        
        self.save()
        return True
    
    def remove_bookmark(self, path: str):
        """移除书签"""
        for i, bookmark in enumerate(self.bookmarks):
            if bookmark.path == path:
                self.bookmarks.pop(i)
                self.save()
                return True
        return False
    
    def get_bookmarks(self, group: str = None) -> List[Bookmark]:
        """获取书签列表"""
        if group:
            return [b for b in self.bookmarks if b.group == group]
        return self.bookmarks
    
    def get_all_groups(self) -> List[str]:
        """获取所有分组"""
        return self.groups
    
    def add_group(self, group_name: str):
        """添加分组"""
        if group_name not in self.groups:
            self.groups.append(group_name)
            self.save()
            return True
        return False
    
    def remove_group(self, group_name: str):
        """移除分组"""
        if group_name in self.groups and group_name != "默认分组":
            # 将该分组的书签移到默认分组
            for bookmark in self.bookmarks:
                if bookmark.group == group_name:
                    bookmark.group = "默认分组"
            
            self.groups.remove(group_name)
            self.save()
            return True
        return False
    
    def rename_group(self, old_name: str, new_name: str):
        """重命名分组"""
        if old_name in self.groups and old_name != "默认分组":
            # 更新分组名称
            for i, group in enumerate(self.groups):
                if group == old_name:
                    self.groups[i] = new_name
                    break
            
            # 更新该分组下所有书签的分组
            for bookmark in self.bookmarks:
                if bookmark.group == old_name:
                    bookmark.group = new_name
            
            self.save()
            return True
        return False


# 全局书签实例
bookmark_manager = BookmarkManager()
