"""REEL CONFIG — One Cedric · "An AI agent for beginners" · 15 s at 128 BPM.

Identity, timeline, palette and copy for one film. Everything on screen is
English; every number on screen is structural (tool count, frontend count,
licence, version) rather than a performance claim the product never made.

The palette is not chosen by eye. Every value below is lifted from the product's
own source, so the film and the running app are the same colour:

    one_cedric/config.py            BRAND  #d97757   ACCENT #4ec9b0
                                    the ✦ cursor mark, styled #ff9e2c
    gateway/webui/style.css :root   --bg #0b0b0d    --bg-soft #101013
                                    --bg-elev #16161a  --border #232328
                                    --brand #d97757  --brand-soft #f0a478
                                    --brand-dim #b5653f  --accent #7dcfff
                                    --text #e8e6e3   --ok #9ece6a
                                    --warn #e0af68   --err #f7768e
    gateway/webui/style.css light   --brand #b55430 (the light-theme brand)

One Cedric's only two graphic assets are its wordmark and its pixel dog
(`one_cedric/ui/dog.py`: ▐•ᴥ•▌~, green when idle, red when busy), plus the ✦
cursor. There is no logo file in the repository, so the film draws the ✦ as a
vector and renders the dog from the product's own frame strings — nothing here
is an invented identity.
"""

# --- identity ---------------------------------------------------------------
BRAND = "ONE CEDRIC"
DOMAIN = "GITHUB.COM/AOAN2011/ONE-CEDRIC"
PRODUCT = "ONE CEDRIC"
STUDIO = "PUBLIC BETA I"
PLATFORMS = "PYTHON 3.10+ · CLI + WEBUI"
TAGLINE = "AN AI AGENT FOR BEGINNERS"
AUTHOR_HANDLE = "@Aoan2011"
LICENSE = "GPL-3.0"
VERSION = "PUBLIC BETA I"

# --- timeline ---------------------------------------------------------------
# 15.000 s exactly. One scene per bar, every cut lands on a downbeat.
#   seconds = bars * 4 * 60 / BPM      BPM = 240 * bars / seconds
#   8 bars -> 128 BPM | 6 bars -> 96 | 5 bars -> 80 | 4 bars -> 64
# 30 fps: 450 frames. A bar is 56.25 frames, so scene lengths resolve to
# 56 56 57 56 56 57 56 56 — build.render_one derives them from time, never
# hard-codes a count.
FPS = 30
BPM = 128
BEAT = 60.0 / BPM          # 0.46875 s
BAR = BEAT * 4             # 1.875 s
BARS = 8
DUR = BAR * BARS           # 15.000 s
NFRAMES = int(round(DUR * FPS))   # 450

# Layout is authored at 720p; the file that comes out is 1080p. Type, rules and
# everything vector are rasterised at the delivery size, so only the soft masks
# (glow, grain, the glass falloff) are built at the authoring size. Nothing in
# this film leans on fine print texture, so 720p authoring is the cheap correct
# path.
OUT_W, OUT_H = 1920, 1080
W, H = 1280, 720

# --- palette ----------------------------------------------------------------
INK = (7, 7, 9)             # deepest plate, a hair under the app's #0b0b0d
BG0 = (11, 11, 13)          # --bg
BG1 = (16, 16, 19)          # --bg-soft
BG2 = (22, 22, 26)          # --bg-elev   (the frosted panel fill)
BG3 = (30, 30, 35)          # one step above --bg-elev
LINE = (35, 35, 40)         # --border
LINE_SOFT = (24, 24, 29)    # --border-soft

BRAND_C = (217, 119, 87)    # --brand        the hero colour
BRAND_BR = (240, 164, 120)  # --brand-soft   brand pushed into glow
BRAND_DK = (181, 101, 63)   # --brand-dim
BRAND_HOT = (255, 158, 44)  # the ✦ cursor mark's own style

ACCENT = (125, 207, 255)    # --accent, the WebUI's cyan (also the HUD colour)
ACCENT_BR = (170, 226, 255)
ACCENT_LT = (203, 235, 255)
TEAL = (78, 201, 176)       # the CLI's ACCENT in config.py

OK = (158, 206, 106)
WARN = (224, 175, 104)
ERR = (247, 118, 142)
PLAN = (187, 154, 247)
INFO = (74, 158, 255)

WHITE = (238, 236, 233)
TEXT = (232, 230, 227)      # --text
TEXT_SOFT = (160, 156, 152)  # --text-soft
TEXT_DIM = (110, 107, 103)  # --text-dim
PAPER = (245, 244, 242)     # the app's light plate, unused in this dark cut
CARD = (255, 255, 255)

# aliases so shared helpers keep their generic names
GREY = TEXT_SOFT
GREY_D = TEXT_DIM
SLATE = (52, 52, 58)

# --- type -------------------------------------------------------------------
S_HERO = 150.0
S_WORD = 152.0
S_NUM = 196.0
S_MONO = 92.0
S_SUB = 16.0
S_TAG = 10.0
S_HUD = 9.0
S_MICRO = 8.0

TRACK_HERO = -4.5
TRACK_WORD = -3.5
TRACK_SUB = 3.0
TRACK_HUD = 1.4

# --- HUD chrome -------------------------------------------------------------
M = 56.0            # live-area margin for panel-style layouts
HUD_M = 27.0
HUD_TOP = 24.0
HUD_BOT = 700.0

SCENES = [
    ("01", "OPEN",          "Title build"),
    ("02", "TERMINAL CLI",  "The CLI frontend"),
    ("03", "240+ TOOLS",    "Capability grid"),
    ("04", "ANY MODEL",     "Providers, one core"),
    ("05", "SANDBOXED",     "Local and file-smart"),
    ("06", "WEBUI",         "Liquid Glass, for real"),
    ("07", "STUDENT BUILT", "Who made this"),
    ("08", "SIGN OFF",      "Lockup and repo"),
]

# 02 — the three idea words, one beat each (the bar is split four ways)
KINETIC_WORDS = ["LOCAL", "FILE-SMART", "SANDBOXED", "BEGINNER-FIRST"]
KINETIC_SUBS = [
    "FILES NEVER LEAVE YOUR MACHINE",
    "IT READS THE FOLDER YOU POINT AT",
    "UNKNOWN SHELL COMMANDS ARE BLOCKED",
    "PLAIN QUESTIONS, REAL ANSWERS",
]

# 03 — the product's own tool categories (README §5)
TOOL_CATS = ["FILES", "WEB", "TERMINAL", "DATA", "OFFICE", "CODE HELP", "MEDIA", "MCP"]
TOOL_CHIPS = [
    "read_file", "write_file", "edit_file", "glob", "grep_regex", "file_info",
    "web_fetch", "web_search", "http_request", "bash", "bash_bg",
    "sqlite", "csv_query", "json_query", "postgres_query",
    "docx", "pptx", "xlsx", "pdf", "lsp_hover", "lsp_defs", "lsp_diag",
    "image", "audio", "video", "qrcode", "archive", "email",
]
TOOL_COUNT = 240

# 04 — anything that speaks the OpenAI protocol
PROVIDERS = ["OLLAMA", "DEEPSEEK", "KIMI", "OPENAI", "ANY COMPATIBLE"]

# 05 — what the sandbox and the local core actually do
SAFETY = [
    ("SANDBOX TERMINAL", "UNKNOWN COMMANDS BLOCKED", OK),
    ("SECRETS SCRUBBED", "ENV VARS CLEANED BEFORE RUN", OK),
    ("SNAPSHOTS + /UNDO", "EVERY EDIT REVERSIBLE", ACCENT),
    ("STAYS ON YOUR MACHINE", "NO UPLOAD, NO TELEMETRY", BRAND_BR),
]

# 06 — the WebUI's own furniture (README §7)
SESSIONS = ["summarize readme", "refactor gateway", "fix lsp timeout", "dream review"]
WEBUI_NAV = ["CHAT", "TOOLS", "STATS", "DREAM", "SETTINGS"]
THINK_LEVELS = ["MINIMAL", "LOW", "MEDIUM", "HIGH", "ULTRA"]
THINK_AT = 2

# 07 — a contribution grid, lit in brand orange
GRID_COLS, GRID_ROWS = 34, 4
