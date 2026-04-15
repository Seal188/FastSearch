"""
主程序入口
"""
import sys
import argparse
import logging
from pathlib import Path

from config import LOG_LEVEL, LOG_FORMAT
from indexer import IndexEngine
from parser import extract_text
from monitor import FileMonitor

logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("fastsearch.log", encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


def cmd_index(args):
    """命令行索引命令"""
    engine = IndexEngine()
    engine.create_index(force=args.force)
    
    directories = [Path(p) for p in args.directories]
    
    print(f"开始索引 {len(directories)} 个目录...")
    
    total_files = 0
    indexed_count = 0
    
    for directory in directories:
        print(f"\n索引目录：{directory}")
        
        for file_path in directory.rglob('*'):
            if not file_path.is_file():
                continue
            
            if file_path.suffix.lower() not in engine.supported_extensions:
                continue
            
            total_files += 1
            
            if not engine.needs_reindex(file_path):
                continue
            
            print(f"  [{indexed_count}] {file_path.name}")
            
            content = extract_text(file_path)
            if content:
                engine.add_document(file_path, content)
                indexed_count += 1
    
    stats = engine.get_stats()
    print(f"\n索引完成!")
    print(f"  已索引：{stats['indexed_files']} 个文件")
    print(f"  失败：{stats['failed_files']} 个文件")
    
    engine.close()


def cmd_search(args):
    """命令行搜索命令"""
    engine = IndexEngine()
    engine.create_index()
    
    query = ' '.join(args.query)
    print(f"搜索：{query}\n")
    
    results = engine.search(query, limit=args.limit)
    
    if not results:
        print("未找到结果")
        return
    
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['filename']}")
        print(f"   路径：{result['path']}")
        print(f"   大小：{result['size']} bytes")
        print()
    
    engine.close()


def cmd_status(args):
    """查看索引状态"""
    engine = IndexEngine()
    engine.create_index()
    
    stats = engine.get_stats()
    
    print("索引状态:")
    print(f"  已索引文件：{stats['indexed_files']}")
    print(f"  失败文件：{stats['failed_files']}")
    print(f"  总大小：{stats['total_size'] / 1024 / 1024:.2f} MB")
    
    engine.close()


def cmd_gui(args):
    """启动 GUI 界面"""
    from gui import main as gui_main
    gui_main()


def main():
    parser = argparse.ArgumentParser(
        description="FastSearch - 轻量级全文搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  fastsearch index C:\\Documents D:\\Projects
  fastsearch search 关键词
  fastsearch status
  fastsearch gui
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    index_parser = subparsers.add_parser('index', help='创建或更新索引')
    index_parser.add_argument('directories', nargs='+', help='要索引的目录')
    index_parser.add_argument('--force', action='store_true', help='强制重建索引')
    index_parser.set_defaults(func=cmd_index)
    
    search_parser = subparsers.add_parser('search', help='搜索文件')
    search_parser.add_argument('query', nargs='+', help='搜索关键词')
    search_parser.add_argument('--limit', type=int, default=50, help='最大结果数')
    search_parser.set_defaults(func=cmd_search)
    
    status_parser = subparsers.add_parser('status', help='查看索引状态')
    status_parser.set_defaults(func=cmd_status)
    
    gui_parser = subparsers.add_parser('gui', help='启动 GUI 界面')
    gui_parser.set_defaults(func=cmd_gui)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return
    
    args.func(args)


if __name__ == '__main__':
    main()
