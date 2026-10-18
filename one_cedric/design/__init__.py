"""设计系统：令牌唯一来源 + 生成器。

用 ``python -m one_cedric.design.gen_tokens`` 生成 CSS。
（刻意不在包初始化时 import 子模块：那会让 ``python -m`` 先加载一次，
再执行一次，触发 runpy 的 RuntimeWarning。）
"""

__all__: list[str] = []
