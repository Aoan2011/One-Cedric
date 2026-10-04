"""便捷启动脚本：python run.py [args]。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from one_cedric.cli import main

if __name__ == "__main__":
    main()