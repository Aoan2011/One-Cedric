"""只读支持 ~/.agents/skills 第三方技能。

`~/.agents/skills/<name>/SKILL.md` 是其它 agent 运行时安装的文档型技能
（YAML frontmatter + Markdown 指引）。本模块只做发现与读取，绝不写入，
把每个技能暴露给 One Cedric 的模型：先枚举，再按需读取全文，让模型按
技能指引执行（例如调用技能所需的 CLI 工具）。
"""
from __future__ import annotations

import re
from pathlib import Path

AGENTS_HOME = Path.home() / ".agents"
SKILLS_DIR = AGENTS_HOME / "skills"
_FRONTMETER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _parse_frontmatter(text: str) -> dict:
    m = _FRONTMETER_RE.match(text)
    meta: dict = {}
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip().strip("\"'")
        if key in ("name", "description", "version"):
            meta[key] = value
    return meta


def list_agents_skills() -> list[dict]:
    """扫描 ~/.agents/skills/*/SKILL.md，返回技能元信息列表（只读）。"""
    if not SKILLS_DIR.is_dir():
        return []
    skills = []
    try:
        entries = sorted(SKILLS_DIR.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            text = skill_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta = _parse_frontmatter(text)
        name = (meta.get("name") or entry.name).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            name = entry.name
        skills.append({
            "name": name,
            "description": meta.get("description", ""),
            "version": meta.get("version", ""),
            "path": str(skill_file),
        })
    return skills


def read_agents_skill(name: str) -> tuple[str | None, str]:
    """读取指定技能的 SKILL.md 全文。

    返回 (content, error)。content 为 None 表示失败（未找到 / 读取错误）。
    """
    if not isinstance(name, str) or not name.strip():
        return None, "请提供技能名（name）"
    target = name.strip()
    skills = list_agents_skills()
    hit = next((s for s in skills if s["name"] == target), None)
    if hit is None:
        names = "、".join(s["name"] for s in skills) or "（无）"
        return None, f"未找到技能 '{target}'（可用: {names}）"
    try:
        content = Path(hit["path"]).read_text(
            encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, f"读取失败: {exc}"
    return content, ""


def agents_skill_tool(args: dict) -> str:
    """agents_skill 工具实现（只读）。

    - 不带 name / list=true：枚举技能名与描述
    - 带 name：返回该技能 SKILL.md 全文
    """
    if not isinstance(args, dict):
        args = {}
    do_list = bool(args.get("list", False))
    name = str(args.get("name", "") or "").strip()
    if do_list or not name:
        skills = list_agents_skills()
        if not skills:
            return ("~/.agents/skills 中没有找到技能。\n"
                    "技能安装方式由对应 agent 运行时提供（如 "
                    "`npx skills add <url>`）。")
        lines = ["~/.agents/skills 第三方技能（只读，共 %d 个）：" % len(skills)]
        for s in skills:
            desc = (s["description"] or "（无描述）")[:120]
            ver = (" v" + s["version"]) if s["version"] else ""
            lines.append(f"- {s['name']}{ver}：{desc}")
        lines.append("\n读取某个技能请调用 agents_skill 并传入 name。")
        return "\n".join(lines)
    content, err = read_agents_skill(name)
    if content is None:
        return f"ERROR: {err}"
    return content
