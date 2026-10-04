"""全局常量、rich 主题、prompts。"""
from __future__ import annotations

import os

from rich.theme import Theme

BETA_VERSION = "Beta 17"

BRAND = "#d97757"
ACCENT = "#4ec9b0"
USER_C = "#4a9eff"
TOOL_C = "#7dcfff"
WARN_C = "#e0af68"
PLAN_C = "#bb9af7"
OK_C = "#9ece6a"
ERR_C = "#f7768e"
DIM_C = "#565f89"

THEME = Theme({
    "brand":     f"bold {BRAND}",
    "brand.dim": f"{BRAND}",
    "accent":    ACCENT,
    "user":      f"bold {USER_C}",
    "tool":      TOOL_C,
    "tool.name": f"bold {TOOL_C}",
    "ok":        f"bold {OK_C}",
    "warn":      f"bold {WARN_C}",
    "err":       f"bold {ERR_C}",
    "path":      ACCENT,
    "dim":       DIM_C,
    "plan":      f"bold {PLAN_C}",
    "meta":      DIM_C,
    "diff.add":  OK_C,
    "diff.del":  ERR_C,
    "diff.ctx":  DIM_C,
    "diff.hunk": "#7aa2f7",
})

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DEFAULT_API_KEY = (
    os.environ.get("ONE_CEDRIC_API_KEY", "")
    or os.environ.get("OPENAI_API_KEY", "")
)

REASONING_MODEL_KEYWORDS = (
    "r1", "qwq", "thinking", "reasoning", "o1", "o3",
    "deepseek-v4", "deepseek-reasoner", "gpt-oss",
)

DEEPSEEK_BUGGY_MODEL_KEYWORDS = (
    "deepseek-v4.1-flash", "deepseek-v4.1", "deepseek-v4-pro",
)

THINK_LEVELS = ("minimal", "low", "medium", "max", "xhigh", "ultra")

THINK_LEVEL_DESC = {
    "minimal": "直接回答，不展示推理",
    "low":     "简短推理",
    "medium":  "标准推理（默认）",
    "max":     "深入推理",
    "xhigh":   "深度推理 + 多角度验证",
    "ultra":   "穷尽推理 + 正反论证 + 边界分析",
}

THINK_TO_REASONING_EFFORT = {
    "minimal": "minimal",
    "low":     "low",
    "medium":  "medium",
    "max":     "high",
    "xhigh":   "high",
    "ultra":   "high",
}

THINK_TO_BUDGET = {
    "minimal": 512,
    "low":     2048,
    "medium":  8192,
    "max":     16384,
    "xhigh":   32768,
    "ultra":   65536,
}

THINK_PROMPT_HINTS = {
    "minimal": "\n\n[思考模式: minimal] 直接给出答案，不要展示推理过程。",
    "low":     "\n\n[思考模式: low] 简要推理后给出答案。",
    "medium":  "",
    "max":     "\n\n[思考模式: max] 深入分析问题，考虑多种可能性后再回答。",
    "xhigh":   ("\n\n[思考模式: xhigh] 深度推理，从多个角度验证结论，"
                "主动指出潜在风险与替代方案。"),
    "ultra":   ("\n\n[思考模式: ultra] 穷尽式推理：列出所有可能方案，"
                "逐一评估优缺点，正反论证，分析边界条件与失败场景，"
                "最后给出最优建议。必要时明确说明假设与不确定性。"),
}

DEFAULT_THINK_LEVEL = "medium"

MAX_BYTES = 200_000
MAX_LINES = 2_000
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_FILE_SIZE = 500_000
MAX_WRITE_BYTES = 1_000_000
DIFF_CONTEXT = 3

MAX_GLOB_RESULTS = 200
MAX_WEB_BYTES = 200_000
WEB_TIMEOUT = 20

MAX_HTTP_RESP_BYTES = 200_000
MAX_HTTP_BODY_BYTES = 100_000
HTTP_DEFAULT_TIMEOUT = 20

MAX_SEARCH_QUERY_LEN = 200
MAX_JSON_RESULTS = 100

MAX_CSV_ROWS = 200
MAX_SQLITE_ROWS = 200
MAX_DIFF_LINES = 2000

DEFAULT_SHELL_TIMEOUT = 30
SHELL_OUTPUT_LIMIT = 8000

ARCHIVE_EXTENSIONS = (
    ".zip", ".tar", ".tar.gz", ".tgz",
    ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
)

GIT_READ_SUBCOMMANDS = {
    "status", "diff", "log", "show", "branch", "blame",
    "rev-parse", "ls-files", "describe", "shortlog",
    "config", "remote", "stash",
}

GIT_WRITE_SUBCOMMANDS = {
    "add", "commit", "checkout", "switch", "restore",
    "stash", "tag", "reset", "merge", "rebase", "cherry-pick",
    "revert", "init",
}

GIT_FORBIDDEN_FLAGS = {
    "--hard", "-f", "--force", "-D", "--delete", "--mixed",
}

DOCKER_READ_SUBCOMMANDS = {
    "ps", "images", "logs", "inspect", "stats", "version",
    "info", "port", "top", "diff", "history", "events",
}

DOCKER_WRITE_SUBCOMMANDS = {
    "run", "exec", "stop", "start", "restart", "rm", "rmi",
    "pull", "build", "push", "tag", "kill", "pause", "unpause",
    "create", "cp", "commit",
}

DOCKER_FORBIDDEN = {
    "system", "swarm", "node", "service", "secret", "context",
    "plugin", "trust", "volume",
}

ENV_SENSITIVE_KEYWORDS = {
    "token", "key", "secret", "password", "passwd", "pwd",
    "auth", "credential", "session", "cookie", "signature",
    "private", "apikey", "api_key",
}

SHELL_WHITELIST: list[list[str]] = [
    ["pytest"],
    ["python", "-m", "pytest"],
    ["python", "-m", "unittest"],
    ["python", "-m", "ruff"],
    ["python", "-m", "black"],
    ["python", "-m", "mypy"],
    ["ruff"], ["ruff", "check"], ["ruff", "format"],
    ["black"], ["mypy"], ["flake8"], ["pylint"],
    ["npm", "test"], ["npm", "run"],
    ["pnpm", "test"], ["pnpm", "run"],
    ["yarn", "test"], ["yarn", "run"],
    ["node", "--version"],
    ["go", "test"], ["go", "build"], ["go", "vet"],
    ["cargo", "test"], ["cargo", "build"], ["cargo", "check"], ["cargo", "clippy"],
    ["git", "status"], ["git", "diff"], ["git", "log"],
    ["git", "branch"], ["git", "show"], ["git", "rev-parse"],
    ["dir"], ["type"], ["where"], ["whoami"], ["hostname"],
    ["python", "--version"], ["pip", "list"],
]

SHELL_KNOWN_COMMANDS = {
    "python", "python3", "py", "node", "npm", "npx", "pnpm", "yarn", "bun",
    "deno", "go", "cargo", "rustc", "java", "javac", "mvn", "gradle",
    "dotnet", "ruby", "php", "perl", "lua",
    "cat", "head", "tail", "less", "more", "wc", "nl",
    "ls", "dir", "tree", "find", "grep", "awk", "sed",
    "file", "stat", "du", "df", "readlink", "realpath",
    "echo", "printf", "sort", "uniq", "cut", "tr", "tee", "xargs",
    "curl", "wget", "ping", "tracert", "traceroute", "nslookup", "dig",
    "ps", "top", "htop", "netstat", "ss", "ipconfig", "ifconfig",
    "uname", "systeminfo", "ver", "date", "whoami", "hostname",
    "tar", "zip", "unzip", "7z", "gzip", "gunzip", "bzip2",
    "nano", "vi", "vim", "code", "notepad",
    "git", "svn", "hg",
    "pip", "pip3", "conda", "poetry", "uv",
    "docker", "docker-compose", "podman", "kubectl",
    "which", "whereis", "type", "man", "help", "true", "false", "sleep",
}

SHELL_BLACKLIST = {
    "format", "diskpart", "chkdsk", "sfc", "bcdedit",
    "mkfs", "fdisk", "parted", "dd", "shred",
    "shutdown", "reboot", "halt", "poweroff", "init",
    "sudo", "su", "runas", "takeown", "icacls", "chmod", "chown", "chattr",
    "useradd", "userdel", "usermod", "passwd", "net", "reg",
    "rm", "del", "rd", "rmdir", "erase",
}

SHELL_DANGEROUS_PATTERNS = [
    "rm -rf /", "rm -fr /", "rm -rf /*",
    "del /f /s /q c:\\", "del /f /s /q c:/*",
    "rd /s /q c:\\", "format c:",
    ":(){ :|:& };:",
    "> /dev/sda", "dd if=/dev/zero",
    "chmod -R 777 /",
    "chown -R",
]

SHELL_FORBIDDEN_TOKENS = [";", "&&", "||", "|", "`", "$(", "${", ">", "<", "&"]

DEFAULT_ALLOW_ARBITRARY_SHELL = False

SESSION_DIRNAME = ".one-cedric"
SESSION_SUBDIR = "sessions"
PROJECTS_SUBDIR = "projects"
PROFILES_SUBDIR = "profiles"
CONFIG_FILENAME = "config.toml"

ACCESS_MODES = ("workspace", "workspacesafe", "workspaceyolo", "fullaccess")
DEFAULT_ACCESS_MODE = "workspace"

ACCESS_MODE_DESC = {
    "workspace":     "工作目录内可读写，写操作需确认",
    "workspacesafe": "工作目录内只读优先，任何写操作均需确认",
    "workspaceyolo": "工作目录内完全放开，写操作自动确认",
    "fullaccess":    "可访问任意路径，完全放开（危险）",
}

ACCESS_MODE_ALIASES = {
    "safe": "workspacesafe",
    "yolo": "workspaceyolo",
    "full": "fullaccess",
}

ACCESS_MODE_COLOR = {
    "workspace":     "dim",
    "workspacesafe": "ok",
    "workspaceyolo": "warn",
    "fullaccess":    "err",
}

DEFAULT_CONFIG: dict = {
    "default": {
        "model": DEFAULT_MODEL,
        "host": DEFAULT_HOST,
        "api_key": "",
        "temperature": 0.2,
        "auto_yes": False,
        "max_steps": 8,
        "compact_keep_turns": 4,
        "auto_compact_threshold": 0,
        "show_reasoning": True,
        "think_level": "medium",
        "enable_computer_use": False,
        "enable_vision": False,
        "allow_arbitrary_shell": False,
        "mode": "workspace",
        "language": "zh",
    },
    "bash": {
        "extra_prefixes": [],
        "extra_blacklist": [],
    },
    "gateway": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 2043,
        "token": "",
    },
    "amap": {
        "api_key": "",
    },
}

SYSTEM_PROMPT = r"""你是 One Cedric，一个可以操作本地文件的命令行助手。

## 工作流程

1. 收到任务后，先判断需要哪些信息。
2. 用户只是打招呼 / 闲聊 / 问概念时，不要调用任何工具，直接聊天回答。
3. 任何文件路径必须先确认存在。
4. 需要看文件内容 -> 调用 read_file。
5. 需要目录结构 -> list_files。
6. 需要找内容 -> search_in_files 或 grep_regex。
7. 修改文件前 -> 必须先 read_file 确认当前内容。
8. 完成修改后 -> 用 bash 跑测试/格式化验证。
9. 任务完成后 -> 用简体中文简短汇报。

## 工具选择优先级

### 文件
- 查看文件：read_file（支持多编码自动检测）
- 局部修改：edit_file（old_string 必须逐字符一致）
- 新建/整体重写：write_file
- 大范围多文件：apply_patch
- 找文件：glob
- 找内容：grep_regex

### 网络
- 需要基于内容回答 -> web_research
- 只想扫一遍有什么 -> web_search
- 已知确切 URL -> web_fetch
- 调用 API -> http_request
- 下载大文件 -> download（多线程 + 断点续传）
- 天气 -> weather（返回 wttr.in 原生 ASCII 图，不要自己总结）

### Python 执行
- 数据分析、画图表、算法验证 -> python_exec
- 图表自动保存到 .cedric_artifacts/
- 未在白名单的库会弹确认

### 系统
- 音量/亮度/主题/WLAN/蓝牙/打印机/电源/服务/进程 -> sysop
- DNS / 防火墙 / 代理 -> sysop
- 打开应用 / 列出应用 / 安装卸载 -> open_app / list_apps / pkg_install

### 位置
- 涉及地理任务先调 locate_rough 粗查
- 展示粗查结果 + 风险告知
- 询问用户是否提供精确位置
- 用户同意后用 locate_set_exact 保存

## 路径规则

所有文件路径都用相对工作目录的形式（如 src/main.py），不要写绝对路径。

## 用户引用（@）

用户消息里可能包含 @文件引用。引用内容已附加在消息末尾。
直接阅读引用块，不要再次调用 read_file。

## 回复格式

- 使用简体中文。
- 使用 Markdown：代码块标语言，重要结论加粗。
- 简短直接，不要客套，不要重复工具返回值。
- 任务完成时给出一句话总结。

## 不要做的事

- 不要在没调用工具的情况下编造文件内容或运行结果。
- 不要在用户没要求时修改无关文件。
- 不要用 read_file 读二进制文件（会被拒绝）。
"""

COMPACT_PROMPT = r"""你是 One Cedric 的对话摘要助手。

请把下面这段历史对话压缩成结构化摘要。

必须保留：
1. 用户的原始目标、约束和偏好
2. 已完成的所有文件改动：文件路径 + 关键变化
3. 关键决策及其原因
4. 尚未完成的待办事项
5. 通过工具发现的重要事实

用简体中文输出，格式：

## 目标

## 已完成

## 关键决策

## 关键上下文

## 待办

不要输出任何额外说明。"""

TITLE_PROMPT = r"""你是会话标题生成器。请根据用户的第一条消息和助手的第一条回复，
生成一个不超过 20 个汉字的标题。

要求：
1. 优先使用动词开头
2. 突出具体对象
3. 只输出标题本身，不要引号、句号、换行、解释

示例输出：
重构 utils.py 的 parse_date
给登录页加验证码
修复 pytest 超时问题
"""

PLAN_SYSTEM_PROMPT = r"""你现在处于「计划模式」。只能使用只读工具，不能修改任何文件。

## 任务

1. 用只读工具调研清楚现状。
2. 调研完成后，输出一份可执行的计划。
3. 计划必须是 Markdown 有序列表（1. 2. 3.），每条一个原子动作。
4. 每条包含：做什么 + 涉及哪个文件。
5. 输出计划后停下，等用户批准。

## 计划格式

## 计划

1. 读取 `src/utils.py` 确认实现
2. 拆出 `_try_iso(s)` 辅助函数
3. 更新测试
4. 运行 pytest 验证
"""