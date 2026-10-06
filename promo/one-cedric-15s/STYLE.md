# STYLE — One Cedric · "An AI agent for beginners"

## Why there is no style card here

The deck is drawn when the user names neither a brand nor a style. This brief
named the brand, so the draw was skipped (`--style none`): a promo film for a
product has to look like *that product*, not like a randomly drawn aesthetic.

The language used is the engine's **brand dark product film**:

| move | how it is done here |
|---|---|
| brand colour, measured not chosen | every value lifted from the repo (below) |
| **real product UI, not a lookalike** | bars 02, 05 and 06 reproduce the actual CLI panels and the actual WebUI (see below) |
| the product's own marks | the ✦ cursor and the pixel dog, drawn from source |
| dark plate, warm grade | grade lifts red, cut flash is brand orange |
| one idea per bar | eight bars at 128 BPM, every cut on a downbeat |

## The UI scenes are reproductions, not inventions

The first cut of this film drew a generic terminal window and a plausible-looking
chat app. That was wrong: it was my idea of a UI, not One Cedric's. Bars 02, 05
and 06 were rebuilt against screenshots of the product actually running.

What the real frontends look like, and what the film now draws:

**CLI** (`one_cedric/ui/` + `rich`) — a stack of bordered panels, not a window:

* an orange banner panel whose **title sits on the top edge** (`✦ One Cedric ✦
  Public Beta I`), with a rule beneath it, six metadata rows
  (`MODEL / API / DIRECTORY / SESSION / GLOBAL / PROJECT`, teal labels,
  right-aligned in their own column), a centred `[ reasoning on ]`, and a
  centred keys line;
* a green status panel titled `One Cedric` carrying the pixel dog, a ✓, `Ready`,
  a dotted `Context` row with `deepseek-flash · turn 0` at the far right, and
  `One Cedric · GPL-3.0`;
* the orange `>` prompt, then the green tool panel it produces
  (`list_files` … `COMPLETE`).

`scenes.panel()` draws that frame as strokes — a bordered box with the title
punched into the top edge — rather than with box-drawing glyphs, which the
bundled faces do not carry.

**WebUI** (`one_cedric/gateway/webui/`) — in the film, top to bottom:

* the bar: `≡`, the ✦ mark, `One Cedric`, a `deepseek-flash` model chip, the
  session-title box, then the icon row (search, theme, panel, bell, new, stats,
  activity, sliders, help) and the red `482` counter;
* a **tabbed** sidebar (`Sessions · Q&A · Tools 240 · Outline`) with a `SESSIONS`
  header and a `+`; session rows carry a title *and* a meta line
  (`16 msgs · 3h ago`), and the active row is an orange glass pill;
* the message stack: the user's message in a bordered box behind an orange `>`,
  a collapsible `Reasoning` block with its character count, tool rows
  (ringed dot + name + argument), then the answer;
* the composer: placeholder line with the real key hints, a paperclip, the
  **auto-confirm toggle**, and a `Send` button with a return-arrow icon;
* the **bottom status bar**: model, working directory, `ready`, session count,
  and the `ctrl+p commands` chip.

Every icon in the top bar and the composer is drawn as vector strokes; none is a
glyph, because the bundled faces carry no icon set.

## Palette — measured, with the source of each value

| token | value | where it came from |
|---|---|---|
| `BRAND_C` | `#d97757` | `one_cedric/config.py` `BRAND`, and `style.css` `--brand` |
| `BRAND_BR` | `#f0a478` | `style.css :root` `--brand-soft` |
| `BRAND_DK` | `#b5653f` | `style.css :root` `--brand-dim` |
| `BRAND_HOT` | `#ff9e2c` | `config.py` `CURSOR_STYLE` — the ✦ cursor's own colour |
| `ACCENT` | `#7dcfff` | `style.css :root` `--accent`; the HUD is built from it |
| `TEAL` | `#4ec9b0` | `config.py` `ACCENT` (the CLI's accent) |
| `OK` | `#9ece6a` | `style.css` `--ok`; also the dog's idle colour |
| `WARN` | `#e0af68` | `style.css` `--warn` |
| `ERR` | `#f7768e` | `style.css` `--err`; also the dog's busy colour |
| `INK` | `#070709` | `--bg #0b0b0d`, taken one step deeper as the deepest plate |
| `BG0` | `#0b0b0d` | `style.css :root` `--bg` |
| `BG1` | `#101013` | `--bg-soft` |
| `BG2` | `#16161a` | `--bg-elev` |
| `LINE` | `#232328` | `--border` |
| `TEXT` | `#e8e6e3` | `--text` |
| `PAPER` | `#f5f4f2` | the app's light theme `--bg` (kept, unused in this cut) |

The plate is deliberately near-black rather than navy, so the warm brand orange
is the only saturated thing in frame.

## Two marks that are the product's, not invented

The repository contains no logo file. Its identity on screen is:

1. **the ✦ cursor** — `config.py`: `CURSOR_MARK = "✦"`, `CURSOR_STYLE = "bold
   #ff9e2c"`. No bundled face carries U+2726, so `scenes.star()` draws it as a
   four-point concave polygon. It appears as the HUD bug, as the "thinking"
   mark before the assistant's name, and as the hero of bars 01 and 08.
2. **the pixel dog** — `one_cedric/ui/dog.py`'s own frame strings
   (`▐•ᴥ•▌~` idle in green, `▐●ᴥ●▌` busy in red), rendered by `scenes.dog()`.
   JBMono carries `▐ • ▌ ~` but not `ᴥ` (U+1D25), so the muzzle is a vector
   wedge instead of a substituted character.

### Glyph rule for this project

Every non-ASCII character drawn on screen was checked against the bundled
faces with fontTools. JBMono is missing U+28xx (all braille — a braille spinner
renders as eight tofu boxes), U+1D25, U+2713 and U+2726. Consequences:

* the CLI spinner is a drawn arc, not a braille spinner;
* the pass mark next to an allowed command is a drawn dot, not `✓`;
* the ✦ is a polygon, not type.

Only `·` (U+00B7), `—`, `…`, `✕` (U+2715) and `●` (U+25CF, dog eyes) are used
as glyphs, and all five exist in JetBrains Mono.

## Grid

```
15.000 s · 128 BPM · 30 fps · 450 frames · one scene per bar (1.875 s)
scene lengths resolve to 56 56 57 56 56 57 56 56 — derived from time, never
hard-coded.
```

## Scene map

| bar | scene | what it says | must-have it carries |
|---|---|---|---|
| 01 | OPEN | the wordmark, the tagline, three structural words | "An AI agent for beginners" |
| 02 | TERMINAL CLI | the real banner, status panel and tool panel | the CLI frontend |
| 03 | 240+ TOOLS | the count, over two bands of real tool names | 240+ built-in tools |
| 04 | ANY MODEL | Ollama / DeepSeek / Kimi / OpenAI into one core | OpenAI-compatible |
| 05 | SANDBOXED | a blocked command, an allowed one, four promises | local and file-smart |
| 06 | WEBUI | the real Liquid Glass window, top bar to status bar | the WebUI frontend |
| 07 | STUDENT BUILT | the author and a contribution grid | built by a high school student |
| 08 | SIGN OFF | lockup, the dog, the repo slug | `github.com/Aoan2011/One-Cedric` |

The repository slug runs in the HUD on **every** frame, so the call to action is
on screen for all fifteen seconds, not only at the end.

## Craft notes worth keeping

* `A.out_expo` is `1 - e^(-kt)` and settles near 0.96, never at 1. Anything that
  must *complete* — the 240 counter, wipe rules, per-character reveals — uses the
  local `scenes.ease()` (a cubic that reaches 1). Using `out_expo` for the
  counter silently printed **230** where the film claims 240.
* Additive washes (`scenes.plate`) take 0–255 palette tuples like everything
  else and run them through `rgb01`. Feeding raw 0–255 values into the additive
  buffer makes the glow ~300x too strong; `chroma()` then clips the whole frame
  to white while the plate still looks black in the source.
