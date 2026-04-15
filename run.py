"""
快速启动脚本
"""
import sys
import subprocess
import os

def check_dependencies():
    """检查依赖是否已安装"""
    required_packages = [
        'PyQt5',
        'whoosh',
        'watchdog',
        'python-docx',
        'openpyxl',
        'pdfplumber',
        'chardet',
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        print("缺少以下依赖包:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\n正在自动安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("依赖安装完成！")

def main():
    check_dependencies()
    
    from gui import main as gui_main
    gui_main()

if __name__ == '__main__':
    main()
