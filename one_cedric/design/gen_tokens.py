"""设计令牌生成器（M1）。

唯一来源是 ``gateway/webui/design/tokens.json``；这个脚本把它编译成
``design/tokens.css``（CSS 自定义属性 + 明暗两套）。

为什么要有生成器：此前的教训是同一批颜色/圆角/动效在 style.css、
polish.css、tokens.css 里各写一遍，最后 61% 的选择器互相覆盖、15 处
``!important`` 互相压制。令牌只允许有一个来源。

跑法::

    python -m one_cedric.design.gen_tokens          # 写文件
    python -m one_cedric.design.gen_tokens --check  # CI：只校验是否漂移
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEBUI = HERE.parent / "gateway" / "webui"
SOURCE = WEBUI / "design" / "tokens.json"
OUTPUT = WEBUI / "design" / "tokens.css"

#: 令牌组 -> CSS 变量前缀。顺序决定输出顺序（保持 diff 稳定）。
GROUPS = {
    "color": "--c",
    "space": "--sp",
    "radius": "--radius",
    "font": "--font",
    "text": "--fs",
    "motion": "--dur",
    "elev": "--elev",
    "z": "--z",
    "layout": "--layout",
    "breakpoint": "--bp",
}

HEADER = """/* 由 one_cedric/design/gen_tokens.py 从 tokens.json 生成 —— 请勿手改。
 *
 * 重新生成：python -m one_cedric.design.gen_tokens
 * 校验漂移：python -m one_cedric.design.gen_tokens --check
 */
"""

#: 少数令牌不走「前缀-键名」的规则，单独点名（历史命名要保持兼容）。
#: ``scale-*`` 是跟随根字号的阶梯（Claude Code / Codex 那类密度），
#: 根字号一动整套 UI 跟着缩放；``base`` 单独给根字号用。
RENAME = {
    "motion": {"dur": "--dur", "dur-fast": "--dur-fast",
               "dur-slow": "--dur-slow", "ease": "--ease",
               "ease-out": "--ease-out"},
    "text": {"xs": "--fs-xs", "sm": "--fs-sm", "md": "--fs-md",
             "lg": "--fs-lg", "xl": "--fs-xl", "2xl": "--fs-2xl",
             "3xl": "--fs-3xl", "base": "--fs-base",
             "scale-xs": "--fs-scale-xs", "scale-sm": "--fs-scale-sm",
             "scale-md": "--fs-scale-md", "scale-lg": "--fs-scale-lg",
             "scale-xl": "--fs-scale-xl", "scale-2xl": "--fs-scale-2xl",
             "scale-3xl": "--fs-scale-3xl", "scale-4xl": "--fs-scale-4xl"},
}


def _subset(theme: str) -> dict[str, str]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    pal = data["color"][theme]
    return {f"--c-{k}": v for k, v in pal.items()}


def render() -> str:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    out = [HEADER, ":root {"]
    for group, prefix in GROUPS.items():
        if group == "color":
            continue
        values = data.get(group) or {}
        if not values:
            continue
        out.append(f"  /* {group} */")
        rename = RENAME.get(group, {})
        for key, value in values.items():
            if key.startswith("$"):
                continue
            name = rename.get(key, f"{prefix}-{key}")
            if group == "text" and key == "base":
                # 根字号：缩放阶梯都以它为单位，必须落在 <html> 上。
                out.append("}")
                out.append("")
                out.append(":root {")
            out.append(f"  {name}: {value};")
    out.append("}")

    # 默认暗色 + 亮色覆盖：两套都只来自同一个 JSON
    for theme, selector in (("dark", ":root"), ("light", ".theme-light")):
        block = _subset(theme)
        out.append("")
        out.append(f"{selector} {{")
        for name, value in block.items():
            out.append(f"  {name}: {value};")
        out.append("  color-scheme: light;" if theme == "light"
                   else "  color-scheme: dark;")
        out.append("}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    css = render()
    if "--check" in argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != css:
            print("design/tokens.css 与 tokens.json 不一致；"
                  "跑 python -m one_cedric.design.gen_tokens 重新生成",
                  file=sys.stderr)
            return 1
        print("tokens.css 与 tokens.json 一致")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(css, encoding="utf-8")
    print(f"已写入 {OUTPUT.relative_to(WEBUI.parent.parent)}"
          f"（{len(css)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
