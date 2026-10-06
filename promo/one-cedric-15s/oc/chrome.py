"""HUD chrome and finishing — One Cedric's frame furniture.

The furniture that turns eight unrelated shots into one reel: the ✦ cursor mark
plus the repo slug top-left, the version top-right, a running timecode, an
eight-dot scene indicator and a progress bar. Scenes draw their content; this
draws the frame around it.

`POST` holds the per-scene finishing settings and `finish()` walks the chain:
bloom -> chromatic aberration -> grade -> vignette -> cut flash -> grain ->
tone map. The cut flash goes in *after* the vignette, or its corners grey out
and a light burst reads as a grey wash.

Everything here is retuned from the template's green neon to One Cedric's warm
plate: the grade lifts red instead of blue, and the cut flash is brand orange.
"""
from __future__ import annotations

import numpy as np

from mg import fonts as F
from mg.core import corner_brackets

from . import scenes as SC
from . import theme as T

W, H = T.W, T.H
DOT_X, DOT_Y = W / 2.0, 604.0
BAR_Y = H - 4.0

# The two furniture colours. Cyan is the app's --accent and owns the HUD; the
# brand orange is reserved for content, so the frame never competes with a scene.
HUD_C = T.ACCENT
HUD_D = T.SLATE


def _tc(t):
    fr = int(round(t * T.FPS))
    return "TC %02d:%02d:%02d" % (fr // (T.FPS * 3600) % 100, fr // T.FPS % 60, fr % T.FPS)


def draw(p, t, scene_i, light=False):
    """The frame around every scene. `light` is accepted for API parity — this
    film is dark end to end."""
    ink = T.GREY
    dim = T.GREY_D
    acc = HUD_C

    # --- brand bug, top left: the ✦ cursor mark plus the repo slug
    SC.star(p, T.HUD_M + 5.0, T.HUD_TOP - 3.4, 6.2, T.BRAND_HOT,
            0.85 + 0.15 * np.sin(t * 3.1))
    p.text(T.HUD_M + 17, T.HUD_TOP, T.DOMAIN, F.mono(T.S_HUD), ink, T.TRACK_HUD)

    # --- version, top right
    p.text(W - T.HUD_M, T.HUD_TOP, f"{T.VERSION} // 15 SEC", F.mono(T.S_HUD), ink,
           T.TRACK_HUD, anchor="rs")

    # --- timecode, bottom left
    p.text(T.HUD_M, T.HUD_BOT, _tc(t), F.mono(T.S_HUD), ink, T.TRACK_HUD)

    # --- scene name, bottom right
    sid, sname, _ = T.SCENES[scene_i]
    wlab = p.text(W - T.HUD_M, T.HUD_BOT, f"SCENE {sid} / {sname}", F.mono(T.S_HUD),
                  ink, T.TRACK_HUD, anchor="rs")
    p.rect(W - T.HUD_M - wlab - 11, T.HUD_BOT - 3.0, 5, 5, T.BRAND_C, 0.9)

    # --- eight-dot indicator
    gap = 15.0
    x0 = DOT_X - gap * (T.BARS - 1) / 2.0
    for i in range(T.BARS):
        cx = x0 + i * gap
        if i == scene_i:
            p.rect(cx - 6.5, DOT_Y - 1.6, 13, 3.2, T.BRAND_C, 1.0, radius=1.6)
        elif i < scene_i:
            p.dot(cx, DOT_Y, 2.0, ink, 0.62)
        else:
            p.dot(cx, DOT_Y, 2.0, dim, 0.55)

    corner_brackets(p, W, H, acc, 26, 15, 0.34)

    # --- progress bar
    p.rect(0, BAR_Y, W, 3.0, dim, 0.30)
    prog = t / T.DUR
    p.rect(0, BAR_Y, W * prog, 3.0, grad=(T.BRAND_BR, T.BRAND_C))
    p.rect(W * prog - 1.5, BAR_Y - 1.0, 3.0, 5.0, T.WHITE, 0.85)

    # --- live status chip: the dog's idle green, so the frame echoes the mascot
    up = min(1.0, t / 0.35)
    if up > 0.01:
        p.dot(T.HUD_M + 4, T.HUD_BOT - 14, 3.0, T.OK,
              up * (0.55 + 0.45 * np.sin(t * 4.6)))
        p.text(T.HUD_M + 13, T.HUD_BOT - 11, "ONLINE", F.mono(T.S_MICRO), T.OK,
               T.TRACK_HUD, alpha=up * 0.85)


# --------------------------------------------------------------------------
# finishing — dark, warm, and quiet enough for UI legibility
# --------------------------------------------------------------------------
POST = {
    0: dict(bloom=(0.62, 0.30), chroma=1.0, vig=0.50, grain=0.0135, scan=0.010, k=1.00),
    1: dict(bloom=(0.66, 0.28), chroma=0.9, vig=0.46, grain=0.0128, scan=0.008, k=0.72),
    2: dict(bloom=(0.60, 0.32), chroma=1.1, vig=0.50, grain=0.0125, scan=0.008, k=0.66),
    3: dict(bloom=(0.58, 0.32), chroma=1.2, vig=0.52, grain=0.0130, scan=0.008, k=0.62),
    4: dict(bloom=(0.62, 0.30), chroma=1.0, vig=0.50, grain=0.0130, scan=0.009, k=0.64),
    5: dict(bloom=(0.70, 0.26), chroma=0.7, vig=0.42, grain=0.0110, scan=0.000, k=0.70),
    6: dict(bloom=(0.62, 0.30), chroma=1.0, vig=0.48, grain=0.0125, scan=0.008, k=0.66),
    7: dict(bloom=(0.64, 0.28), chroma=1.1, vig=0.46, grain=0.0125, scan=0.008, k=1.00),
}


def finish(c, t, scene_i):
    q = dict(POST[scene_i])
    q.update(getattr(c, "post_override", None) or {})

    c.bloom(thr=q["bloom"][0], knee=q["bloom"][1])
    c.chroma(q["chroma"])

    # Warm-to-brand grade: lift red, hold green, pull blue. The plate stays
    # near-black rather than navy, and the brand orange keeps its hue under
    # bloom instead of drifting pink the way a neutral grade makes it.
    c.rgb = c.rgb * np.asarray((1.015, 1.000, 0.988), np.float32).reshape(1, 1, 3)
    c.rgb = c.rgb + np.asarray((0.010, 0.007, 0.005), np.float32).reshape(1, 1, 3)
    l = c.rgb.mean(axis=2, keepdims=True)
    c.rgb = np.clip(l + (c.rgb - l) * 1.05, 0.0, 1.0)
    c.vignette(q["vig"], 1.7)

    # light-burst on every cut: the bar line is also the downbeat
    tl = t % T.BAR
    flash = q["k"] * np.exp(-tl / 0.055)
    if flash > 0.004:
        # a warm burst, not a neutral white one
        c.add += flash * np.asarray((1.00, 0.82, 0.66), np.float32).reshape(1, 1, 3)

    if q["scan"]:
        c.scanlines(q["scan"], 3)
    c.grain(q["grain"])
    c.tonemap(0.80)
    return c
