"""The eight scenes — one per bar of the 128 BPM grid.

Everything on screen is English and every claim is structural (tool count,
frontend count, licence, version, the sandbox's own behaviour) rather than a
performance number the product never measured.

Two pieces of the product's own identity are drawn here rather than invented:

  * the ✦ cursor mark, which the CLI styles `bold #ff9e2c`
    (one_cedric/config.py, CURSOR_MARK / CURSOR_STYLE), and
  * the pixel dog from one_cedric/ui/dog.py, built from that file's own frame
    strings (▐•ᴥ•▌~ idle in green, ▐●ᴥ●▌ busy in red).

There is no logo file anywhere in the repository, so nothing here imitates one.
"""
from __future__ import annotations

import numpy as np

from mg import anim as A
from mg import fonts as F
from mg.core import clip01, gauss, radial, rgb01

from . import theme as T

W, H = T.W, T.H
BEAT = T.BEAT
CX, CY = W / 2.0, H / 2.0


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def mono(p, x, y, s, color, size=None, track=None, alpha=1.0, anchor="ls"):
    return p.text(x, y, s, F.mono(size or T.S_TAG), color,
                  T.TRACK_HUD if track is None else track, anchor, alpha)


def star(p, cx, cy, r, color, alpha=1.0, rot=0.0, inner=0.26, arms=4):
    """The ✦ cursor mark as a vector: a 4-point concave star. JBMono has no
    U+2726, so this is the only way the brand's own cursor reads on screen."""
    pts = []
    for i in range(arms * 2):
        a = rot - np.pi / 2 + i * np.pi / arms
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * np.cos(a), cy + rr * np.sin(a)))
    p.poly(pts, color, alpha)


def reveal(p, x, y, s, f, color, track=0.0, anchor="ls", prog=1.0, alpha=1.0):
    """Per-character reveal: character i appears once prog passes i/n."""
    n = max(1, len(s))
    wdt = F.measure(f, s, track)
    x0 = x - wdt / 2.0 if anchor[0] == "m" else (x - wdt if anchor[0] == "r" else x)
    xs = F.kerned_layout(f, s, track)
    for i, ch in enumerate(s):
        a = float(np.clip(prog * n - i, 0.0, 1.0))
        if a > 0.01 and ch != " ":
            p.text(x0 + xs[i], y, ch, f, color, 0.0, "ls", alpha * a)
    return wdt


def typed(s, t, t0, cps=36.0):
    n = int(max(0.0, t - t0) * cps)
    return s[:max(0, min(len(s), n))]


def ease(t, t0, dur, k=4.0):
    """0->1 progress that actually reaches 1.

    A.out_expo is 1 - e^(-kt), which settles at ~0.96 and never arrives. That is
    right for an entrance — it is what makes a landing feel soft — but it is
    wrong for anything that has to complete: a counter stops at 230 instead of
    240, and a wipe rule stops just short of the word it is underlining.
    """
    return 1.0 - (1.0 - float(np.clip((t - t0) / dur, 0.0, 1.0))) ** k


def glass(p, x, y, w, h, alpha=1.0, radius=8, fill=(T.BG2, T.BG1), border=T.LINE):
    """A Liquid Glass surface: hairline edge, vertical falloff, top highlight."""
    if alpha <= 0.01:
        return
    p.rect(x, y, w, h, border, 0.80 * alpha, radius=radius + 1)
    p.rect(x + 1, y + 1, w - 2, h - 2, alpha=alpha, radius=radius, grad=fill)
    p.rect(x + radius, y + 1.5, w - 2 * radius, 0.9, T.WHITE, 0.055 * alpha)


def hair(p, x0, y, x1, color=T.LINE, alpha=0.70):
    p.rect(x0, y, x1 - x0, 1.0, color, alpha)


def hero_size(s, target_w, track_ratio):
    return F.fit_size(s, target_w, F.display, track_ratio)


def dog(p, x, y, h, eye="•", tail="~", color=T.OK, alpha=1.0):
    """The product's own mascot, drawn from one_cedric/ui/dog.py's frames.

    JBMono carries ▐ • ▌ ~ but not ᴥ (U+1D25) — the one glyph the terminal has
    and the bundled faces do not — so the muzzle is a vector wedge rather than a
    substituted character. `y` is the baseline; `h` is the block height.
    """
    size = h / 0.72
    f = F.mono(size)
    adv = F.measure(f, "▐", 0.0)
    cells = [("▐", color), (eye, color), (None, color), (eye, color),
             ("▌", color), (tail, T.TEXT_SOFT)]
    for i, (g, col) in enumerate(cells):
        px = x + i * adv
        if g is None:
            # the muzzle stays eye-sized: a wedge any larger reads as a beak
            r = size * 0.105
            my = y - size * 0.30
            p.poly([(px + adv * 0.22, my - r), (px + adv * 0.78, my - r),
                    (px + adv * 0.50, my + r * 1.15)], col, alpha)
        else:
            p.text(px, y, g, f, col, 0.0, "ls", alpha)
    return adv * len(cells)


def pill(p, x, y, w, h, label, color, f, alpha=1.0, radius=None, lead=None):
    """A chip: tinted fill, a bright leading edge, uppercase label."""
    if alpha <= 0.01:
        return
    r = h / 2.0 if radius is None else radius
    p.rect(x, y, w, h, color, 0.13 * alpha, radius=r)
    p.rect(x, y, 2.2, h, color, 0.90 * alpha, radius=1.1)
    tx = x + 13
    if lead is not None:
        p.dot(x + 11, y + h / 2.0, 2.4, color, alpha * 0.95)
        tx = x + 20
    p.text(tx, y + h / 2.0 + f.size * 0.35, label.upper(), f, color, 1.8, "ls",
           alpha * 0.94)


def chip(p, x, y, w, h, label, color, f, alpha=1.0, fill=T.BG1, edge=T.LINE):
    if alpha <= 0.01:
        return
    p.rect(x, y, w, h, edge, 0.85 * alpha, radius=4)
    p.rect(x + 1, y + 1, w - 2, h - 2, fill, alpha, radius=3)
    p.text(x + 11, y + h / 2.0 + f.size * 0.35, label, f, color, 0.3, "ls",
           alpha * 0.92)


def status_pill(p, x, y, label, color, alpha=1.0, blink=1.0):
    f = F.ui(10, 600)
    w = F.measure(f, label.upper(), 2.4) + 34
    p.rect(x - w / 2, y - 11, w, 22, color, 0.13 * alpha, radius=11)
    p.dot(x - w / 2 + 15, y, 3.2, color, alpha * blink)
    p.text(x - w / 2 + 26, y + 3.6, label.upper(), f, color, 2.4, "ls",
           alpha * 0.92)
    return w


def plate(c, y, tint, gain=1.0, rx=640, ry=300):
    """A soft additive wash.

    `tint` is an ordinary 0-255 palette tuple like everywhere else in this
    film, so it goes through rgb01 here: feeding raw 0-255 values into the
    additive buffer makes the glow ~300x too strong, and chroma() then clips
    the whole frame to white while the plate looks untouched.
    """
    c.add += (rgb01(tint).reshape(1, 1, 3) * gain
              * gauss(W, H, CX, y, rx, ry)[..., None])


def dotfield(p, color, alpha=0.05, step=32.0):
    pts = [(x, y) for y in np.arange(20, H, step) for x in np.arange(20, W, step)]
    p.dots(pts, 1.0, color, alpha)
def check(p, cx, cy, r, color, alpha=1.0, width=2.0):
    """A drawn pass mark. JBMono has no U+2713 and the terminal's own ✓ is not a
    glyph this project can typeset, so the tick is two strokes."""
    p.line([(cx - r, cy - r * 0.05), (cx - r * 0.22, cy + r * 0.72)], color, width,
           alpha)
    p.line([(cx - r * 0.22, cy + r * 0.72), (cx + r, cy - r * 0.78)], color, width,
           alpha)


def caret(p, cx, cy, r, color, alpha=1.0, down=True):
    """A small solid disclosure triangle, standing in for ▾ / ▸ (neither is in
    the bundled faces)."""
    s = 1.0 if down else -1.0
    p.poly([(cx - r, cy - r * 0.5 * s), (cx + r, cy - r * 0.5 * s),
            (cx, cy + r * 0.8 * s)], color, alpha)


def panel(p, x, y, w, h, title="", border=T.LINE, fill=None, alpha=1.0,
          title_col=None, status=None, status_col=None, radius=5.0,
          title_size=10.5, title_track=1.4):
    """A bordered panel with its title sitting on the top edge — the frame the
    CLI's own output is built from (rich Panels), drawn as strokes rather than
    box-drawing glyphs. A `status` sits right-aligned on the same edge."""
    if alpha <= 0.01:
        return
    p.rect(x, y, w, h, border, 0.92 * alpha, radius=radius)
    if fill is not None:
        p.rect(x + 1, y + 1, w - 2, h - 2, fill, alpha,
               radius=max(0.0, radius - 1.0))
    if not title:
        return
    f = F.mono(title_size)
    lead = 12.0
    p.rect(x + lead - 5.0, y - 0.9, F.measure(f, title, title_track) + 10.0, 2.0,
           fill if fill is not None else T.BG0, alpha)
    p.text(x + lead, y + 4.4, title, f, title_col or border, title_track, "ls",
           alpha)
    if status:
        if fill is not None:
            sw = F.measure(f, status, title_track) + 10.0
            p.rect(x + w - 12.0 - sw, y - 0.9, sw, 2.0, fill, alpha)
        p.text(x + w - 12.0, y + 4.4, status, f, status_col or border,
               title_track, "rs", alpha)


def _ic_burger(p, x, y, r, col, a):
    for k in (-1, 0, 1):
        p.rect(x - r, y + k * r * 0.62 - 0.55, 2 * r, 1.1, col, a)


def _ic_search(p, x, y, r, col, a):
    p.ellipse(x - r * 0.16, y - r * 0.16, r * 0.6, r * 0.6, col, a, width=1.2)
    p.line([(x + r * 0.3, y + r * 0.3), (x + r * 0.85, y + r * 0.85)], col, 1.4, a)


def _ic_sun(p, x, y, r, col, a):
    p.ellipse(x, y, r * 0.40, r * 0.40, col, a, width=1.2)
    for k in range(8):
        th = k * np.pi / 4.0
        p.line([(x + np.cos(th) * r * 0.64, y + np.sin(th) * r * 0.64),
                (x + np.cos(th) * r * 0.98, y + np.sin(th) * r * 0.98)], col, 1.1, a)


def _ic_bell(p, x, y, r, col, a):
    p.arc(x, y - r * 0.12, r * 0.62, r * 0.62, 180, 360, col, 1.2, a)
    p.line([(x - r * 0.64, y + r * 0.2), (x + r * 0.64, y + r * 0.2)], col, 1.2, a)
    p.dot(x, y + r * 0.52, 1.3, col, a)


def _ic_plus(p, x, y, r, col, a):
    p.rect(x - 0.6, y - r, 1.2, 2 * r, col, a)
    p.rect(x - r, y - 0.6, 2 * r, 1.2, col, a)


def _ic_bars(p, x, y, r, col, a):
    for k, hh in enumerate((0.34, 0.62, 0.95)):
        p.rect(x - r + k * r * 0.72, y + r - 2 * r * hh, r * 0.36, 2 * r * hh, col, a)


def _ic_pulse(p, x, y, r, col, a):
    p.line([(x - r, y), (x - r * 0.46, y), (x - r * 0.2, y - r * 0.72),
            (x + r * 0.14, y + r * 0.72), (x + r * 0.46, y), (x + r, y)], col, 1.3, a)


def _ic_sliders(p, x, y, r, col, a):
    for k, yy in enumerate((-r * 0.48, r * 0.48)):
        p.rect(x - r, y + yy - 0.55, 2 * r, 1.1, col, a)
        p.dot(x - r * 0.3 + k * r * 0.86, y + yy, 1.6, col, a)


def _ic_panel(p, x, y, r, col, a):
    p.rect(x - r, y - r * 0.82, 2 * r, 1.64 * r, col, a, radius=1.4)
    p.rect(x - r + 0.9, y - r * 0.82 + 0.9, 2 * r - 1.8, 1.64 * r - 1.8, T.BG1, a,
           radius=1.0)
    p.rect(x - 0.5, y - r * 0.82, 1.0, 1.64 * r, col, a)


def _ic_help(p, x, y, r, col, a):
    p.ellipse(x, y, r * 0.86, r * 0.86, col, a, width=1.2)
    p.arc(x, y - r * 0.22, r * 0.34, r * 0.34, 200, 20, col, 1.2, a)
    p.dot(x, y + r * 0.44, 1.15, col, a)


def _ic_clip(p, x, y, r, col, a):
    p.arc(x, y - r * 0.25, r * 0.5, r * 0.62, 190, 350, col, 1.3, a)
    p.line([(x - r * 0.5, y - r * 0.2), (x - r * 0.5, y + r * 0.5),
            (x, y + r * 0.85), (x + r * 0.5, y + r * 0.5), (x + r * 0.5, y - r * 0.2)],
           col, 1.3, a)


def _ic_enter(p, x, y, r, col, a):
    p.line([(x + r * 0.7, y - r), (x + r * 0.7, y + r * 0.1),
            (x - r * 0.6, y + r * 0.1)], col, 1.3, a)
    p.line([(x - r * 0.3, y - r * 0.35), (x - r * 0.75, y + r * 0.1),
            (x - r * 0.3, y + r * 0.55)], col, 1.3, a)





# --------------------------------------------------------------------------
# 01 / OPEN — the title build
# --------------------------------------------------------------------------
class Open:
    Y_STAR = 236.0
    Y_HERO = 396.0
    Y_RULE = 442.0
    Y_TAG = 492.0
    Y_META = 532.0

    def render(self, c, tl, t):
        c.clear(T.INK)
        settle = A.out_expo(clip01(tl / 1.3), 3.0)
        hz = 350 + 70 * settle
        breath = 1.0 + 0.05 * np.sin(t * 1.9)
        plate(c, hz, T.BRAND_C, 0.055, 620, 118 * breath)
        plate(c, hz - 30, T.BRAND_DK, 0.030, 900, 240)

        p = c.pass_()
        dotfield(p, T.BG3, 0.16, 40.0)
        for a, wd in ((0.10, 3.4), (0.055, 1.4)):
            p.line([(96, hz), (W - 96, hz)], T.BRAND_BR, wd,
                   a * (0.40 + 0.60 * settle) * breath)

        # --- the ✦ cursor lands first: the product's own "I am thinking" mark
        e0 = A.out_elastic(clip01((tl - 0.02) / 0.75), 0.34, 5.0)
        if e0 > 0.01:
            star(p, CX, self.Y_STAR, 34 * (0.55 + 0.45 * e0), T.BRAND_HOT,
                 e0 * (0.85 + 0.15 * np.sin(t * 4.2)), rot=e0 * 0.22 - 0.11)

        # --- the wordmark. Size is solved so the line occupies 80% of the
        # frame: hard-coding it means a longer brand name runs off the edges.
        word = T.BRAND
        tr_ratio = T.TRACK_HERO / T.S_HERO
        size = hero_size(word, W * 0.80, tr_ratio)
        fh = F.display(size)
        tr = tr_ratio * size
        wm = F.measure(fh, word, tr)
        xm = CX - wm / 2.0
        xs = F.kerned_layout(fh, word, tr)
        for i, ch in enumerate(word):
            e = A.out_expo(clip01((tl - 0.12 - i * 0.042) / 0.60), 4.2)
            if e > 0.01 and ch != " ":
                p.text(xm + xs[i], self.Y_HERO + (1.0 - e) * 96, ch, fh, T.WHITE,
                       0.0, "lm", e)

        # --- brand rule wiping under the word
        wipe = ease(tl, 0.60, 0.38)
        if wipe > 0.001:
            x0, x1 = xm - 9, xm + wm + 9
            p.line([(x0, self.Y_RULE), (x0 + (x1 - x0) * wipe, self.Y_RULE)],
                   T.BRAND_C, 3.0, 0.95 * wipe)

        # --- the tagline, one letterspaced line
        es = ease(tl, 0.74, 0.45)
        if es > 0.01:
            fs = F.mono(T.S_SUB)
            tw = F.measure(fs, T.TAGLINE, T.TRACK_SUB)
            reveal(p, CX, self.Y_TAG + (1.0 - es) * 12, T.TAGLINE, fs, T.BRAND_BR,
                   T.TRACK_SUB, "ms", es, es * 0.95)
            _ = tw

        # --- the three structural words, so the frame is dense by the end
        em = ease(tl, 1.02, 0.45)
        if em > 0.01:
            mono(p, CX, self.Y_META, "LOCAL · FILE-SMART · 240+ BUILT-IN TOOLS",
                 T.GREY, T.S_TAG, 1.8, em * 0.86, "ms")
        _ = breath
        c.commit()


# --------------------------------------------------------------------------
# 02 / TWO FRONTENDS — the CLI on the left, the WebUI on the right
# --------------------------------------------------------------------------
class CliFrontend:
    """The terminal frontend, rebuilt from a real `python run.py --chat` session.

    The product's CLI is a stack of bordered panels: an orange banner carrying
    the model / API / directory / session rows, a green status panel with the
    pixel dog and Ready, then the prompt and the tool panel it produces. The
    earlier version of this scene drew a generic terminal window, which is not
    what One Cedric looks like.
    """

    BX, BY, BW, BH_ = 56.0, 112.0, 1168.0, 200.0
    SX, SY, SW, SH_ = 56.0, 326.0, 770.0, 114.0
    TX, TY, TW, TH_ = 56.0, 482.0, 1168.0, 96.0
    ASK = "Read README.md and summarize the project"

    ROWS = [
        ("MODEL", "deepseek-flash"),
        ("API", "https://api.deepseek.com"),
        ("DIRECTORY", "F:\\one-cedric3"),
        ("SESSION", "20261006-204155-e232"),
        ("GLOBAL", "~\\.one-cedric\\config.toml"),
        ("PROJECT", "~\\.one-cedric\\projects\\a2ca85…toml"),
    ]

    def render(self, c, tl, t):
        c.clear(T.BG0)
        plate(c, 330, T.BRAND_C, 0.018, 780, 320)
        p = c.pass_()
        dotfield(p, T.BG3, 0.11, 40.0)

        # --- the launch line, the way the shell shows it
        e0 = ease(tl, 0.0, 0.28)
        if e0 > 0.01:
            mono(p, T.M, 92, "PS F:\\one-cedric3>", T.GREY, 10.0, 0.4, e0 * 0.9)
            mono(p, T.M + 152, 92, typed("python run.py --model deepseek-flash "
                                        "--chat", tl, 0.0, 96.0), T.WHITE, 10.0,
                 0.4, e0)

        # --- the banner panel
        eb = ease(tl, 0.06, 0.32)
        if eb > 0.01:
            panel(p, self.BX, self.BY, self.BW, self.BH_, border=T.BRAND_C,
                  fill=T.INK, alpha=eb, radius=5)
            f = F.mono(11.0)
            ww = F.measure(f, "One Cedric", 0.6)
            star(p, CX - ww / 2 - 30, self.BY + 0.6, 6.2, T.BRAND_HOT, eb)
            p.text(CX - ww / 2, self.BY + 4.6, "One Cedric", f, T.WHITE, 0.6, "ls",
                   eb)
            star(p, CX + ww / 2 + 30, self.BY + 0.6, 6.2, T.BRAND_HOT, eb)
            mono(p, CX + ww / 2 + 44, self.BY + 4.6, T.VERSION, T.GREY, 10.0, 1.4,
                 eb * 0.9)
            hair(p, self.BX + 14, self.BY + 17, self.BX + self.BW - 14, T.INFO,
                 0.5 * eb)

            lab_x, val_x = self.BX + 152, self.BX + 172
            for i, (lab, val) in enumerate(self.ROWS):
                ea = ease(tl, 0.18 + i * 0.040, 0.26)
                if ea <= 0.01:
                    continue
                y = self.BY + 44 + i * 20.0
                mono(p, lab_x, y, lab, T.TEAL, 10.0, 1.4, ea * 0.95, "rs")
                mono(p, val_x, y, val, T.ACCENT_LT, 10.0, 0.3, ea)

            er = ease(tl, 0.42, 0.28)
            if er > 0.01:
                mono(p, CX, self.BY + 172, "[ reasoning on ]", T.TEAL, 10.0, 2.0,
                     er * 0.95, "ms")
                mono(p, CX, self.BY + 190,
                     "type /help for commands  ·  @file to attach  ·  "
                     "Ctrl+C to interrupt", T.GREY_D, 9.0, 1.2, er * 0.8, "ms")

        # --- the status panel: the dog, then the session's own readout
        es = ease(tl, 0.54, 0.32)
        if es > 0.01:
            panel(p, self.SX, self.SY, self.SW, self.SH_, title="One Cedric",
                  border=T.OK, fill=T.INK, alpha=es, title_col=T.OK, radius=5)
            ey = self.SY + 38
            eye = ["•", "•", "-", "•", "•", "•", "-", "•"][int(t * 2.86) % 8]
            tail = "~" if int(t * 5.5) % 2 == 0 else " "
            dog(p, self.SX + 18, ey, 18.0, eye, tail, T.OK, es * 0.95)
            check(p, self.SX + 132, ey - 6, 6.0, T.OK, es * 0.95, 2.0)
            mono(p, self.SX + 146, ey, "Ready", T.OK, 11.0, 0.8, es * 0.95)
            mono(p, self.SX + 18, ey + 32, "Context", T.GREY, 10.0, 1.0, es * 0.85)
            p.dots([(x, ey + 28) for x in np.arange(self.SX + 88, self.SX + self.SW - 250,
                                                    7.0)], 1.0, T.SLATE, es * 0.8)
            mono(p, self.SX + self.SW - 18, ey + 32, "deepseek-flash · turn 0",
                 T.GREY, 10.0, 0.4, es * 0.85, "rs")
            mono(p, self.SX + 18, ey + 60, "One Cedric · GPL-3.0", T.OK, 10.0, 0.8,
                 es * 0.85)

        # --- the prompt, typed the way it is actually typed
        ep = ease(tl, 0.92, 0.42)
        if ep > 0.01:
            p.text(self.SX, 468, ">", F.display(13), T.BRAND_C, 0.0, "ls", ep)
            ask = typed(self.ASK, tl, 0.92, 62.0)
            mono(p, self.SX + 24, 468, ask, T.WHITE, 11.0, 0.2, ep)
            if len(ask) < len(self.ASK):
                cw = F.measure(F.mono(11.0), ask, 0.2)
                p.rect(self.SX + 26 + cw, 459, 6.5, 12, T.BRAND_HOT,
                       ep * (0.5 + 0.5 * np.sin(t * 9.0)))

        # --- and the tool panel that prompt produces
        et = ease(tl, 1.30, 0.34)
        if et > 0.01:
            panel(p, self.TX, self.TY, self.TW, self.TH_, title="list_files",
                  status="COMPLETE", border=T.OK, fill=T.INK, alpha=et,
                  title_col=T.OK, status_col=T.OK, radius=5)
            mono(p, self.TX + 16, self.TY + 24, "20 items", T.GREY, 9.5, 0.8,
                 et * 0.85)
            for i, r in enumerate(("[DIR]  one_cedric/", "[FILE] README.md",
                                   "[FILE] requirements.txt", "[FILE] run.py")):
                ea = ease(tl, 1.38 + i * 0.05, 0.24)
                if ea > 0.01:
                    mono(p, self.TX + 16, self.TY + 46 + i * 15.0, r, T.ACCENT_LT,
                         9.0, 0.3, ea * 0.9)
        c.commit()



# --------------------------------------------------------------------------
# 03 / 240+ TOOLS — the capability grid
# --------------------------------------------------------------------------
class ToolGrid:
    def __init__(self):
        self.rng = np.random.default_rng(20261006)

    def render(self, c, tl, t):
        c.clear(T.INK)
        plate(c, 350, T.BRAND_C, 0.045, 720, 260)
        p = c.pass_()
        dotfield(p, T.BG3, 0.15, 40.0)

        # --- two bands of chips, seven across, ringing the number
        fchip = F.mono(9.0)
        cellw, chiph = 166.9, 36.0
        for k, name in enumerate(T.TOOL_CHIPS):
            band = 0 if k < 14 else 1
            i, j = k % 7, (k // 7) % 2
            x = 56 + i * cellw
            y = (150.0 if band == 0 else 470.0) + j * 50.0
            e = A.out_expo(clip01((tl - 0.06 - k * 0.026) / 0.36), 4.2)
            if e <= 0.01:
                continue
            chip(p, x, y + (1.0 - e) * 10, cellw - 12, chiph, name, T.GREY, fchip,
                 e * (0.55 + 0.45 * e))

        # --- the count. The size is solved from the finished "240+" so the
        # digits stay put horizontally while they climb.
        e = ease(tl, 0.26, 0.82, 3.0)
        val = int(round(T.TOOL_COUNT * e))
        tr_ratio = T.TRACK_HERO / T.S_HERO
        size = hero_size(f"{T.TOOL_COUNT}+", W * 0.46, tr_ratio)
        fh = F.display(size)
        tr = tr_ratio * size
        full_w = F.measure(fh, f"{T.TOOL_COUNT}", tr)
        plus_w = F.measure(fh, "+", tr)
        x0 = CX - (full_w + plus_w) / 2.0
        if val > 0:
            p.text(x0, 372.0, f"{val}", fh, T.WHITE, tr, "ls", min(1.0, e * 4.0))
        if val >= T.TOOL_COUNT:
            ep = float(np.clip(A.out_back(clip01((tl - 1.10) / 0.40), 1.6), 0.0, 1.0))
            p.text(x0 + full_w, 372.0, "+", fh, T.BRAND_C, tr, "ls", ep)

        # --- label + categories
        e2 = A.out_expo(clip01((tl - 1.20) / 0.40), 4.0)
        if e2 > 0.01:
            fs = F.mono(15.0)
            wl = F.measure(fs, "BUILT-IN TOOLS", 4.0)
            p.rect(CX - wl / 2 - 16, 404.0, wl + 32, 1.0, T.LINE, 0.9 * e2)
            p.text(CX, 438.0, "BUILT-IN TOOLS", fs, T.BRAND_BR, 4.0, "ms", e2)
            mono(p, CX, 466.0,
                 " · ".join(T.TOOL_CATS), T.GREY, T.S_MICRO, 2.0, e2 * 0.85, "ms")
        c.commit()


# --------------------------------------------------------------------------
# 04 / ANY MODEL — providers into one core
# --------------------------------------------------------------------------
class AnyModel:
    PX, PW, PH_ = 84.0, 330.0, 54.0
    NX, NW = 764.0, 430.0
    ROW0, ROWG = 158.0, 76.0

    def render(self, c, tl, t):
        c.clear(T.INK)
        plate(c, 330, T.ACCENT, 0.028, 760, 300)
        plate(c, 330, T.BRAND_C, 0.026, 560, 220)

        p = c.pass_()
        dotfield(p, T.BG3, 0.15, 40.0)
        c.commit()

        # --- provider pills, left
        rows = []
        for i, name in enumerate(T.PROVIDERS):
            e = A.out_expo(clip01((tl - 0.05 - i * 0.085) / 0.40), 4.0)
            y = self.ROW0 + i * self.ROWG
            rows.append((y + self.PH_ / 2.0, e))
            if e <= 0.01:
                continue
            p = c.pass_()
            p.push(dx=-22 * (1.0 - e), dy=0)
            col = T.BRAND_C if i == len(T.PROVIDERS) - 1 else T.ACCENT
            pill(p, self.PX, y, self.PW, self.PH_, name, col, F.mono(11.0),
                 e, radius=6, lead=True)
            mono(p, self.PX + self.PW - 14, y + self.PH_ / 2.0 + 4.0,
                 "OPENAI-COMPATIBLE" if i == len(T.PROVIDERS) - 1 else "API",
                 T.GREY_D, T.S_MICRO, 1.0, e * 0.8, "rs")
            p.pop()
            c.commit()

        # --- the connectors and their packets
        x0, x1 = self.PX + self.PW + 8, self.NX - 8
        p = c.pass_()
        for i, (yc, e) in enumerate(rows):
            if e <= 0.02:
                continue
            prog = A.out_expo(clip01((tl - 0.34 - i * 0.06) / 0.48), 3.4)
            if prog <= 0.01:
                continue
            n = 34
            u = np.linspace(0, 1, n)
            ease = u * u * (3.0 - 2.0 * u)
            xs = x0 + (x1 - x0) * ease * prog
            ys = yc + (330.0 - yc) * ease * prog
            p.path(list(zip(xs, ys)), T.ACCENT, 1.1, 0.42 * e)
            # a packet running the wire
            if prog > 0.9:
                ph = (t * 0.85 + i * 0.19) % 1.0
                k = int(ph * (n - 1))
                p.dot(xs[k], ys[k], 3.0, T.BRAND_HOT, 0.95 * e)
                p.dot(xs[k], ys[k], 6.5, T.BRAND_C, 0.22 * e)

        # --- the core node
        en = A.out_expo(clip01((tl - 0.18) / 0.55), 3.0)
        if en > 0.01:
            nx, ny, nw, nh = self.NX, 232.0, self.NW, 196.0
            p.rect(nx - 1, ny - 1, nw + 2, nh + 2, T.BRAND_C, 0.55 * en, radius=13)
            p.rect(nx, ny, nw, nh, en, radius=12, grad=(T.BG2, T.BG1))
            star(p, nx + nw / 2.0, ny + 58, 26 * en, T.BRAND_HOT,
                 en * (0.85 + 0.15 * np.sin(t * 3.6)))
            p.text(nx + nw / 2.0, ny + 108, "ONE CEDRIC", F.display(26), T.WHITE,
                   0.4, "ms", en)
            mono(p, nx + nw / 2.0, ny + 136, "AGENT CORE · TOOL DISPATCH",
                 T.GREY, T.S_MICRO, 2.2, en * 0.85, "ms")
            mono(p, nx + nw / 2.0, ny + 162, "PYTHON 3.10+ · RUNS ON YOUR MACHINE",
                 T.GREY_D, T.S_MICRO, 1.6, en * 0.75, "ms")
        c.commit()

        # --- kicker and footer
        p = c.pass_()
        e1 = A.out_expo(clip01((tl - 0.62) / 0.45), 4.0)
        if e1 > 0.01:
            mono(p, T.M, 104, "MODEL", T.GREY_D, T.S_TAG, 2.2, e1 * 0.9)
            mono(p, W - T.M, 104, "ANY OPENAI-COMPATIBLE PROVIDER", T.BRAND_BR,
                 T.S_TAG, 2.2, e1, "rs")
        e2 = A.out_expo(clip01((tl - 1.24) / 0.42), 4.0)
        if e2 > 0.01:
            mono(p, CX, 560, "OLLAMA · DEEPSEEK · KIMI · CHATGPT · LOCAL",
                 T.GREY, T.S_TAG, 2.0, e2 * 0.9, "ms")
        c.commit()


# --------------------------------------------------------------------------
# 05 / SANDBOXED — what the terminal refuses to do
# --------------------------------------------------------------------------
class Sandboxed:
    """What the terminal refuses to do — in the CLI's own panel frame, so the
    sandbox reads as the same product rather than a generic shell."""

    PX, PW = 56.0, 600.0
    RX = 690.0

    def render(self, c, tl, t):
        c.clear(T.BG0)
        plate(c, 340, T.OK, 0.014, 760, 320)

        p = c.pass_()
        dotfield(p, T.BG3, 0.11, 40.0)

        # --- the refused command
        e1 = ease(tl, 0.06, 0.34)
        if e1 > 0.01:
            panel(p, self.PX, 168.0, self.PW, 150.0, title="bash", status="BLOCKED",
                  border=T.ERR, fill=T.INK, alpha=e1, title_col=T.ERR,
                  status_col=T.ERR)
            bx, by = self.PX + 18, 168.0 + 46.0
            mono(p, bx, by, "$", T.OK, 12.0, 0.3, e1)
            cmd = typed("rm -rf ~/projects", tl, 0.18, 30.0)
            mono(p, bx + 16, by, cmd, T.WHITE, 12.0, 0.3, e1)
            if len(cmd) == len("rm -rf ~/projects"):
                ew = ease(tl, 0.80, 0.30)
                if ew > 0.01:
                    cw = F.measure(F.mono(12.0), cmd, 0.3)
                    p.rect(bx + 16, by - 5, cw * ew, 1.6, T.ERR, 0.95)
                    mono(p, bx + 16, by + 30, "✕ not in the whitelist", T.ERR,
                         10.5, 1.4, ew * 0.95)
                mono(p, bx + 16, by + 54, "unknown shell commands are blocked",
                     T.GREY_D, 9.5, 0.8, ew * 0.85)

        # --- the command that is allowed
        e2 = ease(tl, 0.96, 0.34)
        if e2 > 0.01:
            panel(p, self.PX, 342.0, self.PW, 150.0, title="bash", status="COMPLETE",
                  border=T.OK, fill=T.INK, alpha=e2, title_col=T.OK, status_col=T.OK)
            bx, by = self.PX + 18, 342.0 + 46.0
            mono(p, bx, by, "$", T.OK, 12.0, 0.3, e2)
            cmd = typed("git status", tl, 1.08, 30.0)
            mono(p, bx + 16, by, cmd, T.WHITE, 12.0, 0.3, e2)
            if len(cmd) == len("git status"):
                ea = ease(tl, 1.34, 0.28)
                if ea > 0.01:
                    check(p, bx + 21, by + 26, 5.4, T.OK, ea * 0.95, 1.9)
                    mono(p, bx + 34, by + 30, "snapshot taken · /undo reverses it",
                         T.OK, 10.5, 1.4, ea * 0.95)
                    mono(p, bx + 16, by + 54, "sensitive env vars are scrubbed "
                         "before the command runs", T.GREY_D, 9.5, 0.8, ea * 0.85)

        # --- the four promises, right
        for i, (title, sub, col) in enumerate(T.SAFETY):
            ea = ease(tl, 0.44 + i * 0.13, 0.38)
            if ea <= 0.01:
                continue
            y = 186.0 + i * 92.0
            p.rect(self.RX, y, 534, 74, T.BG1, 0.80 * ea, radius=7)
            p.rect(self.RX, y, 2.4, 74, col, 0.92 * ea, radius=1.2)
            p.text(self.RX + 24, y + 34, title, F.ui(17, 700), T.WHITE, 0.6, "ls", ea)
            mono(p, self.RX + 24, y + 58, sub, T.GREY_D, T.S_MICRO, 1.6, ea * 0.9)
            star(p, self.RX + 534 - 26, y + 26, 7.0, col, ea * 0.75)

        e3 = ease(tl, 0.70, 0.42)
        if e3 > 0.01:
            mono(p, self.RX, 140, "YOUR FOLDERS STAY YOURS", T.BRAND_BR, T.S_TAG,
                 2.2, e3)
            mono(p, self.PX, 528, "sandbox ON · whitelist enforced · snapshots "
                 "before every edit", T.GREY, T.S_TAG, 1.8, e3 * 0.9)
            mono(p, W - T.M, 566, "LOCAL, FILE-SMART, AND CAREFUL BY DEFAULT",
                 T.GREY, T.S_TAG, 2.0, e3 * 0.9, "rs")
        c.commit()



# --------------------------------------------------------------------------
# 06 / LIQUID GLASS — the product's own window, full bleed
# --------------------------------------------------------------------------
class WebUi:
    """The Liquid Glass WebUI, redrawn from a real session.

    Structure, top to bottom: the bar with the ✦ mark, wordmark, model chip,
    session-title box and the window's icon row; a tabbed sidebar whose session
    rows carry message counts; the message / Reasoning / tool-row stack; the
    composer with its paperclip and auto-confirm toggle; and the bottom status
    bar (model, working directory, ready, session count, ctrl+p commands).
    """

    FX, FY, FW, FH_ = 56.0, 86.0, 1168.0, 488.0
    BAR = 46.0
    SB = 248.0
    ST = 34.0

    SESSIONS = [
        ("summarize readme", "16 msgs · 3h ago"),
        ("refactor gateway", "10 msgs · 3h ago"),
        ("fix lsp timeout", "8 msgs · 22h ago"),
        ("dream review", "6 msgs · 1d ago"),
    ]

    def render(self, c, tl, t):
        c.clear(T.INK)
        plate(c, 300, T.BRAND_C, 0.085, 700, 240)
        plate(c, 200, T.ACCENT, 0.026, 640, 190)
        plate(c, 520, T.BRAND_DK, 0.030, 760, 200)

        p = c.pass_()
        dotfield(p, T.BG3, 0.12, 40.0)
        c.commit()

        e = ease(tl, 0.0, 0.40, 3.0)
        if e <= 0.01:
            return
        p = c.pass_()
        p.push(scale=0.972 + 0.028 * e, ax=CX, ay=CY)

        fx, fy, fw, fh = self.FX, self.FY, self.FW, self.FH_
        sby = fy + self.BAR
        byy = fy + fh - self.ST

        # --- window
        p.rect(fx, fy, fw, fh, T.LINE, 0.95 * e, radius=12)
        p.rect(fx + 1, fy + 1, fw - 2, fh - 2, alpha=e, radius=11,
               grad=(T.BG2, T.BG0))

        # --- top bar
        p.rect(fx + 1, fy + 1, fw - 2, self.BAR, T.BG1, 0.80 * e, radius=11)
        p.rect(fx + 1, fy + self.BAR - 12, fw - 2, 12, T.BG1, 0.80 * e)
        hair(p, fx, fy + self.BAR, fx + fw, T.LINE, 0.9 * e)
        cy_bar = fy + self.BAR / 2.0
        _ic_burger(p, fx + 30, cy_bar, 7.0, T.TEXT, e * 0.85)
        star(p, fx + 56, cy_bar, 6.4, T.BRAND_HOT, e)
        p.text(fx + 68, cy_bar + 6, "One Cedric", F.display(15), T.WHITE, 0.3, "ls",
               e)
        chip(p, fx + 188, cy_bar - 13, 116, 26, "deepseek-flash", T.TEXT,
             F.mono(9.0), e * 0.95)
        chip(p, fx + 312, cy_bar - 14, 258, 28, "summarize readme", T.TEXT_SOFT,
             F.mono(9.5), e * 0.9)

        ix = fx + fw - 32
        for fn in (_ic_help, _ic_sliders, _ic_pulse, _ic_bars, _ic_plus, _ic_bell,
                   _ic_panel, _ic_sun, _ic_search):
            fn(p, ix, cy_bar, 7.0, T.TEXT_SOFT, e * 0.78)
            ix -= 29
        p.rect(ix - 26, cy_bar - 11, 54, 22, T.BG3, e * 0.9, radius=11)
        p.dot(ix - 13, cy_bar, 3.4, T.ERR, e * 0.95)
        mono(p, ix + 1, cy_bar + 4, "482", T.TEXT, 9.0, 0.3, e * 0.9)

        # --- sidebar
        p.rect(fx + 1, sby, self.SB, fh - self.BAR - self.ST, T.BG1, 0.72 * e)
        p.rect(fx + 1 + self.SB, sby, 1.0, fh - self.BAR - self.ST, T.LINE, 0.85 * e)
        tx = fx + 11
        for i, (name, act) in enumerate((("Sessions", True), ("Q&A", False),
                                         ("Tools 240", False), ("Outline", False))):
            ea = e * ease(tl, 0.16 + i * 0.05, 0.26)
            f = F.ui(9.5, 600)
            tw = F.measure(f, name, 0.8) + 22
            if act and ea > 0.01:
                p.rect(tx, sby + 8, tw, 24, T.BG3, 0.9 * ea, radius=6)
                p.rect(tx, sby + 8, 2.0, 24, T.BRAND_C, 0.9 * ea, radius=1.0)
            p.text(tx + 11, sby + 24, name, f, T.TEXT if act else T.GREY_D, 0.8,
                   "ls", ea * 0.9)
            tx += tw + 4
        mono(p, fx + 15, sby + 58, "SESSIONS", T.GREY_D, 8.5, 1.6, e * 0.85)
        p.rect(fx + self.SB - 28, sby + 48, 20, 20, T.BG3, e * 0.9, radius=5)
        _ic_plus(p, fx + self.SB - 18, sby + 58, 5.0, T.TEXT_SOFT, e * 0.85)
        for i, (title, meta) in enumerate(self.SESSIONS):
            ea = e * ease(tl, 0.26 + i * 0.06, 0.28)
            if ea <= 0.01:
                continue
            y = sby + 78 + i * 52.0
            if i == 0:
                p.rect(fx + 9, y - 6, self.SB - 18, 46, T.BRAND_C, 0.13 * ea,
                       radius=7)
                p.rect(fx + 9, y - 6, 2.2, 46, T.BRAND_C, 0.9 * ea, radius=1.1)
            p.text(fx + 21, y + 14, title, F.ui(11.5, 600),
                   T.TEXT if i == 0 else T.TEXT_SOFT, 0.2, "ls", ea)
            mono(p, fx + 21, y + 32, meta, T.GREY_D, 8.5, 0.6, ea * 0.85)
        p.dot(fx + 17, byy - 16, 3.2, T.OK, e * 0.9)
        mono(p, fx + 27, byy - 12, "connected", T.OK, 8.5, 0.8, e * 0.85)

        # --- the conversation
        mx = fx + 1 + self.SB + 18
        mw = fx + fw - 18 - mx
        ey = sby + 14
        e1 = e * ease(tl, 0.30, 0.32)
        if e1 > 0.01:
            p.rect(mx, ey, mw - 62, 54, T.LINE, 0.75 * e1, radius=8)
            p.rect(mx + 1, ey + 1, mw - 64, 52, T.BG1, e1, radius=7)
            p.text(mx + 16, ey + 24, ">", F.display(12), T.BRAND_C, 0.0, "ls", e1)
            mono(p, mx + 38, ey + 24, "@README.md what is this project?", T.TEXT,
                 10.5, 0.3, e1)
            mono(p, mx + 38, ey + 42, "workspace · auto-confirm on", T.GREY_D,
                 8.5, 0.6, e1 * 0.8)

        ry = ey + 66
        e2 = e * ease(tl, 0.44, 0.32)
        if e2 > 0.01:
            p.rect(mx + 26, ry, mw - 96, 64, T.LINE, 0.6 * e2, radius=8)
            p.rect(mx + 27, ry + 1, mw - 98, 62, T.BG0, e2, radius=7)
            caret(p, mx + 44, ry + 17, 4.0, T.GREY_D, e2 * 0.85)
            mono(p, mx + 54, ry + 21, "Reasoning", T.GREY, 9.5, 0.8, e2 * 0.9)
            mono(p, mx + mw - 84, ry + 21, "304 chars", T.GREY_D, 8.5, 0.6,
                 e2 * 0.8, "rs")
            mono(p, mx + 44, ry + 43, "The question is about this repository, so I",
                 T.TEXT_SOFT, 9.5, 0.2, e2 * 0.9)
            mono(p, mx + 44, ry + 57, "will read README.md first.", T.TEXT_SOFT,
                 9.5, 0.2, e2 * 0.9)

        ty = ry + 76
        for i, (name, arg) in enumerate((("read_file", "README.md"),
                                        ("glob", "**/*.py"))):
            ea = e * ease(tl, 0.58 + i * 0.07, 0.28)
            if ea <= 0.01:
                continue
            y = ty + i * 34.0
            p.rect(mx + 26, y, mw - 96, 28, T.LINE, 0.55 * ea, radius=7)
            p.rect(mx + 27, y + 1, mw - 98, 26, T.BG1, ea, radius=6)
            p.ellipse(mx + 44, y + 14, 5.6, 5.6, T.INFO, ea * 0.40, width=1.0)
            p.dot(mx + 44, y + 14, 3.0, T.INFO, ea * 0.95)
            mono(p, mx + 58, y + 18, name, T.TEXT, 9.5, 0.4, ea)
            mono(p, mx + 58 + F.measure(F.mono(9.5), name, 0.4) + 16, y + 18, arg,
                 T.GREY_D, 9.5, 0.3, ea * 0.9)

        e3 = e * ease(tl, 0.72, 0.30)
        if e3 > 0.01:
            for i, ln in enumerate((
                    "One Cedric is a local, file-smart AI agent with two frontends:",
                    "a terminal CLI and this Liquid Glass WebUI.")):
                ea = e3 * ease(tl, 0.74 + i * 0.07, 0.26)
                if ea > 0.01:
                    mono(p, mx + 26, ty + 86 + i * 22, ln, T.TEXT, 10.5, 0.3, ea)

        # --- composer
        cz = byy - 66
        e4 = e * ease(tl, 0.84, 0.32)
        if e4 > 0.01:
            p.rect(mx, cz, mw, 60, T.LINE, 0.7 * e4, radius=9)
            p.rect(mx + 1, cz + 1, mw - 2, 58, T.BG1, e4, radius=8)
            mono(p, mx + 18, cz + 24, "Type a message…   (Enter to send · "
                 "Shift+Enter newline · up-arrow history)", T.TEXT_DIM, 9.5, 0.2,
                 e4 * 0.9)
            _ic_clip(p, mx + 22, cz + 44, 6.5, T.TEXT_SOFT, e4 * 0.8)
            p.rect(mx + 38, cz + 38, 30, 13, T.BRAND_C, e4 * 0.70, radius=6.5)
            p.dot(mx + 61, cz + 44.5, 4.6, T.WHITE, e4 * 0.95)
            mono(p, mx + 76, cz + 48, "Auto-confirm", T.TEXT_SOFT, 9.5, 0.3,
                 e4 * 0.9)
            p.rect(mx + mw - 96, cz + 34, 80, 24, T.BRAND_C, e4 * 0.20, radius=6)
            p.rect(mx + mw - 96, cz + 34, 1.8, 24, T.BRAND_C, e4 * 0.85, radius=0.9)
            mono(p, mx + mw - 82, cz + 50, "Send", T.BRAND_BR, 10.0, 0.4, e4)
            _ic_enter(p, mx + mw - 46, cz + 45, 6.5, T.GREY, e4 * 0.8)

        # --- status bar
        p.rect(fx + 1, byy, fw - 2, self.ST - 1, T.BG0, 0.95 * e)
        hair(p, fx, byy, fx + fw, T.LINE, 0.9 * e)
        p.dot(fx + 18, byy + 17, 3.4, T.WARN, e * 0.95)
        mono(p, fx + 28, byy + 21, "deepseek-flash", T.WHITE, 9.5, 0.4, e * 0.95)
        mono(p, fx + 142, byy + 21, "F:\\one-cedric3", T.GREY_D, 9.5, 0.4, e * 0.9)
        mono(p, CX, byy + 21, "ready", T.GREY, 9.5, 0.4, e * 0.85, "ms")
        mono(p, fx + fw - 156, byy + 21, "6 sessions", T.GREY_D, 9.5, 0.4,
             e * 0.85, "rs")
        chip(p, fx + fw - 144, byy + 6, 132, 22, "ctrl+p  commands", T.TEXT_SOFT,
             F.mono(9.0), e * 0.9)
        p.pop()
        c.commit()



# --------------------------------------------------------------------------
# 07 / STUDENT BUILT — who made this
# --------------------------------------------------------------------------
class Student:
    def __init__(self):
        self.rng = np.random.default_rng(2011)

    def render(self, c, tl, t):
        c.clear(T.INK)
        plate(c, 300, T.BRAND_C, 0.050, 700, 240)
        p = c.pass_()
        dotfield(p, T.BG3, 0.15, 40.0)

        # --- the two hero lines, solved to the same measure so they justify
        # like a poster. Baselines come from the real cap metrics: a hard-coded
        # pair puts the kicker inside the first line's capitals.
        tr_ratio = T.TRACK_HERO / T.S_HERO
        hs = []
        for word in ("BUILT BY A", "HIGH SCHOOL STUDENT"):
            size = hero_size(word, W * 0.76, tr_ratio)
            f = F.display(size)
            hs.append((word, f, tr_ratio * size))

        y = 150.0
        places = []
        for word, f, tr in hs:
            ct, cb = F.cap_metrics(f)
            places.append((word, f, tr, y - ct))
            y += (cb - ct) + 20.0
        rule_y = y + 14.0
        handle_y = rule_y + 46.0
        grid_y = handle_y + 26.0

        e0 = A.out_expo(clip01((tl - 0.04) / 0.42), 4.0)
        if e0 > 0.01:
            mono(p, CX, 126, "A STUDENT PROJECT", T.BRAND_BR, T.S_TAG, 3.4,
                 e0 * 0.9, "ms")

        for k, (word, f, tr, base) in enumerate(places):
            t0 = 0.32 + k * 0.16
            e = A.out_expo(clip01((tl - t0) / 0.62), 3.4)
            if e <= 0.01:
                continue
            reveal(p, CX, base + (1.0 - e) * 26, word, f, T.WHITE, tr, "ms",
                   ease(tl, t0, 0.62), min(1.0, e * 1.6))

        rule = ease(tl, 0.66, 0.40)
        if rule > 0.001:
            w2 = F.measure(places[1][1], places[1][0], places[1][2])
            p.rect(CX - w2 / 2 * rule, rule_y, w2 * rule, 2.0, T.BRAND_C, 0.9)

        e1 = A.out_expo(clip01((tl - 0.80) / 0.42), 4.0)
        if e1 > 0.01:
            p.text(CX, handle_y, T.AUTHOR_HANDLE, F.display(22), T.BRAND_BR, 1.0,
                   "ms", e1)

        # --- a contribution grid, lit in the brand's own orange
        cols, rows = T.GRID_COLS, T.GRID_ROWS
        cw, chh, gpx, gpy = 18.0, 18.0, 5.0, 5.0
        total = cols * cw + (cols - 1) * gpx
        gx = CX - total / 2.0
        inten = self.rng.random((rows, cols))
        for r in range(rows):
            for k in range(cols):
                e = A.out_expo(clip01((tl - 0.86 - (k / cols) * 0.28
                                       - r * 0.014) / 0.28), 4.0)
                if e <= 0.01:
                    continue
                v = float(inten[r, k])
                col = T.BRAND_C if v > 0.34 else T.BG3
                a = (0.30 + 0.70 * v) * e
                p.rect(gx + k * (cw + gpx), grid_y + r * (chh + gpy), cw, chh,
                       col, a, radius=3.0)

        e2 = A.out_expo(clip01((tl - 1.30) / 0.42), 4.0)
        if e2 > 0.01:
            mono(p, CX, grid_y + rows * chh + (rows - 1) * gpy + 28.0,
                 f"{T.VERSION} · {T.LICENSE} · CONTRIBUTIONS WELCOME",
                 T.GREY, T.S_TAG, 2.0, e2 * 0.9, "ms")
        c.commit()


# --------------------------------------------------------------------------
# 08 / SIGN OFF — the lockup
# --------------------------------------------------------------------------
class SignOff:
    def __init__(self):
        self.frames = 0

    def render(self, c, tl, t):
        c.clear(T.INK)
        breath = 1.0 + 0.05 * np.sin(t * 1.7)
        plate(c, 340, T.BRAND_C, 0.060, 640, 128 * breath)
        plate(c, 320, T.BRAND_DK, 0.032, 940, 250)

        p = c.pass_()
        dotfield(p, T.BG3, 0.16, 40.0)
        # the two hairlines sit under the wordmark's baseline, not across its
        # caps: at 344 they cut the letters like a strike-through.
        for a, wd in ((0.10, 3.2), (0.05, 1.4)):
            p.line([(96, 398), (W - 96, 398)], T.BRAND_BR, wd,
                   a * (0.45 + 0.55 * min(1.0, tl / 0.9)) * breath)

        e0 = A.out_elastic(clip01((tl - 0.02) / 0.7), 0.34, 5.0)
        if e0 > 0.01:
            star(p, CX, 224, 28 * (0.55 + 0.45 * e0), T.BRAND_HOT,
                 e0 * (0.85 + 0.15 * np.sin(t * 4.0)), rot=e0 * 0.2 - 0.1)

        word = T.BRAND
        tr_ratio = T.TRACK_HERO / T.S_HERO
        size = hero_size(word, W * 0.72, tr_ratio)
        fh = F.display(size)
        tr = tr_ratio * size
        wm = F.measure(fh, word, tr)
        xm = CX - wm / 2.0
        xs = F.kerned_layout(fh, word, tr)
        for i, ch in enumerate(word):
            e = A.out_expo(clip01((tl - 0.14 - i * 0.040) / 0.56), 4.2)
            if e > 0.01 and ch != " ":
                p.text(xm + xs[i], 372 + (1.0 - e) * 70, ch, fh, T.WHITE, 0.0,
                       "lm", e)

        wipe = ease(tl, 0.56, 0.38)
        if wipe > 0.001:
            p.rect(CX - (wm / 2 + 9) * wipe, 412, wm * wipe + 18 * wipe, 2.4,
                   T.BRAND_C, 0.9)

        e1 = A.out_expo(clip01((tl - 0.70) / 0.45), 4.0)
        # the tagline, with the product's own mascot sitting at its right
        if e1 > 0.01:
            fs = F.mono(T.S_SUB)
            tw = F.measure(fs, T.TAGLINE, T.TRACK_SUB)
            mono(p, CX - 26, 462, T.TAGLINE, T.BRAND_BR, T.S_SUB, T.TRACK_SUB,
                 e1 * 0.95, "ms")
            eye = ["•", "•", "-", "•", "•", "•", "-", "•"][int(t * 2.86) % 8]
            tail = "~" if int(t * 5.5) % 2 == 0 else " "
            dog(p, CX - 26 + tw / 2 + 26, 466, 20.0, eye, tail, T.OK, e1 * 0.95)

        # --- the repo slug, in the product's own orange
        e2 = A.out_expo(clip01((tl - 0.88) / 0.45), 3.6)
        if e2 > 0.01:
            f = F.mono(16.0)
            url = "github.com/Aoan2011/One-Cedric"
            uw = F.measure(f, url, 1.6)
            bx = CX - uw / 2 - 46
            p.rect(bx, 500, uw + 92, 46, T.LINE, 0.85 * e2, radius=24)
            p.rect(bx + 1, 501, uw + 90, 44, T.BG1, e2, radius=23)
            star(p, bx + 30, 523, 8.0, T.BRAND_HOT, e2)
            p.text(bx + 48, 528, url, f, T.BRAND_BR, 1.6, "ls", e2)
            mono(p, CX, 566, "PYTHON 3.10+ · 240+ TOOLS · CLI + WEBUI · GPL-3.0",
                 T.GREY, T.S_TAG, 2.0, e2 * 0.85, "ms")

        # --- a last, quiet lift on the star as the bar ends
        ram = clip01((tl - 1.62) / 0.25)
        if ram > 0.01:
            p.rect(0, 0, W, H, T.BRAND_C, 0.045 * ram)
        c.commit()


SCENES = [Open, CliFrontend, ToolGrid, AnyModel, Sandboxed, WebUi, Student,
          SignOff]
