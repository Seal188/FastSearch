"""
文件监控模块
使用 watchdog 监控文件系统变化，实现增量索引
"""
import logging
import time
from pathlib import Path
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, DirDeletedEvent
from threading import Lock
import queue

from config import EXCLUDED_DIRS, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


class FileChangeHandler(FileSystemEventHandler):
    """文件变化事件处理器"""
    
    def __init__(self, callback: Callable[[Path, str], None]):
        super().__init__()
        self.callback = callback
        self._lock = Lock()
        self._pending_files: Set[Path] = set()
        self._debounce_seconds = 2.0
    
    @staticmethod
    def _should_index(file_path: Path) -> bool:
        """检查文件是否应该被索引"""
        if file_path.is_dir():
            return False
        
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        
        for part in file_path.parts:
            if part in EXCLUDED_DIRS:
                return False
        
        if part.startswith('.'):
            return False
        
        return True
    
    def _schedule_index(self, file_path: Path, event_type: str):
        """延迟索引，避免文件还在写入时读取"""
        with self._lock:
            if file_path in self._pending_files:
                return
            
            self._pending_files.add(file_path)
        
        def delayed_index():
            time.sleep(self._debounce_seconds)
            with self._lock:
                self._pending_files.discard(file_path)
            
            if file_path.exists() and file_path.is_file():
                try:
                    self.callback(file_path, event_type)
                except Exception as e:
                    logger.error(f"处理文件变化失败 {file_path}: {e}")
        
        import threading
        thread = threading.Thread(target=delayed_index, daemon=True)
        thread.start()
    
    def on_created(self, event):
        """文件创建事件"""
        if isinstance(event, FileCreatedEvent) and not event.is_directory:
            file_path = Path(event.src_path)
            if FileChangeHandler._should_index(file_path):
                logger.debug(f"文件创建：{file_path}")
                self._schedule_index(file_path, 'create')
    
    def on_modified(self, event):
        """文件修改事件"""
        if isinstance(event, FileModifiedEvent) and not event.is_directory:
            file_path = Path(event.src_path)
            if FileChangeHandler._should_index(file_path):
                logger.debug(f"文件修改：{file_path}")
                self._schedule_index(file_path, 'modify')
    
    def on_deleted(self, event):
        """文件删除事件"""
        if isinstance(event, (FileDeletedEvent, DirDeletedEvent)):
            file_path = Path(event.src_path)
            logger.debug(f"文件删除：{file_path}")
            # 延迟处理删除事件，确保文件已经不存在
            def delayed_delete():
                time.sleep(0.5)  # 短暂延迟，确保文件系统已更新
                if not file_path.exists():
                    try:
                        self.callback(file_path, 'delete')
                    except Exception as e:
                        logger.error(f"处理文件删除失败 {file_path}: {e}")
                else:
                    logger.debug(f"文件删除事件但文件仍存在：{file_path}")
            import threading
            thread = threading.Thread(target=delayed_delete, daemon=True)
            thread.start()


class FileMonitor:
    """文件监控器"""
    
    def __init__(self):
        self.observer = None
        self.watch_paths: Set[Path] = set()
        self.handler = None
        self._running = False
    
    def start(self, watch_paths: Set[Path], callback: Callable[[Path, str], None]):
        """启动监控"""
        if self._running:
            logger.warning("监控器已在运行中")
            return
        
        self.watch_paths = watch_paths
        self.handler = FileChangeHandler(callback)
        self.observer = Observer()
        
        for path in watch_paths:
            if path.exists() and path.is_dir():
                self.observer.schedule(self.handler, str(path), recursive=True)
                logger.info(f"开始监控目录：{path}")
        
        self.observer.start()
        self._running = True
        logger.info("文件监控器已启动")
    
    def stop(self):
        """停止监控"""
        try:
            if self.observer and self._running:
                logger.info("正在停止文件监控器...")
                self.observer.stop()
                self.observer.join(timeout=5)  # 添加超时，避免无限等待
                self._running = False
                logger.info("文件监控器已停止")
            else:
                logger.debug("监控器未运行，无需停止")
        except Exception as e:
            logger.error(f"停止监控器失败：{e}")
            self._running = False  # 确保状态更新
    
    def add_watch_path(self, path: Path):
        """添加监控路径"""
        if path.exists() and path.is_dir() and path not in self.watch_paths:
            self.watch_paths.add(path)
            if self._running and self.observer:
                self.observer.schedule(self.handler, str(path), recursive=True)
                logger.info(f"添加监控目录：{path}")
    
    def remove_watch_path(self, path: Path):
        """移除监控路径"""
        if path in self.watch_paths:
            self.watch_paths.remove(path)
            if self._running and self.observer:
                self.observer.unschedule_all(self.handler)
                for p in self.watch_paths:
                    self.observer.schedule(self.handler, str(p), recursive=True)
                logger.info(f"移除监控目录：{path}")
    
    def is_running(self):
        """检查监控器是否运行"""
        return self._running


class IndexingScheduler:
    """索引调度器"""
    
    def __init__(self, monitor: FileMonitor, index_callback: Callable[[Path], None]):
        self.monitor = monitor
        self.index_callback = index_callback
        self._queue = queue.Queue()
        self._running = False
    
    def start(self):
        """启动调度器"""
        def worker():
            while self._running:
                try:
                    file_path, event_type = self._queue.get(timeout=1)
                    if event_type == 'delete':
                        self.index_callback(file_path)
                    elif event_type in ['create', 'modify']:
                        self.index_callback(file_path)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"索引调度失败：{e}")
        
        import threading
        self._running = True
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        logger.info("索引调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self._running = False
        logger.info("索引调度器已停止")
    
    def on_file_change(self, file_path: Path, event_type: str):
        """处理文件变化事件"""
        self._queue.put((file_path, event_type))
        logger.debug(f"文件变化事件加入队列：{file_path} - {event_type}")
