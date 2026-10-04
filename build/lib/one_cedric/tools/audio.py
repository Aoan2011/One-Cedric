"""音频处理：ffmpeg 封装。

依赖：ffmpeg / ffprobe
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .sandbox import _as_int, _resolve_path


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or ""


def _ffprobe() -> str:
    return shutil.which("ffprobe") or ""


def _check_deps() -> str:
    if not _ffmpeg():
        return "ERROR: 需要 ffmpeg（winget/brew/apt install ffmpeg）"
    return ""


def audio_probe(path: str, root: Path) -> str:
    err = _check_deps()
    if err:
        return err
    p, perr = _resolve_path(root, path)
    if perr:
        return perr
    if not p.exists():
        return f"ERROR: 文件不存在: {path}"

    try:
        r = subprocess.run(
            [_ffprobe(), "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(p)],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[:300]}"

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return "ERROR: 无法解析 ffprobe 输出"

    fmt = data.get("format", {})
    audio_streams = [s for s in data.get("streams", [])
                     if s.get("codec_type") == "audio"]

    lines = [
        f"文件: {p.name}",
        f"容器: {fmt.get('format_long_name', '?')}",
        f"时长: {float(fmt.get('duration', 0)):.2f}s",
        f"大小: {int(fmt.get('size', 0))} bytes",
        f"码率: {int(fmt.get('bit_rate', 0)) // 1000} kbps",
        f"音轨数: {len(audio_streams)}",
        "",
    ]
    for i, s in enumerate(audio_streams):
        lines.append(f"音轨 #{i}")
        lines.append(f"  编解码: {s.get('codec_name', '?')}")
        lines.append(f"  采样率: {s.get('sample_rate')} Hz")
        lines.append(f"  声道: {s.get('channels')}")
        lines.append("")
    return "\n".join(lines)


def audio_convert(path: str, out: str = "", fmt: str = "mp3",
                  bitrate: str = "192k", sample_rate: int = 0,
                  channels: int = 0, root: Path | None = None):
    err = _check_deps()
    if err:
        return "", False, err
    if root is None:
        return "", False, "ERROR: 需要 root"

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}.{fmt}"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    lines = [f"源: {p.relative_to(root)}",
             f"输出: {out_p.relative_to(root)}",
             f"格式: {fmt}  码率: {bitrate}"]
    if sample_rate:
        lines.append(f"采样率: {sample_rate}")
    if channels:
        lines.append(f"声道: {channels}")
    return "\n".join(lines), True, ""


def audio_convert_apply(path, out, fmt, bitrate, sample_rate, channels,
                        root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    codec_map = {"mp3": "libmp3lame", "aac": "aac", "m4a": "aac",
                 "wav": "pcm_s16le", "flac": "flac", "ogg": "libvorbis",
                 "opus": "libopus"}
    codec = codec_map.get(fmt.lower(), "copy")

    args = [_ffmpeg(), "-y", "-i", str(p), "-vn", "-c:a", codec]
    if codec not in ("copy", "pcm_s16le", "flac"):
        args += ["-b:a", bitrate or "192k"]
    if sample_rate:
        args += ["-ar", str(_as_int(sample_rate, 44100))]
    if channels:
        args += ["-ac", str(_as_int(channels, 2))]
    args.append(str(out_p))

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-400:]}"
    return f"已转换 → {out_p.relative_to(root)}"


def audio_clip(path: str, out: str = "", start: str = "",
               duration: str = "", end: str = "",
               root: Path | None = None):
    err = _check_deps()
    if err:
        return "", False, err
    if root is None:
        return "", False, "ERROR: 需要 root"

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"
    if not start:
        return "", False, "ERROR: 需要 start（如 00:01:30）"

    if not out:
        out = f"{p.stem}_clip{p.suffix}"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    time_range = f"起始 {start}"
    if duration:
        time_range += f"  时长 {duration}"
    if end:
        time_range += f"  结束 {end}"
    return (f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"时间: {time_range}"), True, ""


def audio_clip_apply(path, out, start, duration, end, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    args = [_ffmpeg(), "-y", "-ss", str(start), "-i", str(p)]
    if duration:
        args += ["-t", str(duration)]
    if end:
        args += ["-to", str(end)]
    args += ["-c", "copy", str(out_p)]

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-400:]}"
    return f"已剪辑 → {out_p.relative_to(root)}"


def audio_volume(path: str, out: str = "", db: float = 0.0,
                 percent: int = 0, normalize: bool = False,
                 root: Path | None = None):
    err = _check_deps()
    if err:
        return "", False, err
    if root is None:
        return "", False, "ERROR: 需要 root"

    p, perr = _resolve_path(root, path)
    if perr:
        return "", False, perr
    if not p.exists():
        return "", False, f"ERROR: 文件不存在: {path}"

    if not out:
        out = f"{p.stem}_vol{p.suffix}"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    if normalize:
        desc = "音量标准化"
    elif db:
        desc = f"音量 {'+' if db > 0 else ''}{db} dB"
    elif percent:
        desc = f"音量 {percent}%"
    else:
        return "", False, "ERROR: 需要 db / percent / normalize"

    return (f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"调整: {desc}"), True, ""


def audio_volume_apply(path, out, db, percent, normalize, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    if normalize:
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
    elif percent:
        factor = max(0.01, min(float(percent) / 100, 10.0))
        af = f"volume={factor}"
    else:
        af = f"volume={db}dB"

    args = [_ffmpeg(), "-y", "-i", str(p), "-af", af, str(out_p)]

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-400:]}"
    return f"已调整音量 → {out_p.relative_to(root)}"


def audio_concat(files: list, out: str = "", root: Path | None = None):
    err = _check_deps()
    if err:
        return "", False, err
    if root is None:
        return "", False, "ERROR: 需要 root"
    if not files or len(files) < 2:
        return "", False, "ERROR: 需要至少 2 个文件"

    checked = []
    for f in files:
        p, perr = _resolve_path(root, str(f))
        if perr:
            return "", False, perr
        if not p.exists():
            return "", False, f"ERROR: 文件不存在: {f}"
        checked.append(p)

    if not out:
        out = "concat.mp3"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    preview = [f"将拼接 {len(checked)} 个音频："]
    for c in checked:
        preview.append(f"  · {c.relative_to(root)}")
    preview.append(f"输出: {out_p.relative_to(root)}")
    return "\n".join(preview), True, ""


def audio_concat_apply(files, out, root) -> str:
    import tempfile
    paths = []
    for f in files:
        p, _ = _resolve_path(root, str(f))
        paths.append(p)

    out_p, _ = _resolve_path(root, out)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as tf:
        for p in paths:
            safe = str(p).replace("'", "'\\''")
            tf.write(f"file '{safe}'\n")
        list_file = tf.name

    try:
        args = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                "-i", list_file, "-c", "copy", str(out_p)]
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            args = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                    "-i", list_file, "-c:a", "libmp3lame",
                    "-b:a", "192k", str(out_p)]
            r = subprocess.run(args, capture_output=True, text=True,
                               timeout=600, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return f"ERROR: {r.stderr[-400:]}"
    finally:
        try:
            Path(list_file).unlink(missing_ok=True)
        except Exception:
            pass

    return f"已拼接 {len(paths)} 个音频 → {out_p.relative_to(root)}"