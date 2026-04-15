## 🌐 Language

- [中文](README.md)
- [English](README_en.md)

---

# 🔍 FastSearch - Bookmark & Full-Text Search Tool

![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-yellow.svg)

🚀 A lightweight local bookmark and full-text search tool, built on Whoosh, supporting fast and accurate file retrieval.

## ✨ Features

🔍 **High-Speed Search** - Inverted index technology, search response time < 100ms  
📁 **Bookmark Management** - Intelligent browser bookmark management for quick locating  
📄 **Multi-Format Support** - Supports Office, PDF, TXT, HTML and various file formats  
💡 **Smart Preview** - Line numbers, keyword highlighting, in-file search  
🖥️ **Friendly Interface** - Modern GUI design based on PyQt5  
⚡ **Incremental Indexing** - Smart file change detection, only indexes new or modified files  
📦 **Lightweight & Efficient** - Background resident memory usage < 200MB  
🛡️ **Secure & Reliable** - Only indexes user-specified directories, respects privacy

## 🚀 Quick Start

### 📥 Installation

1. **Clone the project**
```bash
git clone https://github.com/Seal188/FastSearch.git
cd FastSearch
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

### 📦 Optional Dependencies (OCR Feature)

If you need OCR text recognition, install additional packages:

```bash
pip install pytesseract Pillow
```

**Note:** Before using OCR functionality, you also need to install the Tesseract OCR engine:
1. Download Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
2. Add the `tesseract.exe` path to your system environment variables after installation
3. Or specify the Tesseract installation path in the program settings

### 🎯 Run

```bash
python run.py
```

### 📦 Build EXE (Optional)

```bash
pyinstaller fastsearch.spec
```

## 📂 Project Structure

```
FastSearch/
├── main.py                 # Main program entry
├── gui.py                  # GUI main interface
├── indexer.py              # Search engine (Whoosh)
├── parser.py               # Document parser
├── bookmark_manager.py     # Bookmark manager
├── config_manager.py       # Configuration manager
├── history_manager.py      # History manager
├── enhanced_preview.py     # Enhanced preview component
├── monitor.py              # File monitor
├── config.py               # Configuration file
├── run.py                  # Quick start script
├── requirements.txt        # Python dependencies
└── icon.ico                # Program icon
```

## 💡 Core Features

### 1. Search Functionality 🔍
- ✅ Precise search, fuzzy search, regular expressions
- ✅ Multi-keyword combined search
- ✅ Directory and file type filtering

### 2. File Preview 📄
- ✅ Smart preview panel
- ✅ Keyword highlighting
- ✅ Line numbers and quick positioning

### 3. Bookmark Management ⭐
- ✅ Add, delete, and group bookmarks
- ✅ Quick access to frequently used files
- ✅ Sync with browser bookmarks

### 4. History Records 📜
- ✅ Automatic browsing history recording
- ✅ Quick history retrieval
- ✅ Smart sorting and searching

## 🛠️ Tech Stack

- **Language**: Python 3.7+
- **GUI**: PyQt5
- **Search Engine**: Whoosh
- **File Monitoring**: Watchdog
- **Document Parsing**: python-docx, openpyxl, pdfplumber

## 🤝 Contributing

Contributions, issues and feature requests are welcome!

If you find a bug or have a feature suggestion:
1. Submit an [Issue](https://github.com/Seal188/FastSearch/issues)
2. Fork the project
3. Create your feature branch (`git checkout -b feature/AmazingFeature`)
4. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

## 📝 License

This project is for learning and communication purposes only. Commercial use without authorization is not allowed.

---

⭐ If you find this project helpful, please give it a Star!
