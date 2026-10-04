"""视频处理：ffmpeg 封装。

依赖：ffmpeg / ffprobe 在 PATH 中
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
        return ("ERROR: 需要 ffmpeg 命令\n"
                "  Windows: winget install ffmpeg\n"
                "  macOS: brew install ffmpeg\n"
                "  Linux: sudo apt install ffmpeg")
    return ""


def video_probe(path: str, root: Path) -> str:
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
        return f"ERROR: ffprobe 失败: {r.stderr[:300]}"

    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return f"ERROR: 无法解析 ffprobe 输出"

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    lines = [
        f"文件: {p.name}",
        f"容器: {fmt.get('format_long_name', fmt.get('format_name', '?'))}",
        f"时长: {float(fmt.get('duration', 0)):.2f}s",
        f"大小: {int(fmt.get('size', 0))} bytes",
        f"码率: {int(fmt.get('bit_rate', 0)) // 1000} kbps",
        "",
    ]

    for i, s in enumerate(streams):
        codec_type = s.get("codec_type", "?")
        lines.append(f"流 #{i} [{codec_type}]")
        if codec_type == "video":
            lines.append(f"  编解码: {s.get('codec_name', '?')}")
            lines.append(f"  分辨率: {s.get('width')} × {s.get('height')}")
            lines.append(f"  帧率: {s.get('r_frame_rate', '?')}")
        elif codec_type == "audio":
            lines.append(f"  编解码: {s.get('codec_name', '?')}")
            lines.append(f"  采样率: {s.get('sample_rate')} Hz")
            lines.append(f"  声道: {s.get('channels')}")
        lines.append("")

    return "\n".join(lines)


def video_convert(path: str, out: str = "", fmt: str = "mp4",
                  video_codec: str = "", audio_codec: str = "",
                  crf: int = 23, preset: str = "medium",
                  scale: str = "", bitrate: str = "",
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
        out = f"{p.stem}_converted.{fmt}"

    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    preview = [f"源: {p.relative_to(root)}",
               f"输出: {out_p.relative_to(root)}",
               f"格式: {fmt}"]
    if video_codec:
        preview.append(f"视频编解码: {video_codec}")
    if audio_codec:
        preview.append(f"音频编解码: {audio_codec}")
    preview.append(f"CRF: {crf}  preset: {preset}")
    if scale:
        preview.append(f"缩放: {scale}")
    if bitrate:
        preview.append(f"码率: {bitrate}")

    return "\n".join(preview), True, ""


def video_convert_apply(path, out, fmt, video_codec, audio_codec,
                        crf, preset, scale, bitrate, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    args = [_ffmpeg(), "-y", "-i", str(p)]
    if video_codec:
        args += ["-c:v", video_codec]
    if video_codec in ("libx264", "libx265", ""):
        args += ["-crf", str(max(0, min(_as_int(crf, 23), 51)))]
        args += ["-preset", preset or "medium"]
    if audio_codec:
        args += ["-c:a", audio_codec]
    if bitrate:
        args += ["-b:v", bitrate]
    vf = []
    if scale:
        vf.append(f"scale={scale}")
    if vf:
        args += ["-vf", ",".join(vf)]
    args.append(str(out_p))

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=3600, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "ERROR: 转码超时（>1h）"
    except OSError as exc:
        return f"ERROR: {exc}"

    if r.returncode != 0:
        return f"ERROR: ffmpeg 失败: {r.stderr[-500:]}"

    return (f"已转换 → {out_p.relative_to(root)}\n"
            f"{p.stat().st_size} → {out_p.stat().st_size} bytes")


def video_clip(path: str, out: str = "", start: str = "", duration: str = "",
               end: str = "", reencode: bool = False,
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
        return "", False, "ERROR: 需要 start（如 00:00:10 或 10.5）"

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
            f"时间: {time_range}\n"
            f"模式: {'重编码（精确）' if reencode else '流复制（快速）'}"), True, ""


def video_clip_apply(path, out, start, duration, end, reencode, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    args = [_ffmpeg(), "-y", "-ss", str(start), "-i", str(p)]
    if duration:
        args += ["-t", str(duration)]
    if end:
        args += ["-to", str(end)]
    if not reencode:
        args += ["-c", "copy"]
    args.append(str(out_p))

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=1800, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "ERROR: 剪辑超时"
    except OSError as exc:
        return f"ERROR: {exc}"

    if r.returncode != 0:
        return f"ERROR: ffmpeg 失败: {r.stderr[-500:]}"
    return f"已剪辑 → {out_p.relative_to(root)}"


def video_extract_audio(path: str, out: str = "", fmt: str = "mp3",
                        bitrate: str = "192k",
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
        out = f"{p.stem}.{fmt}"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"从 {p.relative_to(root)} 提取音轨\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"格式: {fmt}  码率: {bitrate}"), True, ""


def video_extract_audio_apply(path, out, fmt, bitrate, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    codec_map = {"mp3": "libmp3lame", "aac": "aac",
                 "wav": "pcm_s16le", "flac": "flac", "m4a": "aac"}
    codec = codec_map.get(fmt.lower(), "copy")

    args = [_ffmpeg(), "-y", "-i", str(p), "-vn",
            "-c:a", codec]
    if codec not in ("copy", "pcm_s16le", "flac"):
        args += ["-b:a", bitrate or "192k"]
    args.append(str(out_p))

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "ERROR: 提取超时"
    except OSError as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: ffmpeg 失败: {r.stderr[-500:]}"
    return f"已提取音轨 → {out_p.relative_to(root)}"


def video_thumbnail(path: str, out: str = "", time: str = "00:00:01",
                    width: int = 0,
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
        out = f"{p.stem}_thumb.jpg"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"截图 {p.relative_to(root)} 的 {time}\n"
            f"输出: {out_p.relative_to(root)}"
            + (f"  宽 {width}px" if width else "")), True, ""


def video_thumbnail_apply(path, out, time, width, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    args = [_ffmpeg(), "-y", "-ss", str(time), "-i", str(p), "-frames:v", "1"]
    if width:
        args += ["-vf", f"scale={width}:-1"]
    args.append(str(out_p))

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=120, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-300:]}"
    return f"已生成缩略图 → {out_p.relative_to(root)}"


def video_to_gif(path: str, out: str = "", start: str = "0",
                 duration: str = "3", fps: int = 12, width: int = 480,
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
        out = f"{p.stem}.gif"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"视频转 GIF\n"
            f"源: {p.relative_to(root)}\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"时段: {start} + {duration}s  FPS: {fps}  宽: {width}"), True, ""


def video_to_gif_apply(path, out, start, duration, fps, width, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)

    try:
        f = max(5, min(int(fps), 30))
        w = max(80, min(int(width), 1920))
    except (TypeError, ValueError):
        f, w = 12, 480

    filter_complex = (
        f"fps={f},scale={w}:-1:flags=lanczos,split[s0][s1];"
        f"[s0]palettegen[p];[s1][p]paletteuse"
    )
    args = [_ffmpeg(), "-y", "-ss", str(start), "-t", str(duration),
            "-i", str(p), "-vf", filter_complex, str(out_p)]

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=600, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-500:]}"
    return f"已生成 GIF → {out_p.relative_to(root)}"


def video_compress(path: str, out: str = "", crf: int = 28,
                   preset: str = "slow", target_height: int = 720,
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
        out = f"{p.stem}_compressed.mp4"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    return (f"压缩视频\n"
            f"源: {p.relative_to(root)}（{p.stat().st_size} bytes）\n"
            f"输出: {out_p.relative_to(root)}\n"
            f"CRF: {crf}  preset: {preset}  目标高度: {target_height}px"), True, ""


def video_compress_apply(path, out, crf, preset, target_height, root) -> str:
    p, _ = _resolve_path(root, path)
    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    args = [_ffmpeg(), "-y", "-i", str(p),
            "-c:v", "libx264",
            "-crf", str(max(18, min(_as_int(crf, 28), 35))),
            "-preset", preset or "slow"]
    if target_height:
        args += ["-vf", f"scale=-2:{_as_int(target_height, 720)}"]
    args += ["-c:a", "aac", "-b:a", "128k", str(out_p)]

    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           timeout=3600, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR: {exc}"
    if r.returncode != 0:
        return f"ERROR: {r.stderr[-500:]}"

    ratio = (1 - out_p.stat().st_size / p.stat().st_size) * 100
    return (f"已压缩 → {out_p.relative_to(root)}\n"
            f"{p.stat().st_size} → {out_p.stat().st_size} bytes"
            f"（减少 {ratio:.1f}%）")


def video_merge(files: list, out: str = "", root: Path | None = None):
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
        out = "merged.mp4"
    out_p, oerr = _resolve_path(root, out)
    if oerr:
        return "", False, oerr

    preview = [f"将合并 {len(checked)} 个视频："]
    for c in checked:
        preview.append(f"  · {c.relative_to(root)}")
    preview.append(f"输出: {out_p.relative_to(root)}")
    preview.append("模式: 重编码（所有文件统一编码）")
    return "\n".join(preview), True, ""


def video_merge_apply(files, out, root) -> str:
    import tempfile
    paths = []
    for f in files:
        p, _ = _resolve_path(root, str(f))
        paths.append(p)

    out_p, _ = _resolve_path(root, out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # 用 concat demuxer
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
                           timeout=1800, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            # 降级重编码
            args = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0",
                    "-i", list_file, "-c:v", "libx264", "-crf", "23",
                    "-c:a", "aac", str(out_p)]
            r = subprocess.run(args, capture_output=True, text=True,
                               timeout=3600, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return f"ERROR: {r.stderr[-500:]}"
    finally:
        try:
            Path(list_file).unlink(missing_ok=True)
        except Exception:
            pass

    return f"已合并 {len(paths)} 个视频 → {out_p.relative_to(root)}"