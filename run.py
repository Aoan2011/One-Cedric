"""便捷启动脚本：python run.py [args]。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# 本地依赖库（computer use 等可选工具）：.pylibs 由
#   pip install --target .pylibs <packages>
# 安装，避免依赖系统 Python 的 site-packages 写权限。
_libs = Path(__file__).parent / ".pylibs"
if _libs.is_dir():
    sys.path.insert(0, str(_libs))

from one_cedric.cli import main

if __name__ == "__main__":
    main()