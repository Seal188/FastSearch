"""
全文索引引擎 V2
极简同步模式，追求稳定性而非速度
"""
import os
import hashlib
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID
from whoosh.qparser import MultifieldParser
from whoosh.analysis import Analyzer, Token
import logging

from config import INDEX_PATH, DB_PATH, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

# 预加载 jieba 分词器（避免每次搜索时重新加载）
try:
    import jieba
    logger.debug("jieba 分词器已预加载")
except ImportError:
    logger.warning("jieba 分词器未安装，中文搜索可能不可用")
    jieba = None


class ChineseAnalyzer(Analyzer):
    """
    基于 jieba 的中文分词器（简化版）
    支持中文和英文混合文本的分词
    """
    def __call__(self, value, **kwargs):
        """
        分词方法
        
        Args:
            value: 要分词的文本
            **kwargs: WHOOSH 传递的其他参数
        """
        try:
            # jieba 已经预加载，直接使用
            if jieba is None:
                # 如果没有安装 jieba，返回原始文本
                t = Token()
                t.text = value
                t.pos = 0
                yield t
                return
            
            # 使用 jieba 分词
            tokens = jieba.lcut(value)
            
            # 过滤空白和标点符号
            tokens = [t for t in tokens if t and not t.isspace() 
                     and not all(c in '，。！？；：""''、？！' for c in t)]
            
            # 计算位置并生成 Token
            # 注意：WHOOSH 的 Token.pos 属性指的是 position（整数），不是 part of speech（词性）
            pos = 0
            for token_text in tokens:
                t = Token()
                t.text = token_text
                t.pos = pos  # 位置（整数），不是词性标注！
                yield t
                pos += 1  # 每个词的位置递增
                
        except Exception as e:
            logger.error(f"中文分词失败：{e}")
            # 返回原始文本作为后备
            t = Token()
            t.text = value
            t.pos = 0
            yield t


class IndexEngine:
    """
    全文索引引擎（极简同步模式）
    
    设计原则：
    1. 单线程同步操作 - 所有操作在主线程中顺序执行
    2. 立即提交 - 每个文件索引后立即 commit
    3. 零缓冲零队列 - 不使用任何缓冲机制
    4. 简单可预测 - 代码逻辑清晰，易于调试
    """
    
    def __init__(self):
        """初始化索引引擎"""
        self.index = None
        self.schema = None
        self.db_conn = None
        # 添加互斥锁，确保线程安全
        self._write_lock = threading.Lock()
        self._init_schema()
    
    def _init_schema(self):
        """初始化索引模式"""
        # 使用自定义的中文分词器
        analyzer = ChineseAnalyzer()
        logger.info("使用中文分词器（基于 jieba）")
        
        self.schema = Schema(
            path=ID(stored=True, unique=True),
            filename=TEXT(stored=True, analyzer=analyzer),
            content=TEXT(stored=True, analyzer=analyzer),
        )
    
    def create_index(self, force: bool = False):
        """创建或打开索引"""
        index_path = Path(INDEX_PATH)
        
        # 确保索引目录存在
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 如果强制重建，先删除旧索引
        if force and index_path.exists():
            import shutil
            try:
                shutil.rmtree(index_path)
                logger.info(f"已删除旧索引：{index_path}")
            except Exception as e:
                logger.error(f"删除旧索引失败：{e}")
        
        # 创建或打开索引
        try:
            if not exists_in(index_path):
                # 创建新索引
                index_path.mkdir(parents=True, exist_ok=True)
                self.index = create_in(index_path, self.schema)
                logger.info(f"创建新索引：{index_path}")
            else:
                # 打开现有索引
                self.index = open_dir(index_path)
                logger.info(f"打开现有索引：{index_path}")
        except Exception as e:
            # 如果打开索引失败，尝试重建
            logger.error(f"打开索引失败：{e}，尝试重建索引")
            try:
                if index_path.exists():
                    import shutil
                    shutil.rmtree(index_path)
                index_path.mkdir(parents=True, exist_ok=True)
                self.index = create_in(index_path, self.schema)
                logger.info(f"重建新索引：{index_path}")
            except Exception as e2:
                logger.error(f"重建索引失败：{e2}")
                raise
        
        # 初始化数据库
        self._init_database()
    
    def rebuild_index(self):
        """
        完全重建索引
        删除所有旧索引并重新创建
        """
        index_path = Path(INDEX_PATH)
        
        logger.info("开始重建索引...")
        
        # 删除旧索引
        if index_path.exists():
            import shutil
            try:
                shutil.rmtree(index_path)
                logger.info(f"已删除旧索引：{index_path}")
            except Exception as e:
                logger.error(f"删除旧索引失败：{e}")
                return False
        
        # 删除元数据库
        db_path = Path(DB_PATH)
        if db_path.exists():
            try:
                db_path.unlink()
                logger.info(f"已删除元数据库：{db_path}")
            except Exception as e:
                logger.error(f"删除元数据库失败：{e}")
        
        # 重新创建索引
        try:
            index_path.mkdir(parents=True, exist_ok=True)
            self.index = create_in(index_path, self.schema)
            logger.info(f"创建新索引：{index_path}")
            
            # 重新初始化数据库
            self._init_database()
            
            logger.info("索引重建完成")
            return True
        except Exception as e:
            logger.error(f"重建索引失败：{e}")
            return False
    
    def _init_database(self):
        """初始化 SQLite 元数据库"""
        self.db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        cursor = self.db_conn.cursor()
        
        # 创建元数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_metadata (
                path TEXT PRIMARY KEY,
                size INTEGER,
                modified REAL,
                hash TEXT,
                status TEXT,
                indexed_at TIMESTAMP
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON file_metadata(status)')
        self.db_conn.commit()
        logger.info("元数据库初始化完成")
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """计算文件 MD5 哈希"""
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"计算哈希失败 {file_path}: {e}")
            return ""
    
    def needs_reindex(self, file_path: Path) -> bool:
        """检查文件是否需要重新索引"""
        cursor = self.db_conn.cursor()
        cursor.execute(
            "SELECT hash, modified FROM file_metadata WHERE path=?",
            (str(file_path),)
        )
        row = cursor.fetchone()
        
        if not row:
            # 数据库中没有记录，需要索引
            return True
        
        old_hash, old_modified = row
        
        try:
            stat = file_path.stat()
            current_modified = stat.st_mtime
            current_hash = self.calculate_file_hash(file_path)
            
            # 文件内容或修改时间变化，需要重新索引
            if current_hash != old_hash:
                return True
            
            if abs(current_modified - old_modified) > 1.0:
                return True
            
            return False
        except Exception as e:
            logger.error(f"检查文件状态失败 {file_path}: {e}")
            return True
    
    def add_document(self, file_path: Path, content: str) -> bool:
        """
        添加文档到索引（同步直接写入）
        
        Args:
            file_path: 文件路径
            content: 文件内容
        
        Returns:
            bool: 是否成功
        """
        import os
        # 规范化路径（统一为绝对路径，使用系统分隔符）
        normalized_path = os.path.normpath(os.path.abspath(str(file_path)))
        
        with self._write_lock:
            try:
                # 写入索引（使用上下文管理器）
                with self.index.writer() as writer:
                    writer.add_document(
                        path=normalized_path,  # 使用规范化路径
                        content=content,
                        filename=file_path.name,
                    )
                
                # 更新数据库
                cursor = self.db_conn.cursor()
                stat = file_path.stat()
                file_hash = self.calculate_file_hash(file_path)
                
                cursor.execute('''
                    INSERT OR REPLACE INTO file_metadata 
                    (path, size, modified, hash, status, indexed_at)
                    VALUES (?, ?, ?, ?, 'indexed', datetime('now'))
                ''', (
                    normalized_path,  # 使用规范化路径
                    stat.st_size,
                    stat.st_mtime,
                    file_hash,
                ))
                self.db_conn.commit()
                
                logger.debug(f"索引成功：{file_path}")
                return True
                
            except Exception as e:
                import traceback
                logger.error(f"添加文档失败 {file_path}: {e}")
                logger.error(f"详细错误：{traceback.format_exc()}")
                
                # 标记为失败
                try:
                    cursor = self.db_conn.cursor()
                    stat = file_path.stat()
                    cursor.execute('''
                        INSERT OR REPLACE INTO file_metadata 
                        (path, size, modified, hash, status, indexed_at)
                        VALUES (?, ?, ?, ?, 'failed', datetime('now'))
                    ''', (
                        normalized_path,  # 使用规范化路径
                        stat.st_size,
                        stat.st_mtime,
                        self.calculate_file_hash(file_path),
                    ))
                    self.db_conn.commit()
                except:
                    pass
                
                return False
    
    def remove_document(self, file_path: Path) -> bool:
        """从索引中移除文档"""
        import os
        # 规范化路径
        normalized_path = os.path.normpath(os.path.abspath(str(file_path)))
        
        with self._write_lock:
            try:
                # 使用上下文管理器删除文档
                with self.index.writer() as writer:
                    writer.delete_by_term('path', normalized_path)
                
                cursor = self.db_conn.cursor()
                cursor.execute(
                    "DELETE FROM file_metadata WHERE path=?",
                    (normalized_path,)
                )
                self.db_conn.commit()
                return True
            except Exception as e:
                logger.error(f"移除文档失败 {file_path}: {e}")
                return False
    
    def search(self, query_text: str, limit: int = 100, search_mode: str = 'fuzzy') -> List[Dict[str, Any]]:
        """
        搜索文档
        
        Args:
            query_text: 搜索关键词
            limit: 结果数量限制
            search_mode: 搜索模式 ('fuzzy', 'exact', 'regex')
        
        Returns:
            搜索结果列表
        """
        if not self.index:
            return []
        
        try:
            with self.index.searcher() as searcher:
                # 根据不同模式解析查询
                if search_mode == 'exact':
                    # 精准搜索：使用 Term 查询实现精确匹配
                    # 在 content 和 filename 两个字段中搜索
                    from whoosh.query import Or, Term
                    
                    # 创建两个 Term 查询（content 和 filename）
                    content_query = Term("content", query_text)
                    filename_query = Term("filename", query_text)
                    
                    # 使用 Or 连接（匹配任意一个字段）
                    query = Or([content_query, filename_query])
                    
                elif search_mode == 'regex':
                    # 正则搜索：在 content 和 filename 两个字段中搜索
                    from whoosh.query import Regex, Or
                    
                    # 创建两个正则查询（content 和 filename）
                    content_regex = Regex("content", query_text)
                    filename_regex = Regex("filename", query_text)
                    
                    # 使用 Or 连接（匹配任意一个字段）
                    query = Or([content_regex, filename_regex])
                else:
                    # 模糊搜索：默认模式（分词匹配）
                    # 使用 MultifieldParser 进行分词
                    parser = MultifieldParser(
                        ["content", "filename"], 
                        schema=self.schema
                    )
                    query = parser.parse(query_text)
                
                results = searcher.search(query, limit=limit)
                
                # 去重：使用字典按路径去重，保留最高分的结果
                seen_paths = {}
                for hit in results:
                    path = hit['path']
                    if path not in seen_paths or hit.score > seen_paths[path]['score']:
                        seen_paths[path] = {
                            'path': hit['path'],
                            'filename': hit['filename'],
                            'score': hit.score
                        }
                
                # 按分数排序
                unique_results = sorted(
                    seen_paths.values(),
                    key=lambda x: x['score'],
                    reverse=True
                )
                
                return unique_results
        except Exception as e:
            logger.error(f"搜索失败：{e}")
            return []
    
    def search_with_query(self, query_obj, limit: int = 100) -> List[Dict[str, Any]]:
        """
        使用自定义查询对象搜索
        
        Args:
            query_obj: WHOOSH 查询对象
            limit: 结果数量限制
        
        Returns:
            搜索结果列表
        """
        if not self.index:
            return []
        
        try:
            with self.index.searcher() as searcher:
                results = searcher.search(query_obj, limit=limit)
                
                # 去重：使用字典按路径去重，保留最高分的结果
                seen_paths = {}
                for hit in results:
                    path = hit['path']
                    if path not in seen_paths or hit.score > seen_paths[path]['score']:
                        seen_paths[path] = {
                            'path': hit['path'],
                            'filename': hit['filename'],
                            'score': hit.score
                        }
                
                # 按分数排序
                unique_results = sorted(
                    seen_paths.values(),
                    key=lambda x: x['score'],
                    reverse=True
                )
                
                return unique_results
        except Exception as e:
            logger.error(f"搜索失败：{e}")
            return []
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        cursor = self.db_conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM file_metadata WHERE status='indexed'")
        indexed_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM file_metadata WHERE status='failed'")
        failed_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(size) FROM file_metadata WHERE status='indexed'")
        total_size = cursor.fetchone()[0] or 0
        
        try:
            with self.index.searcher() as searcher:
                doc_count = searcher.doc_count_all()
        except Exception:
            doc_count = 0
        
        return {
            'indexed_files': indexed_count,
            'failed_files': failed_count,
            'total_size': total_size,
            'doc_count': doc_count,
        }
    
    def clear_index_for_directory(self, dir_path: str) -> bool:
        """清除指定目录的所有索引数据"""
        with self._write_lock:
            try:
                # 规范化路径，确保正确匹配
                from pathlib import Path
                dir_path_normalized = str(Path(dir_path))
                
                # 确保路径以分隔符结尾，避免误匹配
                # 例如：E:\test 不会匹配到 E:\test2
                if not dir_path_normalized.endswith('\\') and not dir_path_normalized.endswith('/'):
                    dir_path_normalized = dir_path_normalized + os.sep
                
                cursor = self.db_conn.cursor()
                
                # 查询该目录下的所有文件（精确匹配）
                cursor.execute(
                    "SELECT path FROM file_metadata WHERE path LIKE ?",
                    (dir_path_normalized + '%',)
                )
                files = cursor.fetchall()
                
                if not files:
                    logger.info(f"目录 {dir_path} 下没有找到索引数据")
                    return True
                
                # 从索引中删除（使用上下文管理器）
                with self.index.writer() as writer:
                    for (file_path,) in files:
                        writer.delete_by_term('path', file_path)
                
                # 从数据库删除
                cursor.execute(
                    "DELETE FROM file_metadata WHERE path LIKE ?",
                    (dir_path_normalized + '%',)
                )
                self.db_conn.commit()
                
                logger.info(f"已清除目录 {dir_path} 的索引，共 {len(files)} 个文件")
                return True
            except Exception as e:
                logger.error(f"清除目录索引失败 {dir_path}: {e}")
                return False
    
    def close(self):
        """关闭索引和数据库连接"""
        if self.index:
            try:
                self.index.close()
            except Exception as e:
                logger.error(f"关闭索引失败：{e}")
        
        if self.db_conn:
            self.db_conn.close()
        
        logger.info("索引引擎已关闭")
