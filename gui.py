"""
GUI 主界面模块
使用 PyQt5 实现简洁界面
"""
import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTextEdit, QLabel, QStatusBar, QMenuBar, QMenu, QAction,
    QFileDialog, QMessageBox, QProgressBar, QToolBar, QFrame,
    QComboBox, QCheckBox, QDialog, QDialogButtonBox,
    QGroupBox, QSystemTrayIcon, QMenu as QContextMenu, QSpinBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QInputDialog, QScrollArea, QAbstractItemView, QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QDesktopServices, QColor

from config import (
    DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT,
    SUPPORTED_EXTENSIONS, EXCLUDED_DIRS
)
from config_manager import config
from bookmark_manager import bookmark_manager
from history_manager import history_manager
from enhanced_preview import EnhancedPreviewPanel
from indexer import IndexEngine
from parser import extract_text
from monitor import FileMonitor, IndexingScheduler

import logging
import shutil
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SearchResultsPager:
    """搜索结果分页器"""
    def __init__(self, results: list, page_size: int = 100):
        self.results = results
        self.page_size = page_size
        self.current_page = 0
    
    def get_page(self, page_num: int) -> list:
        """获取指定页的结果"""
        start = page_num * self.page_size
        end = start + self.page_size
        return self.results[start:end]
    
    def total_pages(self) -> int:
        """总页数"""
        if not self.results:
            return 0
        return (len(self.results) + self.page_size - 1) // self.page_size
    
    def has_next(self) -> bool:
        """是否有下一页"""
        return self.current_page < self.total_pages() - 1
    
    def has_previous(self) -> bool:
        """是否有上一页"""
        return self.current_page > 0
    
    def next_page(self) -> int:
        """下一页"""
        if self.has_next():
            self.current_page += 1
        return self.current_page
    
    def previous_page(self) -> int:
        """上一页"""
        if self.has_previous():
            self.current_page -= 1
        return self.current_page


class SearchWorker(QThread):
    """搜索工作线程"""
    results_ready = pyqtSignal(list)
    
    # 类级别的搜索缓存（所有实例共享）
    _search_cache = {}
    _cache_ttl = 300  # 5 分钟有效期
    _max_cache_size = 100  # 最多缓存 100 个查询
    
    def __init__(self, index_engine: IndexEngine, query: str, search_mode: str = "精准搜索", limit: int = 100):
        super().__init__()
        self.index_engine = index_engine
        self.query = query
        self.search_mode = search_mode
        self.limit = limit
        self._stop_flag = False
    
    @classmethod
    def _get_cached_results(cls, query: str, search_mode: str):
        """获取缓存的搜索结果"""
        import time
        key = f"{query}:{search_mode}"
        if key in cls._search_cache:
            timestamp, results = cls._search_cache[key]
            if time.time() - timestamp < cls._cache_ttl:
                logger.debug(f"缓存命中：{query} ({search_mode})")
                return results
            else:
                # 清理过期缓存
                del cls._search_cache[key]
        return None
    
    @classmethod
    def _cache_results(cls, query: str, search_mode: str, results: list):
        """缓存搜索结果"""
        import time
        key = f"{query}:{search_mode}"
        cls._search_cache[key] = (time.time(), results)
        
        # 清理旧缓存（如果超出大小限制）
        cls._cleanup_cache()
        
        logger.debug(f"缓存结果：{query} ({search_mode}) - {len(results)} 个结果")
    
    @classmethod
    def _cleanup_cache(cls):
        """清理过期缓存和超出大小限制的缓存"""
        import time
        now = time.time()
        
        # 清理过期缓存
        expired = [
            k for k, (t, _) in cls._search_cache.items()
            if now - t > cls._cache_ttl
        ]
        for key in expired:
            del cls._search_cache[key]
        
        # 如果缓存超出大小限制，删除最旧的
        if len(cls._search_cache) > cls._max_cache_size:
            # 按时间排序，删除最旧的
            sorted_items = sorted(
                cls._search_cache.items(),
                key=lambda x: x[1][0]  # 按时间戳排序
            )
            # 只删除超出限制的部分，而不是 20%
            to_delete = len(sorted_items) - cls._max_cache_size
            for key, _ in sorted_items[:to_delete]:
                del cls._search_cache[key]
        
        logger.debug(f"缓存清理完成：剩余 {len(cls._search_cache)} 个缓存")
    
    @classmethod
    def clear_cache(cls):
        """清空缓存"""
        cls._search_cache.clear()
        logger.info("搜索缓存已清空")
    
    def run(self):
        try:
            # 先尝试从缓存获取
            cached_results = self._get_cached_results(self.query, self.search_mode)
            if cached_results is not None:
                # 使用缓存结果
                if not self._stop_flag:
                    self.results_ready.emit(cached_results)
                return
            
            # 缓存未命中，执行搜索
            results = self._perform_search()
            
            # 缓存结果（如果有结果）
            if results and not self._stop_flag:
                self._cache_results(self.query, self.search_mode, results)
                self.results_ready.emit(results)
        except Exception as e:
            logger.error(f"搜索线程出错：{e}", exc_info=True)
            # 发送空结果表示出错
            if not self._stop_flag:
                self.results_ready.emit([])
    
    def _perform_search(self):
        """执行搜索"""
        if self.search_mode == "精准搜索":
            # 精准搜索：使用引号包裹实现完全匹配
            return self.index_engine.search(self.query, self.limit, search_mode='exact')
        elif self.search_mode == "正则搜索":
            # 正则搜索：使用 WHOOSH 的正则查询（在 content 和 filename 两个字段中搜索）
            try:
                from whoosh.query import Regex, Or
                
                # 创建两个正则查询（content 和 filename）
                content_regex = Regex("content", self.query)
                filename_regex = Regex("filename", self.query)
                
                # 使用 Or 连接（匹配任意一个字段）
                query_obj = Or([content_regex, filename_regex])
                return self.index_engine.search_with_query(query_obj, self.limit)
            except Exception as e:
                logger.error(f"正则搜索错误：{e}", exc_info=True)
                return []
        else:
            # 模糊搜索：默认模式（分词匹配）
            return self.index_engine.search(self.query, self.limit, search_mode='fuzzy')
    
    def stop(self):
        """停止搜索"""
        self._stop_flag = True


class IndexWorker(QThread):
    """索引工作线程"""
    progress = pyqtSignal(int, int, int, str, float)  # current, total, indexed, filename, remaining_time
    stats_update = pyqtSignal(int, int, int)  # total_files, indexed_count, skipped_count
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, index_engine: IndexEngine, directories: List[Path]):
        super().__init__()
        self.index_engine = index_engine
        self.directories = directories
        self._stop_flag = False
        self._pause_flag = False
        import time
        self._start_time = time.time()
    
    def run(self):
        try:
            import time
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            self._start_time = time.time()
            
            total_files = 0
            indexed_count = 0
            skipped_count = 0
            processed_files = 0
            
            # 第一次遍历：统计文件总数（用于准确进度）
            self.progress.emit(0, 0, 0, "正在扫描文件...", 0)
            for directory in self.directories:
                if self._stop_flag:
                    break
                for file_path in directory.rglob('*'):
                    if self._stop_flag:
                        break
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    if any(part in EXCLUDED_DIRS for part in file_path.parts):
                        continue
                    total_files += 1
            
            self.stats_update.emit(total_files, 0, 0)
            
            # 收集所有需要索引的文件
            files_to_index = []
            for directory in self.directories:
                if self._stop_flag:
                    break
                
                for file_path in directory.rglob('*'):
                    if self._stop_flag:
                        break
                    
                    if not file_path.is_file():
                        continue
                    
                    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        continue
                    
                    if any(part in EXCLUDED_DIRS for part in file_path.parts):
                        continue
                    
                    files_to_index.append(file_path)
            
            # 使用单线程顺序索引（避免并发写入冲突）
            logger.info(f"开始索引，共 {len(files_to_index)} 个文件需要索引")
            
            # 顺序处理每个文件
            for file_path in files_to_index:
                if self._stop_flag:
                    break
                
                # 初始化失败计数器
                failed_count = 0
                
                try:
                    # 解析文件内容
                    content = extract_text(file_path)
                    if content:
                        # 直接写入索引（同步模式）
                        if self.index_engine.add_document(file_path, content):
                            indexed_count += 1
                        else:
                            failed_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    logger.error(f"索引文件失败 {file_path}: {e}")
                    failed_count += 1
                
                processed_files += 1
                
                # 更新进度
                self.progress.emit(processed_files, total_files, indexed_count, file_path.name, 0)
                self.stats_update.emit(total_files, indexed_count, skipped_count)
            
            self.stats_update.emit(total_files, indexed_count, skipped_count)
            
            logger.info(f"索引完成：{indexed_count} 个文件已索引，{skipped_count} 个文件跳过")
            self.finished.emit()
        except Exception as e:
            logger.error(f"索引过程失败：{e}")
            self.error.emit(str(e))
    
    def _index_single_file(self, file_path: Path):
        """索引单个文件（在线程池中执行）"""
        try:
            content = extract_text(file_path)
            if content:
                self.index_engine.add_document(file_path, content)
                return True
            return False
        except Exception as e:
            logger.error(f"索引文件失败 {file_path}: {e}")
            return False
    
    def stop(self):
        """停止索引"""
        self._stop_flag = True
    
    def pause(self):
        """暂停索引"""
        self._pause_flag = True
    
    def resume(self):
        """恢复索引"""
        self._pause_flag = False
    
    def is_paused(self) -> bool:
        """检查是否暂停"""
        return self._pause_flag


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.index_engine = IndexEngine()
        self.index_engine.create_index()
        
        self.monitor = FileMonitor()
        self.search_worker = None
        self.index_worker = None
        self._indexing_paused = False
        
        # 从配置加载索引目录
        self.watch_paths = set(config.get_index_directories())
        
        # 搜索结果分页
        self.results_pager = None
        self.all_results = []
        
        self._init_ui()
        self._create_menu()
        self._connect_signals()
        self._create_tray_icon()
        
        # 启动文件监控
        if self.watch_paths:
            from pathlib import Path
            watch_paths = {Path(p) for p in self.watch_paths}
            self.monitor.start(watch_paths, self._on_file_change)
        
        self.setWindowTitle("FastSearch - 轻量级全文搜索")
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
    
    def _init_ui(self):
        """初始化 UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self._create_toolbar()
        
        # 搜索区域
        search_layout = QHBoxLayout()
        search_layout.setSpacing(5)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索...")
        self.search_input.setFont(QFont("Microsoft YaHei", 12))
        self.search_input.setFixedHeight(40)
        search_layout.addWidget(self.search_input, 1)
        
        # 搜索模式选择
        self.search_mode = QComboBox()
        self.search_mode.addItems(["精准搜索", "模糊搜索", "正则搜索"])
        self.search_mode.setFixedHeight(40)
        self.search_mode.setFixedWidth(100)
        self.search_mode.currentTextChanged.connect(self._on_search_mode_changed)
        search_layout.addWidget(self.search_mode)
        
        # 指定目录按钮
        dir_filter_btn = QPushButton("📁 目录")
        dir_filter_btn.setFixedHeight(40)
        dir_filter_btn.setFixedWidth(70)
        dir_filter_btn.clicked.connect(self._set_search_directory)
        search_layout.addWidget(dir_filter_btn)
        
        # 指定类型按钮
        self.type_filter_btn = QPushButton("📄 类型")
        self.type_filter_btn.setFixedHeight(40)
        self.type_filter_btn.setFixedWidth(120)  # 增加宽度以显示更多信息
        self.type_filter_btn.clicked.connect(self._set_file_types)
        search_layout.addWidget(self.type_filter_btn)
        
        self.search_button = QPushButton("🔍 搜索")
        self.search_button.setFixedHeight(40)
        self.search_button.setFixedWidth(100)
        search_layout.addWidget(self.search_button)
        
        # 搜索取消按钮
        self.search_cancel_button = QPushButton("❌ 取消")
        self.search_cancel_button.setFixedHeight(40)
        self.search_cancel_button.setFixedWidth(80)
        self.search_cancel_button.setVisible(False)
        self.search_cancel_button.clicked.connect(self._cancel_search)
        search_layout.addWidget(self.search_cancel_button)
        
        main_layout.addLayout(search_layout)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧：结果表格 + 分页控制
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        
        # 使用表格显示文件列表
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["名称", "修改日期", "类型", "文件大小"])
        
        # 优化列宽设置
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 名称：拉伸填充
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 修改日期：自适应
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 类型：自适应
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 文件大小：自适应
        
        # 设置列宽（使用 setColumnWidth 而不是 setColumnMinimumWidth）
        self.results_table.setColumnWidth(0, 200)  # 名称初始宽度
        self.results_table.setColumnWidth(1, 140)  # 修改日期初始宽度
        self.results_table.setColumnWidth(2, 80)   # 类型初始宽度
        self.results_table.setColumnWidth(3, 100)   # 文件大小初始宽度
        
        # 设置行高（通过 verticalHeader 设置）
        self.results_table.verticalHeader().setDefaultSectionSize(28)
        
        # 表格样式
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.results_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self._show_file_context_menu)
        self.results_table.itemDoubleClicked.connect(self._on_result_double_clicked)
        self.results_table.setAlternatingRowColors(True)  # 交替行颜色
        
        # 设置垂直滚动条策略：需要时显示，否则隐藏
        self.results_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 启用鼠标滚轮翻页
        self.results_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        self.results_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e0e0e0;
                background-color: white;
                alternate-background-color: #f9f9f9;
            }
            QTableWidget::item {
                padding: 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #3399ff;
                color: white;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 6px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                color: #333;
            }
        """)
        
        left_layout.addWidget(self.results_table)
        
        # 分页控制（放在左侧底部）
        page_control_widget = QWidget()
        page_layout = QHBoxLayout(page_control_widget)
        page_layout.setContentsMargins(5, 5, 5, 5)
        
        self.prev_page_btn = QPushButton("⏮️ 上一页")
        self.prev_page_btn.setFixedHeight(30)
        self.prev_page_btn.clicked.connect(self._on_prev_page)
        self.prev_page_btn.setEnabled(False)
        page_layout.addWidget(self.prev_page_btn)
        
        self.page_label = QLabel("第 0/0 页")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setFixedWidth(150)
        page_layout.addWidget(self.page_label)
        
        self.next_page_btn = QPushButton("下一页 ⏭️")
        self.next_page_btn.setFixedHeight(30)
        self.next_page_btn.clicked.connect(self._on_next_page)
        self.next_page_btn.setEnabled(False)
        page_layout.addWidget(self.next_page_btn)
        
        page_layout.addStretch()
        
        # 每页显示数量选择
        page_layout.addWidget(QLabel("每页:"))
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["50", "100", "200", "500"])
        self.page_size_combo.setCurrentText("100")
        self.page_size_combo.setFixedWidth(80)
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        page_layout.addWidget(self.page_size_combo)
        
        left_layout.addWidget(page_control_widget)
        
        splitter.addWidget(left_widget)
        
        # 右侧：增强型预览区域（上下结构）
        self.enhanced_preview = EnhancedPreviewPanel()
        splitter.addWidget(self.enhanced_preview)
        
        # 设置初始分割比例（4:6）
        splitter.setSizes([400, 600])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # 进度条和详细进度信息
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(200)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        # 暂停/继续按钮
        self.pause_button = QPushButton("⏸️ 暂停")
        self.pause_button.setFixedWidth(80)
        self.pause_button.setVisible(False)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.status_bar.addPermanentWidget(self.pause_button)
        
        # 取消按钮
        self.cancel_button = QPushButton("⏹️ 取消")
        self.cancel_button.setFixedWidth(80)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_indexing)
        self.status_bar.addPermanentWidget(self.cancel_button)
        
        # 详细进度标签
        self.progress_detail = QLabel("")
        self.progress_detail.setVisible(False)
        self.status_bar.addWidget(self.progress_detail)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        
        # 初始化搜索过滤
        self.search_directory = None
        self.search_file_types = []
        
        # 从配置加载搜索设置
        self._load_search_settings()
        
        # 设置状态栏提示
        self._setup_status_tips()
    
    def _load_search_settings(self):
        """加载搜索设置"""
        # 加载文件类型设置
        self.search_file_types = config.get_search_file_types()
        if self.search_file_types:
            self.status_bar.showMessage(f"已加载文件类型过滤：{', '.join(self.search_file_types)}", 2000)
            # 更新类型按钮文本显示已选择的类型
            self._update_type_button_text()
        
        # 加载搜索模式设置
        saved_mode = config.get_search_mode()
        index = self.search_mode.findText(saved_mode)
        if index >= 0:
            self.search_mode.setCurrentIndex(index)
        
        # 加载搜索目录设置（默认全选）
        saved_dirs = config.get_search_directory()
        index_dirs = config.get_index_directories()
        
        if saved_dirs:
            # 如果配置中有保存的目录，使用配置
            self.search_directory = saved_dirs
            if isinstance(saved_dirs, list):
                dir_names = [Path(d).name for d in saved_dirs]
                self.status_bar.showMessage(f"已加载目录选择：{', '.join(dir_names)}", 2000)
            else:
                self.status_bar.showMessage(f"已加载目录选择：{Path(saved_dirs).name}", 2000)
        else:
            # 如果没有配置，默认全选
            self.search_directory = index_dirs
            if index_dirs:
                dir_names = [Path(d).name for d in index_dirs]
                self.status_bar.showMessage(f"已选择全部 {len(index_dirs)} 个索引目录：{', '.join(dir_names)}", 3000)
            else:
                self.status_bar.showMessage("暂无索引目录", 2000)
    
    def _update_type_button_text(self):
        """更新类型按钮文本，显示当前已选择的类型"""
        if self.search_file_types:
            if len(self.search_file_types) == 1:
                self.type_filter_btn.setText(f"📄 类型 ({self.search_file_types[0]})")
            elif len(self.search_file_types) <= 3:
                self.type_filter_btn.setText(f"📄 类型 ({', '.join(self.search_file_types)})")
            else:
                self.type_filter_btn.setText(f"📄 类型 ({len(self.search_file_types)} 个)")
        else:
            self.type_filter_btn.setText("📄 类型")
    
    def _on_search_mode_changed(self, mode: str):
        """搜索模式改变时保存"""
        config.set_search_mode(mode)
    
    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        self.index_action = QAction("📋 索引管理", self)
        toolbar.addAction(self.index_action)
        
        toolbar.addSeparator()
        
        self.refresh_action = QAction("🔄 刷新索引", self)
        toolbar.addAction(self.refresh_action)
        
        toolbar.addSeparator()
        
        bookmark_action = QAction("🔖 书签管理", self)
        bookmark_action.triggered.connect(self._show_bookmark_manager)
        toolbar.addAction(bookmark_action)
        
        toolbar.addSeparator()
        
        history_action = QAction("📜 历史记录", self)
        history_action.triggered.connect(self._show_history)
        toolbar.addAction(history_action)
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("文件")
        
        add_dir_action = QAction("添加索引目录", self)
        add_dir_action.triggered.connect(self._show_index_manager)
        file_menu.addAction(add_dir_action)
        
        refresh_action = QAction("刷新索引", self)
        refresh_action.triggered.connect(self._refresh_index_from_config)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _connect_signals(self):
        """连接信号"""
        self.search_button.clicked.connect(self._start_search)
        self.search_input.returnPressed.connect(self._start_search)
        
        self.results_table.itemClicked.connect(self._on_result_selected)
        
        self.index_action.triggered.connect(self._show_index_manager)
        self.refresh_action.triggered.connect(self._refresh_index_from_config)
    
    def _start_search(self):
        """开始搜索"""
        query = self.search_input.text().strip()
        if not query:
            self.status_label.setText("请输入搜索关键词")
            return
        
        # 获取搜索模式
        search_mode = self.search_mode.currentText()
        
        # 显示搜索开始状态（包含目录信息）
        if self.search_directory:
            if isinstance(self.search_directory, list):
                dir_names = [Path(d).name for d in self.search_directory]
                dir_info = f"{', '.join(dir_names)} ({len(dir_names)} 个目录)"
            else:
                dir_info = Path(self.search_directory).name
            self.status_label.setText(f"🔍 正在搜索：{query} ({search_mode}) - 范围：{dir_info}...")
        else:
            self.status_label.setText(f"🔍 正在搜索：{query} ({search_mode})...")
        
        self.results_table.setRowCount(0)
        self.enhanced_preview.clear()
        self.search_cancel_button.setVisible(True)
        
        self.search_worker = SearchWorker(self.index_engine, query, search_mode)
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.finished.connect(self._on_search_finished)
        self.search_worker.start()
    
    def _on_search_results(self, results: List[Dict[str, Any]]):
        """处理搜索结果（带分页）"""
        try:
            self.search_cancel_button.setVisible(False)
            self.results_table.setRowCount(0)
            
            if not results:
                self.status_label.setText("❌ 未找到匹配的结果")
                self.all_results = []
                self.results_pager = None
                return
            
            # 应用过滤
            filtered_results = self._filter_results(results)
            
            # 保存所有结果并创建分页器
            self.all_results = filtered_results
            self.results_pager = SearchResultsPager(filtered_results, page_size=100)
            
            # 显示第一页
            self._display_results_page(0)
            
            # 显示搜索结果状态
            if len(filtered_results) == 0:
                self.status_label.setText("❌ 未找到匹配的结果")
            elif len(filtered_results) == 1:
                self.status_label.setText(f"✅ 找到 1 个结果")
            else:
                total_pages = self.results_pager.total_pages()
                self.status_label.setText(f"✅ 找到 {len(filtered_results)} 个结果（共 {total_pages} 页）")
        except Exception as e:
            logger.error(f"处理搜索结果失败：{e}")
            self.status_label.setText(f"❌ 搜索出错：{str(e)}")
            self.all_results = []
            self.results_pager = None
    
    def _display_results_page(self, page_num: int):
        """显示指定页的结果"""
        try:
            if not self.results_pager:
                return
            
            # 清空表格
            self.results_table.setRowCount(0)
            
            # 获取当前页的结果
            page_results = self.results_pager.get_page(page_num)
            
            if not page_results:
                return
            
            # 填充表格
            self.results_table.setRowCount(len(page_results))
            
            for i, result in enumerate(page_results):
                # 名称
                name_item = QTableWidgetItem(result['filename'])
                name_item.setData(Qt.UserRole, result['path'])
                self.results_table.setItem(i, 0, name_item)
                
                # 修改日期
                try:
                    from datetime import datetime
                    mtime = Path(result['path']).stat().st_mtime
                    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                except:
                    date_str = "未知"
                self.results_table.setItem(i, 1, QTableWidgetItem(date_str))
                
                # 类型
                ext = Path(result['filename']).suffix.upper()
                self.results_table.setItem(i, 2, QTableWidgetItem(ext if ext else "文件"))
                
                # 文件大小
                try:
                    size = Path(result['path']).stat().st_size
                    # 格式化文件大小显示
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    elif size < 1024 * 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                except:
                    size_str = "未知"
                self.results_table.setItem(i, 3, QTableWidgetItem(size_str))
            
            # 更新状态栏显示页码
            total_pages = self.results_pager.total_pages()
            current_page = self.results_pager.current_page + 1  # 从 1 开始计数
            self.status_label.setText(f"📄 第 {current_page}/{total_pages} 页，共 {len(self.all_results)} 个结果")
            
            # 更新分页按钮
            self._update_page_buttons()
        except Exception as e:
            logger.error(f"显示结果页失败：{e}")
            self.status_label.setText(f"❌ 显示结果失败：{str(e)}")
    
    def _filter_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤搜索结果"""
        import os
        filtered = results
        
        # 目录过滤（支持多选）
        if self.search_directory:
            # 如果是列表，说明是多选模式
            if isinstance(self.search_directory, list):
                # 规范化所有选中的目录路径
                normalized_dirs = [
                    os.path.normpath(os.path.abspath(d)) 
                    for d in self.search_directory
                ]
                # 检查文件路径是否以任一选中目录开头
                filtered = [
                    r for r in filtered 
                    if any(
                        os.path.normpath(os.path.abspath(r['path'])).startswith(dir_path)
                        for dir_path in normalized_dirs
                    )
                ]
            else:
                # 单个目录（旧版本兼容）
                normalized_dir = os.path.normpath(os.path.abspath(self.search_directory))
                filtered = [
                    r for r in filtered 
                    if os.path.normpath(os.path.abspath(r['path'])).startswith(normalized_dir)
                ]
        
        # 文件类型过滤
        if self.search_file_types:
            filtered = [r for r in filtered if Path(r['filename']).suffix.lower() in self.search_file_types]
        
        return filtered
    
    def _on_prev_page(self):
        """上一页"""
        if self.results_pager and self.results_pager.has_previous():
            self.results_pager.previous_page()
            self._display_results_page(self.results_pager.current_page)
            self._update_page_buttons()
    
    def _on_next_page(self):
        """下一页"""
        if self.results_pager and self.results_pager.has_next():
            self.results_pager.next_page()
            self._display_results_page(self.results_pager.current_page)
            self._update_page_buttons()
    
    def _on_page_size_changed(self, size_str: str):
        """每页显示数量改变"""
        if not self.all_results:
            return
        
        page_size = int(size_str)
        self.results_pager = SearchResultsPager(self.all_results, page_size=page_size)
        self._display_results_page(0)
        self._update_page_buttons()
    
    def _update_page_buttons(self):
        """更新分页按钮状态"""
        if not self.results_pager:
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
            self.page_label.setText("第 0/0 页")
            return
        
        total_pages = self.results_pager.total_pages()
        current_page = self.results_pager.current_page + 1  # 从 1 开始计数
        
        self.prev_page_btn.setEnabled(self.results_pager.has_previous())
        self.next_page_btn.setEnabled(self.results_pager.has_next())
        self.page_label.setText(f"第 {current_page}/{total_pages} 页")
    
    def _on_search_finished(self):
        """搜索完成"""
        self.search_cancel_button.setVisible(False)
        # 如果状态栏还是"正在搜索"，说明没有触发 results_ready（可能是空结果）
        current_status = self.status_label.text()
        if "正在搜索" in current_status:
            self.status_label.setText("⏸️ 搜索已完成，但没有更多结果")
    
    def _cancel_search(self):
        """取消搜索"""
        if self.search_worker:
            self.search_worker.stop()
            self.search_cancel_button.setVisible(False)
            self.status_label.setText("⛔ 搜索已取消")
    
    def _on_result_selected(self, item):
        """处理结果选择"""
        row = item.row()
        path_item = self.results_table.item(row, 0)
        if not path_item:
            return
        
        file_path = path_item.data(Qt.UserRole)
        if not file_path:
            return
        
        file_path = Path(file_path)
        if not file_path.exists():
            self.enhanced_preview.code_editor.setPlainText("文件不存在")
            return
        
        # 使用线程解析文件，避免阻塞 UI
        import threading
        
        self.status_label.setText(f"📖 正在加载：{file_path.name}...")
        
        result = [None]
        error = [None]
        
        def extract():
            try:
                result[0] = extract_text(file_path)
            except Exception as e:
                error[0] = str(e)
        
        thread = threading.Thread(target=extract)
        thread.daemon = True
        thread.start()
        thread.join(timeout=10)  # 10 秒超时
        
        if thread.is_alive():
            self.enhanced_preview.code_editor.setPlainText(
                f"[文件加载超时]\n文件过大或内容复杂：{file_path.name}\n\n"
                f"建议使用其他工具打开查看。"
            )
            self.status_label.setText("⏱️ 文件加载超时")
            return
        
        if error[0]:
            self.enhanced_preview.code_editor.setPlainText(f"[加载失败]\n{error[0]}")
            self.status_label.setText("❌ 文件加载失败")
            return
        
        content = result[0]
        if content:
            self.enhanced_preview.code_editor.setPlainText(content)
            
            query = self.search_input.text().strip()
            if query:
                # 高亮关键词
                self.enhanced_preview.code_editor.highlight_text(query, QColor(255, 255, 0))
                
                # 在文件中搜索并定位到第一个匹配
                self.enhanced_preview.search_panel.perform_search(query)
            
            # 添加到历史记录
            history_manager.add_entry(str(file_path), file_path.name)
            self.status_label.setText(f"✅ 已加载：{file_path.name}")
        else:
            self.enhanced_preview.code_editor.setPlainText("无法预览此文件")
            self.status_label.setText("⚠️ 无法解析文件内容")
    
    def _on_result_double_clicked(self, item):
        """双击结果"""
        self._on_result_selected(item)
        # 可以在这里添加自动打开文件的操作
    
    def _show_index_manager(self):
        """显示索引管理对话框"""
        dialog = IndexManagerDialog(self.index_engine, self)
        dialog.exec_()
    
    def _refresh_index_from_config(self):
        """从配置刷新索引（使用已配置的目录）"""
        directories = config.get_index_directories()
        
        if not directories:
            QMessageBox.warning(
                self,
                "提示",
                '尚未配置索引目录，请先点击"索引管理"添加目录'
            )
            return
        
        # 转换为 Path 对象
        from pathlib import Path
        path_objects = [Path(d) for d in directories]
        
        reply = QMessageBox.question(
            self,
            "确认刷新",
            f"将对以下 {len(directories)} 个目录重新索引:\n\n" +
            "\n".join([f"  • {d}" for d in directories]) +
            "\n\n确定开始？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._start_indexing(path_objects)
    
    def _start_indexing(self, directories: List[Path]):
        """开始索引"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.pause_button.setVisible(True)
        self.cancel_button.setVisible(True)
        self.progress_detail.setVisible(True)
        self._indexing_paused = False
        self.pause_button.setText("暂停")
        
        self.index_worker = IndexWorker(self.index_engine, directories)
        self.index_worker.progress.connect(self._on_index_progress)
        self.index_worker.stats_update.connect(self._on_stats_update)
        self.index_worker.finished.connect(self._on_index_finished)
        self.index_worker.error.connect(self._on_index_error)
        self.index_worker.start()
        
        self.status_label.setText("正在扫描文件...")
    
    def _on_index_progress(self, processed: int, total: int, indexed: int, file_path: str, remaining: float):
        """索引进度更新"""
        if total > 0:
            progress = int(processed / total * 100)
            self.progress_bar.setValue(progress)
        
        # 格式化剩余时间
        if remaining > 60:
            time_str = f"{remaining / 60:.1f} 分钟"
        else:
            time_str = f"{remaining:.0f} 秒"
        
        # 显示详细进度
        self.progress_detail.setText(
            f"已处理：{processed}/{total} | 已索引：{indexed} | 剩余：{time_str}"
        )
        
        # 显示当前文件名
        filename = Path(file_path).name if file_path else ""
        if len(filename) > 50:
            filename = "..." + filename[-47:]
        self.status_label.setText(f"索引中：{filename}")
    
    def _on_stats_update(self, total: int, indexed: int, skipped: int):
        """统计信息更新"""
        # 可以在这里更新其他 UI 元素
        pass
    
    def _toggle_pause(self):
        """切换暂停/继续状态"""
        if not self.index_worker:
            return
        
        if self._indexing_paused:
            self.index_worker.resume()
            self.pause_button.setText("暂停")
            self.status_label.setText("正在索引...")
            self._indexing_paused = False
        else:
            self.index_worker.pause()
            self.pause_button.setText("继续")
            self.status_label.setText("已暂停")
            self._indexing_paused = True
    
    def _cancel_indexing(self):
        """取消索引"""
        if not self.index_worker:
            return
        
        reply = QMessageBox.question(
            self,
            "确认取消",
            "确定要取消当前索引任务吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.index_worker.stop()
            self.status_label.setText("已取消索引")
            self.pause_button.setVisible(False)
            self.cancel_button.setVisible(False)
            self.progress_detail.setVisible(False)
    
    def _on_index_finished(self):
        """索引完成"""
        self.progress_bar.setVisible(False)
        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.progress_detail.setVisible(False)
        self.status_label.setText("索引完成")
        QMessageBox.information(self, "完成", "索引已更新完成")
    
    def _on_index_error(self, error: str):
        """索引错误"""
        self.progress_bar.setVisible(False)
        self.pause_button.setVisible(False)
        self.cancel_button.setVisible(False)
        self.progress_detail.setVisible(False)
        self.status_label.setText("索引失败")
        QMessageBox.critical(self, "错误", f"索引失败：{error}")
    
    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于 FastSearch",
            "<h2>FastSearch</h2>"
            "<p>版本：1.0.0</p>"
            "<p>轻量级全文搜索工具</p>"
            "<p>© 2026</p>"
        )
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _update_watch_paths(self, directories: List[str]):
        """更新监控目录"""
        from pathlib import Path
        
        # 停止当前监控
        self.monitor.stop()
        
        # 更新目录列表
        self.watch_paths = set(directories)
        
        # 重新启动监控
        if self.watch_paths:
            watch_paths = {Path(p) for p in self.watch_paths}
            self.monitor.start(watch_paths, self._on_file_change)
            print(f"重新开始监控 {len(watch_paths)} 个目录")
    
    def _on_file_change(self, file_path: Path, event_type: str):
        """
        处理文件变化事件
        
        注意：这里不自动索引，只记录日志
        避免与主索引线程冲突
        """
        try:
            if event_type == 'delete':
                logger.info(f"文件已删除：{file_path}，将从索引中移除")
                self.index_engine.remove_document(file_path)
            elif event_type == 'create':
                logger.info(f"文件已创建：{file_path}，将在下次索引时添加")
            elif event_type == 'modify':
                logger.info(f"文件已修改：{file_path}，将在下次索引时更新")
        except Exception as e:
            logger.error(f"处理文件变化事件失败 {file_path}: {e}")
    
    def _setup_status_tips(self):
        """设置状态栏提示信息"""
        # 为各个按钮设置状态栏提示
        tips = {
            self.search_button: "开始搜索，支持精准、模糊和正则表达式搜索",
            self.search_mode: "选择搜索模式：精准搜索、模糊匹配或正则表达式",
            self.pause_button: "暂停或继续当前的索引任务",
            self.cancel_button: "取消当前的索引或搜索任务",
            self.refresh_action: "使用已配置的目录重新建立索引",
            self.index_action: "管理索引目录，添加或删除要索引的文件夹",
        }
        
        for widget, tip in tips.items():
            widget.setStatusTip(tip)
            # 使用 hovered 信号（适用于 QPushButton）
            if hasattr(widget, 'hovered'):
                widget.hovered.connect(lambda checked=False, t=tip: self.status_bar.showMessage(t, 5000))
    
    def _set_search_directory(self):
        """设置搜索目录 - 从已添加的索引目录中选择（支持多选）"""
        # 获取已添加的索引目录列表
        index_dirs = config.get_index_directories()
        
        if not index_dirs:
            QMessageBox.information(self, "提示", "暂无索引目录，请先在索引管理中添加目录")
            return
        
        # 创建选择对话框（简洁风格）
        dialog = QDialog(self)
        dialog.setWindowTitle("选择搜索范围")
        dialog.resize(550, 450)
        
        # 简洁的样式表
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #333;
                font-size: 13px;
            }
            QListWidget {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
                font-size: 12px;
                selection-background-color: #0078D7;
                selection-color: white;
            }
            QListWidget::item:hover {
                background-color: #e5f3ff;
            }
            QListWidget::item:selected {
                background-color: #0078D7;
            }
            QPushButton {
                background-color: #0078D7;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #003c66;
            }
        """)
        
        # 主布局
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题
        title_label = QLabel("从已添加的索引目录中选择（支持多选）：")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(title_label)
        
        # 创建目录列表（支持多选）
        dir_list = QListWidget()
        dir_list.setSelectionMode(QListWidget.MultiSelection)  # 支持多选
        dir_list.setMinimumHeight(280)
        
        # 添加所有索引目录（简洁显示）
        for dir_path in index_dirs:
            # 简洁显示：目录名称 + 路径
            dir_name = Path(dir_path).name
            full_path = str(dir_path)
            item = QListWidgetItem(f"📁 {dir_name}  ({full_path})")
            item.setData(Qt.UserRole, dir_path)
            item.setToolTip(full_path)  # 鼠标悬停显示完整路径
            dir_list.addItem(item)
        
        main_layout.addWidget(dir_list)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        # 全选按钮
        select_all_btn = QPushButton("✓ 全选")
        select_all_btn.clicked.connect(lambda: [dir_list.item(i).setSelected(True) for i in range(dir_list.count())])
        button_layout.addWidget(select_all_btn)
        
        # 反选按钮
        invert_btn = QPushButton("⇄ 反选")
        invert_btn.setStyleSheet("background-color: #FF9800;")
        invert_btn.clicked.connect(lambda: [dir_list.item(i).setSelected(not dir_list.item(i).isSelected()) for i in range(dir_list.count())])
        button_layout.addWidget(invert_btn)
        
        # 重置按钮（改为重置为全选，而不是清空）
        reset_btn = QPushButton("↺ 重置")
        reset_btn.setStyleSheet("background-color: #2196F3;")
        reset_btn.clicked.connect(lambda: [dir_list.item(i).setSelected(True) for i in range(dir_list.count())])
        reset_btn.setToolTip("重置为全选状态")
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # 统计信息
        count_label = QLabel(f"共 {len(index_dirs)} 个索引目录")
        count_label.setStyleSheet("color: #666; font-size: 11px;")
        main_layout.addWidget(count_label)
        
        # 确定/取消按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        main_layout.addWidget(button_box)
        
        if dialog.exec_() == QDialog.Accepted:
            # 获取所有选中的目录
            import os
            selected_dirs = []
            for i in range(dir_list.count()):
                item = dir_list.item(i)
                if item.isSelected():
                    # 规范化路径
                    dir_path = item.data(Qt.UserRole)
                    normalized_path = os.path.normpath(os.path.abspath(dir_path))
                    selected_dirs.append(normalized_path)
            
            if selected_dirs:
                self.search_directory = selected_dirs  # 存储为列表
                # 保存到配置
                config.set_search_directory(selected_dirs)
                dir_names = [Path(d).name for d in selected_dirs]
                self.status_bar.showMessage(f"已选择 {len(selected_dirs)} 个目录：{', '.join(dir_names)}", 3000)
            else:
                # 如果没有选择，默认全选
                self.search_directory = index_dirs
                # 清空配置（表示全选）
                config.clear_search_directory()
                self.status_bar.showMessage(f"已选择全部 {len(index_dirs)} 个索引目录", 3000)
        else:
            # 如果取消，默认全选
            self.search_directory = index_dirs
            # 清空配置（表示全选）
            config.clear_search_directory()
            self.status_bar.showMessage("已选择全部索引目录", 2000)
    
    def _set_file_types(self):
        """设置文件类型过滤"""
        dialog = QDialog(self)
        dialog.setWindowTitle("选择文件类型")
        dialog.resize(500, 600)
        
        layout = QVBoxLayout(dialog)
        
        label = QLabel("选择要搜索的文件类型（可多选）:")
        layout.addWidget(label)
        
        # 创建带分组的列表
        from PyQt5.QtWidgets import QListWidget, QListWidgetItem
        from PyQt5.QtCore import Qt
        
        type_list = QListWidget()
        type_list.setSelectionMode(QListWidget.ExtendedSelection)
        
        # 完整的文件类型列表（按分类排序）
        file_types = [
            # 文本和代码文件
            ("📝 文本文件", None),  # 分组标题
            (".txt", "纯文本文件"),
            (".md", "Markdown 文档"),
            (".rst", "reStructuredText"),
            (".log", "日志文件"),
            (".csv", "CSV 数据文件"),
            (".ini", "配置文件"),
            (".cfg", "配置文件"),
            (".conf", "配置文件"),
            (".json", "JSON 数据"),
            (".xml", "XML 文档"),
            (".yaml", "YAML 配置"),
            (".yml", "YAML 配置"),
            
            ("💻 源代码", None),
            (".py", "Python 脚本"),
            (".js", "JavaScript"),
            (".ts", "TypeScript"),
            (".java", "Java"),
            (".cpp", "C++"),
            (".c", "C 语言"),
            (".h", "C/C++ 头文件"),
            (".cs", "C#"),
            (".php", "PHP"),
            (".rb", "Ruby"),
            (".go", "Go"),
            (".html", "HTML 网页"),
            (".htm", "HTML 网页"),
            (".css", "样式表"),
            
            # Office 文档
            ("📄 Word 文档", None),
            (".docx", "Word 文档"),
            (".doc", "Word 97-2003"),
            (".docm", "Word 宏文档"),
            (".dotx", "Word 模板"),
            (".dotm", "Word 宏模板"),
            
            ("📊 Excel 表格", None),
            (".xlsx", "Excel 工作簿"),
            (".xls", "Excel 97-2003"),
            (".xlsm", "Excel 宏工作簿"),
            (".et", "WPS 表格"),
            
            ("📽️ PowerPoint 演示", None),
            (".pptx", "PowerPoint 演示"),
            (".ppt", "PowerPoint 97-2003"),
            (".pptm", "PowerPoint 宏演示"),
            (".potx", "PowerPoint 模板"),
            (".potm", "PowerPoint 宏模板"),
            (".dps", "WPS 演示"),
            
            # 电子书格式
            ("📖 电子书", None),
            (".epub", "EPUB 电子书"),
            (".mobi", "MOBI 电子书"),
            (".azw", "Kindle AZW"),
            (".azw3", "Kindle AZW3"),
            
            # 其他文档
            ("📚 其他文档", None),
            (".pdf", "PDF 文档"),
            (".rtf", "RTF 文档"),
            (".odt", "OpenDocument 文本"),
            (".ods", "OpenDocument 表格"),
            (".odp", "OpenDocument 演示"),
        ]
        
        # 添加项目到列表
        for type_ext, description in file_types:
            if description is None:
                # 分组标题
                item = QListWidgetItem(type_ext)
                item.setFlags(Qt.NoItemFlags)  # 不可选择
                # 设置标题样式
                font = item.font()
                font.setBold(True)
                font.setPointSize(font.pointSize() + 1)
                item.setFont(font)
                type_list.addItem(item)
            else:
                # 文件类型
                item = QListWidgetItem(f"{type_ext}  {description}")
                item.setData(Qt.UserRole, type_ext)  # 存储扩展名
                # 如果该类型已在选择列表中，设置为选中状态
                if type_ext in self.search_file_types:
                    item.setSelected(True)
                type_list.addItem(item)
        
        layout.addWidget(type_list)
        
        # 快速选择按钮
        select_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(lambda: self._select_all_types(type_list))
        select_layout.addWidget(select_all_btn)
        
        select_text_btn = QPushButton("文本文件")
        select_text_btn.clicked.connect(lambda: self._select_category(type_list, ["📝 文本文件", "💻 源代码"]))
        select_layout.addWidget(select_text_btn)
        
        select_office_btn = QPushButton("Office 文档")
        select_office_btn.clicked.connect(lambda: self._select_category(type_list, ["📄 Word 文档", "📊 Excel 表格", "📽️ PowerPoint 演示"]))
        select_layout.addWidget(select_office_btn)
        
        select_ebook_btn = QPushButton("电子书")
        select_ebook_btn.clicked.connect(lambda: self._select_category(type_list, ["📖 电子书"]))
        select_layout.addWidget(select_ebook_btn)
        
        select_layout.addStretch()
        layout.addLayout(select_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec_() == QDialog.Accepted:
            selected = []
            for i in range(type_list.count()):
                item = type_list.item(i)
                if item.isSelected() and item.data(Qt.UserRole):
                    selected.append(item.data(Qt.UserRole))
            
            self.search_file_types = selected
            # 保存到配置
            config.set_search_file_types(selected)
            # 更新按钮文本
            self._update_type_button_text()
            self.status_bar.showMessage(f"文件类型：{', '.join(selected) if selected else '全部'}", 3000)
    
    def _select_all_types(self, type_list: QListWidget):
        """全选所有文件类型"""
        from PyQt5.QtCore import Qt
        for i in range(type_list.count()):
            item = type_list.item(i)
            if item.flags() != Qt.NoItemFlags:  # 不是分组标题
                item.setSelected(True)
    
    def _select_category(self, type_list: QListWidget, categories: list):
        """选择指定分类的所有类型"""
        from PyQt5.QtCore import Qt
        current_category = None
        for i in range(type_list.count()):
            item = type_list.item(i)
            text = item.text()
            
            # 检查是否是分组标题
            if item.flags() == Qt.NoItemFlags:
                # 更新当前分类
                for cat in categories:
                    if text.startswith(cat.split(" ")[0]):  # 匹配 emoji
                        current_category = cat
                        break
                continue
            
            # 如果在目标分类中，选中该项
            if current_category in categories and item.data(Qt.UserRole):
                item.setSelected(True)
    
    def _show_file_context_menu(self, pos):
        """显示文件列表右键菜单"""
        row = self.results_table.rowAt(pos.y())
        if row < 0:
            return
        
        item = self.results_table.item(row, 0)
        if not item:
            return
        
        file_path = item.data(Qt.UserRole)
        
        # 如果右键点击的行没有被选中，则选中该行
        if not item.isSelected():
            self.results_table.clearSelection()
            self.results_table.selectRow(row)
        
        menu = QContextMenu(self)
        
        open_file_action = QAction("📂 打开文件", self)
        open_file_action.triggered.connect(lambda: self._open_file(file_path))
        menu.addAction(open_file_action)
        
        open_folder_action = QAction("📁 打开所在文件夹", self)
        open_folder_action.triggered.connect(lambda: self._open_file_location(file_path))
        menu.addAction(open_folder_action)
        
        menu.addSeparator()
        
        copy_path_action = QAction("� 复制路径", self)
        copy_path_action.triggered.connect(lambda: self._copy_file_path(file_path))
        menu.addAction(copy_path_action)
        
        menu.addSeparator()
        
        history_action = QAction("📜 查看历史", self)
        history_action.triggered.connect(self._show_history)
        menu.addAction(history_action)
        
        bookmark_action = QAction("🔖 添加到书签", self)
        bookmark_action.triggered.connect(lambda: self._add_bookmark(file_path))
        menu.addAction(bookmark_action)
        
        menu.exec_(self.results_table.viewport().mapToGlobal(pos))
    
    def _open_file(self, file_path: str):
        """打开文件"""
        try:
            if file_path and Path(file_path).exists():
                # 使用 os.startfile 打开文件（Windows 原生方法）
                os.startfile(str(file_path))
                # 添加到历史记录
                history_manager.add_entry(file_path, Path(file_path).name)
                self.status_bar.showMessage(f"已打开：{Path(file_path).name}", 2000)
            else:
                QMessageBox.warning(self, "文件不存在", f"文件已不存在：\n{file_path}")
                logger.warning(f"文件不存在：{file_path}")
        except Exception as e:
            logger.error(f"打开文件失败：{e}", exc_info=True)
            QMessageBox.critical(self, "打开失败", f"无法打开文件：\n{str(e)}\n\n请确保文件关联了相应的应用程序")
    
    def _open_file_location(self, file_path: str):
        """打开文件所在文件夹"""
        if file_path and Path(file_path).exists():
            os.startfile(str(Path(file_path).parent))
    
    def _copy_file_path(self, file_path: str):
        """复制文件路径"""
        if file_path:
            QApplication.clipboard().setText(file_path)
            self.status_bar.showMessage("路径已复制到剪贴板", 2000)
    
    def _get_selected_files(self) -> List[str]:
        """获取选中的文件列表"""
        files = []
        selected_rows = set()
        
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.isSelected():
                # 避免重复添加同一行
                if row not in selected_rows:
                    selected_rows.add(row)
                    file_path = item.data(Qt.UserRole)
                    if file_path:
                        files.append(file_path)
        
        return files
    
    def _change_preview_zoom(self, size: int):
        """改变预览字体大小"""
        font = self.enhanced_preview.code_editor.font()
        font.setPointSize(size)
        self.enhanced_preview.code_editor.setFont(font)
    
    def _show_history(self):
        """显示浏览历史"""
        dialog = QDialog(self)
        dialog.setWindowTitle("浏览历史")
        dialog.resize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        history_table = QTableWidget()
        history_table.setColumnCount(2)
        history_table.setHorizontalHeaderLabels(["文件名", "查看时间"])
        history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        history_table.setSelectionBehavior(QTableWidget.SelectRows)
        history_table.setContextMenuPolicy(Qt.CustomContextMenu)  # 启用自定义右键菜单
        
        entries = history_manager.get_entries(50)
        history_table.setRowCount(len(entries))
        
        for i, entry in enumerate(entries):
            history_table.setItem(i, 0, QTableWidgetItem(entry.filename))
            history_table.setItem(i, 1, QTableWidgetItem(entry.viewed_at))
            history_table.item(i, 0).setData(Qt.UserRole, entry.file_path)
            history_table.item(i, 1).setData(Qt.UserRole, entry.file_path)
        
        # 连接双击事件（打开文件）
        history_table.itemDoubleClicked.connect(
            lambda item: self._open_file_from_history(item, dialog)
        )
        
        # 连接右键菜单信号
        history_table.customContextMenuRequested.connect(
            lambda pos: self._show_history_context_menu(history_table, pos, dialog)
        )
        
        layout.addWidget(history_table)
        
        button_layout = QHBoxLayout()
        
        clear_button = QPushButton("清空历史")
        clear_button.clicked.connect(lambda: self._clear_history(history_table))
        button_layout.addWidget(clear_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.close)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def _show_history_context_menu(self, table: QTableWidget, pos, dialog):
        """显示历史记录右键菜单"""
        selected_row = table.rowAt(pos.y())
        if selected_row < 0:
            return
        
        item = table.item(selected_row, 0)
        if not item:
            return
        
        file_path = item.data(Qt.UserRole)
        if not file_path:
            return
        
        # 创建右键菜单
        menu = QContextMenu(self)
        
        # 打开文件
        open_file_action = QAction("📄 打开文件", self)
        open_file_action.triggered.connect(lambda: self._open_file_from_history_context(file_path, dialog))
        menu.addAction(open_file_action)
        
        # 打开文件所在文件夹
        open_location_action = QAction("📂 打开文件所在文件夹", self)
        open_location_action.triggered.connect(lambda: self._open_file_location(file_path))
        menu.addAction(open_location_action)
        
        # 分隔线
        menu.addSeparator()
        
        # 复制文件路径
        copy_path_action = QAction("📋 复制文件路径", self)
        copy_path_action.triggered.connect(lambda: self._copy_file_path(file_path))
        menu.addAction(copy_path_action)
        
        # 显示菜单
        menu.exec_(table.viewport().mapToGlobal(pos))
    
    def _open_file_from_history(self, item, dialog):
        """双击从历史打开文件"""
        file_path = item.data(Qt.UserRole)
        if file_path:
            self._open_file(file_path)
            dialog.close()
    
    def _open_file_from_history_context(self, file_path: str, dialog):
        """从右键菜单打开历史文件"""
        if file_path and Path(file_path).exists():
            self._open_file(file_path)
            dialog.close()
        else:
            QMessageBox.warning(self, "文件不存在", f"文件已不存在：\n{file_path}")
    
    def _clear_history(self, table: QTableWidget):
        """清空历史"""
        reply = QMessageBox.question(
            self, "确认", "确定要清空浏览历史吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            history_manager.clear()
            table.setRowCount(0)
    
    def _add_bookmark(self, file_path: str):
        """添加书签"""
        if not file_path:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("添加书签")
        dialog.resize(400, 200)
        
        layout = QVBoxLayout(dialog)
        
        # 文件名
        name_input = QLineEdit()
        name_input.setPlaceholderText("书签名称")
        name_input.setText(Path(file_path).name)
        layout.addWidget(QLabel("书签名称:"))
        layout.addWidget(name_input)
        
        # 完整路径
        path_input = QLineEdit()
        path_input.setText(file_path)
        path_input.setReadOnly(True)
        layout.addWidget(QLabel("文件路径:"))
        layout.addWidget(path_input)
        
        # 分组
        group_input = QComboBox()
        group_input.addItems(bookmark_manager.get_all_groups())
        group_input.setEditable(True)
        layout.addWidget(QLabel("书签分组:"))
        layout.addWidget(group_input)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec_() == QDialog.Accepted:
            name = name_input.text().strip()
            group = group_input.currentText().strip()
            
            if name and bookmark_manager.add_bookmark(name, file_path, group):
                self.status_bar.showMessage("书签已添加", 2000)
            else:
                self.status_bar.showMessage("书签已存在", 2000)
    
    def _show_bookmark_manager(self):
        """显示书签管理对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("书签管理")
        dialog.resize(700, 500)
        
        layout = QVBoxLayout(dialog)
        
        # 书签列表
        bookmark_table = QTableWidget()
        bookmark_table.setColumnCount(3)
        bookmark_table.setHorizontalHeaderLabels(["名称", "路径", "分组"])
        bookmark_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        bookmark_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        bookmark_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        bookmark_table.setSelectionBehavior(QTableWidget.SelectRows)
        bookmark_table.setSelectionMode(QTableWidget.SingleSelection)
        bookmark_table.setContextMenuPolicy(Qt.CustomContextMenu)  # 启用自定义右键菜单
        
        bookmarks = bookmark_manager.get_bookmarks()
        bookmark_table.setRowCount(len(bookmarks))
        
        for i, bookmark in enumerate(bookmarks):
            bookmark_table.setItem(i, 0, QTableWidgetItem(bookmark.name))
            bookmark_table.setItem(i, 1, QTableWidgetItem(bookmark.path))
            bookmark_table.setItem(i, 2, QTableWidgetItem(bookmark.group))
            # 保存文件路径到 UserRole
            bookmark_table.item(i, 0).setData(Qt.UserRole, bookmark.path)
            bookmark_table.item(i, 1).setData(Qt.UserRole, bookmark.path)
            bookmark_table.item(i, 2).setData(Qt.UserRole, bookmark.path)
        
        # 连接双击事件（打开书签）
        bookmark_table.itemDoubleClicked.connect(
            lambda item: self._open_bookmark(item, dialog)
        )
        
        # 连接右键菜单信号
        bookmark_table.customContextMenuRequested.connect(
            lambda pos: self._show_bookmark_context_menu(bookmark_table, pos, dialog)
        )
        
        layout.addWidget(bookmark_table)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        add_button = QPushButton("➕ 添加")
        add_button.clicked.connect(lambda: self._add_bookmark_from_manager(dialog))
        button_layout.addWidget(add_button)
        
        delete_button = QPushButton("🗑️ 删除")
        delete_button.clicked.connect(lambda: self._delete_bookmark(bookmark_table))
        button_layout.addWidget(delete_button)
        
        # 分组管理
        group_button = QPushButton("📁 分组管理")
        group_button.clicked.connect(lambda: self._show_group_manager())
        button_layout.addWidget(group_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton("✅ 完成")
        close_button.clicked.connect(dialog.close)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def _show_bookmark_context_menu(self, table: QTableWidget, pos, dialog):
        """显示书签管理右键菜单"""
        selected_row = table.rowAt(pos.y())
        if selected_row < 0:
            return
        
        # 获取文件路径
        item = table.item(selected_row, 0)
        if not item:
            return
        
        file_path = item.data(Qt.UserRole)
        if not file_path:
            return
        
        # 创建右键菜单
        menu = QContextMenu(self)
        
        # 打开文件
        open_file_action = QAction("📄 打开文件", self)
        open_file_action.triggered.connect(lambda: self._open_bookmark_from_context(file_path, dialog))
        menu.addAction(open_file_action)
        
        # 打开文件所在文件夹
        open_location_action = QAction("📂 打开文件所在文件夹", self)
        open_location_action.triggered.connect(lambda: self._open_file_location(file_path))
        menu.addAction(open_location_action)
        
        # 分隔线
        menu.addSeparator()
        
        # 复制文件路径
        copy_path_action = QAction("📋 复制文件路径", self)
        copy_path_action.triggered.connect(lambda: self._copy_file_path(file_path))
        menu.addAction(copy_path_action)
        
        # 显示菜单
        menu.exec_(table.viewport().mapToGlobal(pos))
    
    def _open_bookmark_from_context(self, file_path: str, dialog):
        """从右键菜单打开书签"""
        if file_path and Path(file_path).exists():
            self._open_file(file_path)
            dialog.close()
        else:
            QMessageBox.warning(self, "文件不存在", f"文件已不存在：\n{file_path}")
    
    def _open_bookmark(self, item, dialog):
        """打开书签"""
        row = item.row()
        path_item = bookmark_table.item(row, 1) if 'bookmark_table' in locals() else None
        if path_item:
            file_path = path_item.text()
            self._open_file(file_path)
            dialog.close()
    
    def _add_bookmark_from_manager(self, dialog):
        """从管理器添加书签"""
        # 简化版本，实际应该弹出添加对话框
        QMessageBox.information(self, "提示", "请在文件列表右键菜单中选择'添加到书签'")
    
    def _delete_bookmark(self, table: QTableWidget):
        """删除书签"""
        row = table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择要删除的书签")
            return
        
        name_item = table.item(row, 0)
        path_item = table.item(row, 1)
        
        if path_item:
            reply = QMessageBox.question(
                self, "确认删除", f"确定要删除书签 '{name_item.text()}' 吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                bookmark_manager.remove_bookmark(path_item.text())
                table.removeRow(row)
    
    def _show_group_manager(self):
        """显示分组管理对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("分组管理")
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        group_list = QListWidget()
        group_list.addItems(bookmark_manager.get_all_groups())
        layout.addWidget(QLabel("书签分组列表:"))
        layout.addWidget(group_list)
        
        button_layout = QHBoxLayout()
        
        add_group_btn = QPushButton("➕ 添加分组")
        add_group_btn.clicked.connect(lambda: self._add_group(group_list))
        button_layout.addWidget(add_group_btn)
        
        delete_group_btn = QPushButton("🗑️ 删除分组")
        delete_group_btn.clicked.connect(lambda: self._delete_group(group_list))
        button_layout.addWidget(delete_group_btn)
        
        rename_group_btn = QPushButton("✏️ 重命名")
        rename_group_btn.clicked.connect(lambda: self._rename_group(group_list))
        button_layout.addWidget(rename_group_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("✅ 完成")
        close_btn.clicked.connect(dialog.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        dialog.exec_()
    
    def _add_group(self, group_list: QListWidget):
        """添加分组"""
        name, ok = QInputDialog.getText(self, "添加分组", "请输入分组名称:")
        if ok and name:
            if bookmark_manager.add_group(name):
                group_list.addItem(name)
            else:
                QMessageBox.warning(self, "提示", "分组已存在")
    
    def _delete_group(self, group_list: QListWidget):
        """删除分组"""
        current = group_list.currentItem()
        if not current:
            QMessageBox.warning(self, "提示", "请先选择要删除的分组")
            return
        
        if current.text() == "默认分组":
            QMessageBox.warning(self, "提示", "不能删除默认分组")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除分组 '{current.text()}' 吗？\n该分组的书签将移到默认分组",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            bookmark_manager.remove_group(current.text())
            group_list.takeItem(group_list.row(current))
    
    def _rename_group(self, group_list: QListWidget):
        """重命名分组"""
        current = group_list.currentItem()
        if not current:
            QMessageBox.warning(self, "提示", "请先选择要重命名的分组")
            return
        
        if current.text() == "默认分组":
            QMessageBox.warning(self, "提示", "不能重命名默认分组")
            return
        
        old_name = current.text()
        new_name, ok = QInputDialog.getText(
            self, "重命名分组", "请输入新分组名称:",
            text=old_name
        )
        
        if ok and new_name and new_name != old_name:
            if bookmark_manager.rename_group(old_name, new_name):
                current.setText(new_name)
            else:
                QMessageBox.warning(self, "提示", "重命名失败")
    
    def closeEvent(self, event):
        """关闭事件"""
        logger.info("应用程序正在关闭...")
        self._cleanup_resources()
        event.accept()
    
    def __del__(self):
        """析构函数 - 确保资源被清理（作为 closeEvent 的后备）"""
        # 不再通过析构函数清理，避免竞态条件
        pass
    
    def _cleanup_resources(self):
        """清理资源"""
        try:
            # 避免重复清理
            if hasattr(self, '_cleanup_done') and self._cleanup_done:
                return
            
            logger.info("正在清理资源...")
            
            # 停止文件监控
            if hasattr(self, 'monitor') and self.monitor:
                try:
                    self.monitor.stop()
                    logger.info("文件监控器已停止")
                except Exception as e:
                    logger.error(f"停止监控器失败：{e}")
            
            # 关闭索引引擎
            if hasattr(self, 'index_engine') and self.index_engine:
                try:
                    self.index_engine.close()
                    logger.info("索引引擎已关闭")
                except Exception as e:
                    logger.error(f"关闭索引引擎失败：{e}")
            
            # 停止文件监控调度器
            if hasattr(self, 'scheduler') and self.scheduler:
                try:
                    self.scheduler.stop()
                    logger.info("索引调度器已停止")
                except Exception as e:
                    logger.error(f"停止调度器失败：{e}")
            
            # 停止搜索线程
            if hasattr(self, 'search_worker') and self.search_worker:
                try:
                    self.search_worker.stop()
                    if self.search_worker.isRunning():
                        self.search_worker.wait(1000)  # 等待 1 秒
                    logger.info("搜索线程已停止")
                except Exception as e:
                    logger.error(f"停止搜索线程失败：{e}")
            
            # 停止索引线程
            if hasattr(self, 'index_worker') and self.index_worker:
                try:
                    self.index_worker.stop()
                    if self.index_worker.isRunning():
                        self.index_worker.wait(1000)  # 等待 1 秒
                    logger.info("索引线程已停止")
                except Exception as e:
                    logger.error(f"停止索引线程失败：{e}")
            
            self._cleanup_done = True
            logger.info("资源清理完成")
        except Exception as e:
            logger.error(f"资源清理失败：{e}")
    
    def _create_tray_icon(self):
        """创建系统托盘图标"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        
        # 创建托盘菜单
        tray_menu = QContextMenu()
        
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self._show_from_tray)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(quit_action)
        
        # 创建托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(0))  # 使用标准图标
        self.tray_icon.setToolTip("FastSearch - 轻量级全文搜索")
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
    
    def _show_from_tray(self):
        """从托盘显示窗口"""
        self.showNormal()
        self.activateWindow()
    
    def _on_tray_activated(self, reason):
        """托盘图标被激活"""
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_from_tray()
    
    def _quit_app(self):
        """退出应用"""
        QApplication.quit()
    
    def changeEvent(self, event):
        """窗口状态改变事件"""
        if event.type() == QEvent.WindowStateChange and self.isMinimized():
            # 最小化时隐藏到托盘
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.hide()
        super().changeEvent(event)


class IndexManagerDialog(QDialog):
    """索引管理对话框"""
    
    def __init__(self, index_engine: IndexEngine, parent=None):
        super().__init__(parent)
        self.index_engine = index_engine
        
        # 从配置加载目录列表
        self.directories = config.get_index_directories()
        print(f"从配置加载目录：{self.directories}")  # 调试信息
        
        self.setWindowTitle("索引管理")
        self.resize(700, 500)
        
        layout = QVBoxLayout(self)
        
        # 统计信息区域
        stats_group = QGroupBox("索引统计")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel()
        self._update_stats_label()
        stats_layout.addWidget(self.stats_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # 目录列表区域
        dir_group = QGroupBox("索引目录列表")
        dir_layout = QVBoxLayout()
        
        self.dir_list = QListWidget()
        self.dir_list.setSelectionMode(QListWidget.SingleSelection)
        self.dir_list.itemDoubleClicked.connect(self._on_item_double_click)
        dir_layout.addWidget(self.dir_list)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        add_button = QPushButton("➕ 添加目录")
        add_button.clicked.connect(self._add_directory)
        button_layout.addWidget(add_button)
        
        remove_button = QPushButton("❌ 移除选中")
        remove_button.clicked.connect(self._remove_directory)
        button_layout.addWidget(remove_button)
        
        clear_index_button = QPushButton("🗑️ 清除索引")
        clear_index_button.clicked.connect(self._clear_selected_index)
        button_layout.addWidget(clear_index_button)
        
        rebuild_button = QPushButton("🔄 重建索引")
        rebuild_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        rebuild_button.clicked.connect(self._rebuild_index)
        button_layout.addWidget(rebuild_button)
        
        button_layout.addStretch()
        
        refresh_button = QPushButton("🔄 刷新统计")
        refresh_button.clicked.connect(self._update_stats_label)
        button_layout.addWidget(refresh_button)
        
        close_button = QPushButton("✅ 完成")
        close_button.clicked.connect(self._save_and_close)
        button_layout.addWidget(close_button)
        
        dir_layout.addLayout(button_layout)
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        self._load_directories()
    
    def _update_stats_label(self):
        """更新统计信息显示"""
        stats = self.index_engine.get_stats()
        
        # 基础统计
        stats_text = (
            f"📊 已索引文件：<b>{stats['indexed_files']}</b> 个\n"
            f"⚠️ 失败文件：<b>{stats['failed_files']}</b> 个\n"
            f"💾 总大小：<b>{self._format_size(stats['total_size'])}</b>\n"
            f"📁 索引目录：<b>{len(self.directories)}</b> 个\n"
            f"� 索引文档数：<b>{stats['doc_count']}</b>"
        )
        
        self.stats_label.setText(stats_text)
    
    def _load_directories(self):
        """加载目录列表"""
        self.dir_list.clear()
        
        if not self.directories:
            self.dir_list.addItem("📭 暂无索引目录，请点击上方\"添加目录\"按钮")
            return
        
        for i, dir_path in enumerate(self.directories):
            item_text = f"📁 {dir_path}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, dir_path)  # 存储原始路径
            self.dir_list.addItem(item)
        
        self._update_stats_label()
    
    def _add_directory(self):
        """添加目录"""
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly)
        dialog.setWindowTitle("选择要索引的目录")
        dialog.setDirectory(os.path.expanduser("~"))  # 默认打开用户目录
        
        if dialog.exec_() == QDialog.Accepted:
            selected_paths = dialog.selectedFiles()
            if not selected_paths:
                QMessageBox.warning(self, "提示", "未选择任何目录")
                return
            
            for path in selected_paths:
                if path not in self.directories:
                    self.directories.append(path)
                    print(f"已添加目录：{path}")  # 调试信息
                else:
                    print(f"目录已存在：{path}")  # 调试信息
            
            self._load_directories()
            print(f"当前目录列表：{self.directories}")  # 调试信息
        else:
            print("用户取消了选择")  # 调试信息
    
    def _remove_directory(self):
        """移除选中的目录"""
        current_row = self.dir_list.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要移除的目录")
            return
        
        # 获取选中项的路径
        current_item = self.dir_list.item(current_row)
        dir_path = current_item.data(Qt.UserRole)
        
        if dir_path and dir_path in self.directories:
            self.directories.remove(dir_path)
            self._load_directories()
    
    def _clear_selected_index(self):
        """清除选中目录的索引数据"""
        current_row = self.dir_list.currentRow()
        
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先选择要清除索引的目录")
            return
        
        # 获取选中项的路径
        current_item = self.dir_list.item(current_row)
        dir_path = current_item.data(Qt.UserRole)
        
        if not dir_path:
            return
        
        # 确认操作
        reply = QMessageBox.question(
            self,
            "确认清除",
            f"确定要清除目录 '{dir_path}' 的索引数据吗？\n\n这将删除该目录下所有文件的索引，但不会删除实际文件。\n清除后需要重新索引才能搜索到这些文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # 调用索引引擎的清除方法
                self.index_engine.clear_index_for_directory(dir_path)
                QMessageBox.information(
                    self,
                    "清除成功",
                    f"已清除目录 '{dir_path}' 的索引数据。\n\n请重新索引以更新索引库。"
                )
                self._update_stats_label()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "清除失败",
                    f"清除索引时出错：{str(e)}"
                )
    
    def _rebuild_index(self):
        """完全重建索引"""
        reply = QMessageBox.question(
            self,
            "确认重建",
            "⚠️ 警告：这将完全删除并重建所有索引！\n\n"
            "• 删除所有现有索引数据\n"
            "• 删除元数据库\n"
            "• 重新索引所有配置的文件\n\n"
            "这可能需要较长时间，确定继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # 显示进度对话框
        progress = QProgressDialog("正在重建索引...", "取消", 0, 100, self)
        progress.setWindowTitle("重建索引")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        
        try:
            # 调用重建索引方法
            success = self.index_engine.rebuild_index()
            
            if success:
                QMessageBox.information(
                    self,
                    "重建完成",
                    "✅ 索引已完全重建！\n\n"
                    "现在可以开始重新索引文件。"
                )
                self._update_stats_label()
            else:
                QMessageBox.warning(
                    self,
                    "重建失败",
                    "❌ 重建索引时出错，请查看终端日志。"
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "重建失败",
                f"重建索引时发生错误：\n{str(e)}"
            )
        finally:
            progress.close()
    
    def _on_item_double_click(self, item):
        """双击目录项，在资源管理器中打开"""
        dir_path = item.data(Qt.UserRole)
        if dir_path:
            import os
            os.startfile(dir_path)
    
    def _save_and_close(self):
        """保存并关闭"""
        # 保存配置到文件
        config.set_index_directories(self.directories)
        print(f"保存目录配置：{self.directories}")
        
        # 更新主窗口的监控目录
        if self.parent() and hasattr(self.parent(), '_update_watch_paths'):
            self.parent()._update_watch_paths(self.directories)
        
        self.accept()
    
    def get_directories(self) -> List[str]:
        """获取当前目录列表"""
        return self.directories
    
    def _format_size(self, size: float) -> str:
        """格式化大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


def main():
    app = QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
