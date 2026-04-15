"""
增强型文件预览组件
支持行号显示、文件内搜索、结果高亮等功能
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit,
    QLineEdit, QPushButton, QCheckBox, QSplitter, QLabel,
    QFrame, QScrollArea, QComboBox, QToolButton, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QRegExp
from PyQt5.QtGui import (
    QFont, QTextFormat, QTextCursor, QColor, QPalette,
    QFontMetrics, QTextBlockUserData, QPainter
)
import re
from typing import List, Dict, Tuple, Optional


class LineNumberArea(QWidget):
    """行号显示区域"""
    
    def __init__(self, editor: 'CodeEditor'):
        super().__init__(editor)
        self.codeEditor = editor
        self.setAutoFillBackground(True)
        # 淡灰色背景（比编辑器背景稍深）
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        self.setPalette(palette)
    
    def sizeHint(self):
        return self.codeEditor.lineNumberAreaSize()
    
    def paintEvent(self, event):
        self.codeEditor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    """带行号的代码编辑器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 先设置字体，确保 fontMetrics 可用
        self.setFont(QFont("Consolas", 10))
        
        # 设置护眼背景色（淡灰色）
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #F5F5F5;
                color: #333333;
            }
        """)
        
        # 创建行号区域
        self.lineNumberArea = LineNumberArea(self)
        
        # 连接信号
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        
        # 初始化
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()
    
    def lineNumberAreaSize(self):
        """计算行号区域宽度"""
        digits = 1
        maximum = max(1, self.blockCount())
        while maximum >= 10:
            maximum /= 10
            digits += 1
        
        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def updateLineNumberAreaWidth(self, _):
        """更新行号区域宽度"""
        self.setViewportMargins(self.lineNumberAreaSize(), 0, 0, 0)
    
    def updateLineNumberArea(self, rect, dy):
        """更新行号显示"""
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)
    
    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)
        
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(
            cr.left(), cr.top(), self.lineNumberAreaSize(), cr.height()
        )
    
    def lineNumberAreaPaintEvent(self, event):
        """绘制行号"""
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor(240, 248, 255))  # 淡蓝色背景
        
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        # 淡蓝色数字（更柔和）
        painter.setPen(QColor(128, 128, 128))
        painter.setFont(self.font())
        
        while block.isValid() and (top <= event.rect().bottom()):
            if block.isVisible() and (bottom >= event.rect().top()):
                number = str(blockNumber + 1)
                painter.drawText(0, top, self.lineNumberArea.width() - 5,
                               self.fontMetrics().height(),
                               Qt.AlignRight, number)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber += 1
    
    def highlightCurrentLine(self):
        """高亮当前行"""
        if not self.isReadOnly():
            return
        
        # 清除额外选择
        extraSelections = []
        
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor(255, 255, 225).lighter(110)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)
        
        self.setExtraSelections(extraSelections)
    
    def highlight_text(self, text: str, color: QColor = QColor(255, 255, 0),
                      case_sensitive: bool = False, whole_word: bool = False,
                      use_regex: bool = False):
        """高亮文本"""
        if not text:
            return
        
        # 清除所有额外选择
        extra_selections = []
        
        # 获取全文
        document_text = self.toPlainText()
        
        try:
            if use_regex:
                # 正则表达式搜索
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(text, flags)
                
                for match in pattern.finditer(document_text):
                    start = match.start()
                    end = match.end()
                    
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.KeepAnchor)
                    
                    selection = QTextEdit.ExtraSelection()
                    selection.format.setBackground(color)
                    selection.cursor = cursor
                    extra_selections.append(selection)
            else:
                # 普通文本搜索
                search_text = text
                original_document = document_text  # 保存原始文本用于位置计算
                
                if not case_sensitive:
                    search_text = search_text.lower()
                    document_text = document_text.lower()
                
                start = 0
                while True:
                    pos = document_text.find(search_text, start)
                    if pos == -1:
                        break
                    
                    # 检查是否为完整单词
                    if whole_word:
                        # 检查前一个字符
                        if pos > 0:
                            prev_char = document_text[pos-1]
                            if prev_char.isalnum() or prev_char == '_':
                                start = pos + 1
                                continue
                        
                        # 检查后一个字符
                        end_pos = pos + len(search_text)
                        if end_pos < len(document_text):
                            next_char = document_text[end_pos]
                            if next_char.isalnum() or next_char == '_':
                                start = pos + 1
                                continue
                    
                    # 使用原始位置创建光标（不分大小写时也适用）
                    cursor = QTextCursor(self.document())
                    cursor.setPosition(pos)
                    cursor.setPosition(pos + len(text), QTextCursor.KeepAnchor)
                    
                    selection = QTextEdit.ExtraSelection()
                    selection.format.setBackground(color)
                    selection.cursor = cursor
                    extra_selections.append(selection)
                    
                    start = pos + 1
            
            self.setExtraSelections(extra_selections)
        except Exception as e:
            print(f"高亮失败：{e}")
    
    def clear_highlights(self):
        """清除所有高亮"""
        self.setExtraSelections([])


class SearchMatch:
    """搜索匹配项"""
    
    def __init__(self, line_number: int, line_text: str, match_start: int, match_end: int):
        self.line_number = line_number
        self.line_text = line_text
        self.match_start = match_start
        self.match_end = match_end
    
    def __str__(self):
        return f"Line {self.line_number}: {self.line_text[:50]}..."


class FileSearchPanel(QFrame):
    """文件内搜索面板"""
    
    match_selected = pyqtSignal(int)  # 行号
    
    def __init__(self, code_editor: CodeEditor, parent=None):
        super().__init__(parent)
        self.code_editor = code_editor
        self.current_matches: List[SearchMatch] = []
        self.current_match_index = -1
        self.all_matches: Dict[str, List[SearchMatch]] = {}  # 按搜索词分组
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 搜索工具栏
        search_layout = QHBoxLayout()
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("在文件中搜索...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input, 1)
        
        # 匹配选项
        self.case_check = QCheckBox("大小写")
        self.case_check.setFixedWidth(70)
        search_layout.addWidget(self.case_check)
        
        self.whole_word_check = QCheckBox("全词")
        self.whole_word_check.setFixedWidth(50)
        search_layout.addWidget(self.whole_word_check)
        
        self.regex_check = QCheckBox("正则")
        self.regex_check.setFixedWidth(50)
        search_layout.addWidget(self.regex_check)
        
        # 导航按钮
        self.prev_button = QToolButton()
        self.prev_button.setText("↑ 上一个")
        self.prev_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.prev_button.clicked.connect(self._go_to_prev)
        search_layout.addWidget(self.prev_button)
        
        self.next_button = QToolButton()
        self.next_button.setText("下一个 ↓")
        self.next_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.next_button.clicked.connect(self._go_to_next)
        search_layout.addWidget(self.next_button)
        
        layout.addLayout(search_layout)
        
        # 结果计数标签
        self.result_label = QLabel("0 个匹配")
        self.result_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.result_label)
        
        # 结果显示区域（带滚动条）
        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.results_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.results_scroll.setMaximumHeight(200)  # 最大高度 200px
        
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(2)
        
        self.results_scroll.setWidget(self.results_container)
        layout.addWidget(self.results_scroll)
    
    def _on_search(self):
        """执行搜索"""
        query = self.search_input.text().strip()
        if not query:
            return
        
        self.perform_search(query)
    
    def perform_search(self, query: str):
        """执行搜索并显示结果"""
        # 清除旧高亮
        self.code_editor.clear_highlights()
        
        # 获取搜索选项
        case_sensitive = self.case_check.isChecked()
        whole_word = self.whole_word_check.isChecked()
        use_regex = self.regex_check.isChecked()
        
        # 执行搜索
        self.current_matches = self._find_matches(
            query, case_sensitive, whole_word, use_regex
        )
        
        # 保存到新组
        if query not in self.all_matches:
            self.all_matches[query] = []
        self.all_matches[query] = self.current_matches
        
        # 更新标签
        self.result_label.setText(f"{len(self.current_matches)} 个匹配")
        
        # 高亮显示
        self.code_editor.highlight_text(
            query,
            QColor(255, 255, 0),
            case_sensitive,
            whole_word,
            use_regex
        )
        
        # 显示结果列表
        self._update_results_display(query)
        
        # 滚动到顶部，确保新结果可见
        self.results_scroll.verticalScrollBar().setValue(0)
        
        # 跳转到第一个匹配
        if self.current_matches:
            self.current_match_index = 0
            self._goto_match(0)
    
    def _find_matches(self, query: str, case_sensitive: bool,
                     whole_word: bool, use_regex: bool) -> List[SearchMatch]:
        """查找所有匹配"""
        matches = []
        document_text = self.code_editor.toPlainText()
        lines = document_text.split('\n')
        
        current_line = 0
        for line in lines:
            current_line += 1
            
            try:
                if use_regex:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    pattern = re.compile(query, flags)
                    
                    for match in pattern.finditer(line):
                        matches.append(SearchMatch(
                            current_line,
                            line,
                            match.start(),
                            match.end()
                        ))
                else:
                    search_line = line if case_sensitive else line.lower()
                    search_query = query if case_sensitive else query.lower()
                    
                    start = 0
                    while True:
                        pos = search_line.find(search_query, start)
                        if pos == -1:
                            break
                        
                        # 检查完整单词
                        if whole_word:
                            # 检查前一个字符
                            if pos > 0:
                                prev_char = search_line[pos-1]
                                if prev_char.isalnum() or prev_char == '_':
                                    start = pos + 1
                                    continue
                            
                            # 检查后一个字符
                            end_pos = pos + len(search_query)
                            if end_pos < len(search_line):
                                next_char = search_line[end_pos]
                                if next_char.isalnum() or next_char == '_':
                                    start = pos + 1
                                    continue
                        
                        matches.append(SearchMatch(
                            current_line,
                            line,
                            pos,
                            pos + len(query)
                        ))
                        
                        start = pos + 1
            
            except Exception as e:
                print(f"搜索错误：{e}")
        
        return matches
    
    def _update_results_display(self, current_query: str):
        """更新结果显示"""
        # 清空旧的结果
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 为每个搜索词组创建可折叠面板（按搜索顺序显示）
        for query, matches in self.all_matches.items():
            if not matches:
                continue
            
            # 创建折叠按钮
            is_current = (query == current_query)
            collapse_btn = QPushButton(f"📄 {query} ({len(matches)} 个匹配)")
            collapse_btn.setCheckable(True)
            collapse_btn.setChecked(True)  # 默认展开
            collapse_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f0f0f0;
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 5px;
                    text-align: left;
                    font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #e0e0e0;
                    border-color: #999;
                }
                QPushButton:hover {
                    background-color: #fffacd;
                }
            """)
            self.results_layout.addWidget(collapse_btn)
            
            # 创建结果容器
            matches_widget = QWidget()
            matches_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            matches_layout = QVBoxLayout(matches_widget)
            matches_layout.setContentsMargins(10, 2, 2, 2)
            matches_layout.setSpacing(1)
            
            # 添加匹配项
            for i, match in enumerate(matches):
                # 高亮匹配文本中的关键词
                highlighted_text = self._highlight_keyword_in_line(
                    match.line_text, query, is_current
                )
                
                match_btn = QPushButton(f"行 {match.line_number}: {highlighted_text}")
                match_btn.setStyleSheet("""
                    QPushButton {
                        background-color: white;
                        border: 1px solid #ddd;
                        border-radius: 2px;
                        padding: 3px;
                        text-align: left;
                        font-family: Consolas;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #fffacd;
                        border-color: #ffd700;
                    }
                """)
                match_btn.clicked.connect(
                    lambda checked, line=match.line_number: self._on_match_clicked(line)
                )
                matches_layout.addWidget(match_btn)
            
            self.results_layout.addWidget(matches_widget)
            
            # 连接折叠功能
            collapse_btn.toggled.connect(
                lambda checked, w=matches_widget: w.setVisible(checked)
            )
        
        # 添加弹性空间，确保内容贴顶显示
        self.results_layout.addStretch()
    
    def _highlight_keyword_in_line(self, line_text: str, keyword: str, is_current: bool) -> str:
        """在行文本中高亮关键词"""
        import re
        try:
            # 不区分大小写替换
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            # 使用黄色背景高亮
            highlighted = pattern.sub(
                f'<span style="background-color: yellow; color: black;">\\g<0></span>',
                line_text
            )
            return highlighted[:100]  # 限制长度
        except:
            return line_text[:100]
    
    def _on_match_clicked(self, line_number: int):
        """点击匹配项"""
        self._goto_line(line_number)
        self.match_selected.emit(line_number)
    
    def _go_to_prev(self):
        """上一个匹配"""
        if not self.current_matches:
            return
        
        # 确保按钮不可检查
        self.prev_button.setChecked(False)
        
        self.current_match_index = (self.current_match_index - 1) % len(self.current_matches)
        self._goto_match(self.current_match_index)
        self._update_match_display()
    
    def _go_to_next(self):
        """下一个匹配"""
        if not self.current_matches:
            return
        
        # 确保按钮不可检查
        self.next_button.setChecked(False)
        
        self.current_match_index = (self.current_match_index + 1) % len(self.current_matches)
        self._goto_match(self.current_match_index)
        self._update_match_display()
    
    def _update_match_display(self):
        """更新匹配显示"""
        if self.current_matches:
            self.result_label.setText(
                f"{self.current_match_index + 1}/{len(self.current_matches)} 个匹配"
            )
    
    def _goto_match(self, index: int):
        """跳转到指定匹配"""
        if index < 0 or index >= len(self.current_matches):
            return
        
        match = self.current_matches[index]
        self._goto_line(match.line_number)
    
    def _goto_line(self, line_number: int):
        """跳转到指定行"""
        cursor = self.code_editor.textCursor()
        block = self.code_editor.document().findBlockByNumber(line_number - 1)
        
        if block.isValid():
            # 设置光标位置
            cursor.setPosition(block.position())
            self.code_editor.setTextCursor(cursor)
            
            # 确保该行可见（滚动到视图中央）
            self.code_editor.centerCursor()
            
            # 高亮当前行
            self._highlight_current_line(cursor)
    
    def _highlight_current_line(self, cursor: QTextCursor):
        """高亮当前行"""
        # 清除旧的行高亮
        extra_selections = []
        
        # 添加新的行高亮（淡黄色背景）
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(255, 250, 205))  # LemonChiffon
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = cursor
        extra_selections.append(selection)
        
        # 保留关键词高亮（通过检查颜色 RGB 值）
        existing = self.code_editor.extraSelections()
        for sel in existing:
            bg_color = sel.format.background().color()
            # 检查是否为黄色高亮（RGB 值接近 255, 255, 0）
            if bg_color.red() == 255 and bg_color.green() == 255 and bg_color.blue() == 0:
                extra_selections.append(sel)
        
        self.code_editor.setExtraSelections(extra_selections)
    
    def clear(self):
        """清空搜索"""
        self.search_input.clear()
        self.current_matches = []
        self.all_matches = {}
        self.code_editor.clear_highlights()
        self.result_label.setText("0 个匹配")
        
        # 清空结果显示
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class EnhancedPreviewPanel(QWidget):
    """增强型预览面板（上下结构）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建可调节的分割器
        splitter = QSplitter(Qt.Vertical)
        
        # 上部分：代码编辑器
        self.code_editor = CodeEditor()
        self.code_editor.setReadOnly(True)
        splitter.addWidget(self.code_editor)
        
        # 下部分：搜索面板
        self.search_panel = FileSearchPanel(self.code_editor)
        splitter.addWidget(self.search_panel)
        
        # 设置初始比例（上 70%，下 30%）
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        
        layout.addWidget(splitter)
    
    def set_content(self, content: str):
        """设置内容"""
        self.code_editor.setPlainText(content)
        self.search_panel.clear()
    
    def search_in_file(self, query: str):
        """在文件中搜索"""
        self.search_panel.search_input.setText(query)
        self.search_panel.perform_search(query)
    
    def clear(self):
        """清空内容"""
        self.code_editor.clear()
        self.search_panel.clear()
