# 🔍 FastSearch - 书签与全文搜索工具

![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-yellow.svg)

🚀 一款轻量级的本地书签与全文搜索工具，基于 Whoosh 构建，支持快速、准确的文件检索。

## ✨ 功能特点

🔍 **高速搜索** - 采用倒排索引技术，搜索响应时间 < 100ms  
📁 **书签管理** - 智能管理浏览器书签，快速定位  
📄 **多格式支持** - 支持 Office、PDF、TXT、HTML 等多种文件格式  
💡 **智能预览** - 行号显示、关键词高亮、文件内搜索  
🖥️ **友好界面** - 基于 PyQt5 的现代化 GUI 设计  
⚡ **增量索引** - 智能检测文件变化，只索引新增或修改的文件  
📦 **轻量高效** - 后台常驻内存占用 < 200MB  
🛡️ **安全可靠** - 仅索引用户指定的目录，尊重隐私

## 🚀 快速开始

### 📥 安装

1. **克隆项目**
```bash
git clone https://github.com/Seal188/FastSearch.git
cd FastSearch
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

### 📦 可选依赖（OCR功能）

如果你需要 OCR 文字识别功能，需要额外安装：

```bash
pip install pytesseract Pillow
```

**注意：** 使用 OCR 功能前，还需要安装 Tesseract OCR 引擎：
1. 下载 Tesseract OCR：https://github.com/UB-Mannheim/tesseract/wiki
2. 安装后在系统环境变量中添加 `tesseract.exe` 的路径
3. 或在程序设置中指定 Tesseract 的安装路径

### 🎯 运行

```bash
python run.py
```

### 📦 打包成 EXE（可选）

```bash
pyinstaller fastsearch.spec
```

## 📂 项目结构

```
FastSearch/
├── main.py                 # 主程序入口
├── gui.py                  # GUI 主界面
├── indexer.py              # 索引引擎（Whoosh）
├── parser.py               # 文档解析器
├── bookmark_manager.py     # 书签管理器
├── config_manager.py       # 配置管理器
├── history_manager.py      # 历史记录管理
├── enhanced_preview.py     # 增强预览组件
├── monitor.py              # 文件监控器
├── config.py               # 配置文件
├── run.py                  # 快速启动脚本
├── requirements.txt        # Python 依赖列表
└── icon.ico                # 程序图标
```

## 💡 核心功能

### 1. 搜索功能 🔍
- ✅ 精准搜索、模糊搜索、正则表达式
- ✅ 多关键词组合搜索
- ✅ 指定目录和文件类型过滤

### 2. 文件预览 📄
- ✅ 智能预览面板
- ✅ 关键词高亮显示
- ✅ 行号显示与快速定位

### 3. 书签管理 ⭐
- ✅ 书签添加、删除、分组
- ✅ 快速访问常用文件
- ✅ 与浏览器书签同步

### 4. 历史记录 📜
- ✅ 自动记录浏览历史
- ✅ 快速回溯访问记录
- ✅ 智能排序和搜索

## 🛠️ 技术栈

- **语言**: Python 3.7+
- **GUI**: PyQt5
- **搜索引擎**: Whoosh
- **文件监控**: Watchdog
- **文档解析**: python-docx, openpyxl, pdfplumber

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

如果你发现了 bug 或者有新功能建议，请：
1. 提交 [Issue](https://github.com/Seal188/FastSearch/issues)
2. Fork 本项目
3. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
4. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
5. 推送到分支 (`git push origin feature/AmazingFeature`)
6. 创建 Pull Request

## 📝 许可证

本项目仅供学习和交流使用，未经授权不得用于商业用途。

---

⭐ 如果这个项目对你有帮助，请给我一个 Star！
