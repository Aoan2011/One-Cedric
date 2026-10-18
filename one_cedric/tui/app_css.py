"""Shell C 的样式表入口。

真正的样式写在 ``theme.tcss``（纯 ASCII —— Textual 0.43 在 Windows 用
cp936 读样式，非 ASCII 会直接抛 StylesheetError；``tests/test_tui.py``
有一条专门遍历 ``one_cedric/tui/`` 下所有 .tcss/.css 的断言）。

变量值（``$accent`` 等）必须与 ``theme.py`` 的 COLORS 一致，
``test_theme_colors_match_css_variables`` 会逐个核对。
"""

from pathlib import Path

_CSS_PATH = Path(__file__).with_name("theme.tcss")

#: App.CSS 读这里；同步作为「样式表文件必须纯 ASCII」的测试对象。
CSS = _CSS_PATH.read_text(encoding="ascii")
