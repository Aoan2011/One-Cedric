"""音量控制。"""
from __future__ import annotations

import re

from ._platform import IS_WINDOWS, IS_MAC, IS_LINUX, has_cmd, run_cmd, unsupported


def _win_get() -> str:
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        return "ERROR: 需要 pycaw（pip install pycaw）"
    try:
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        vol = volume.GetMasterVolumeLevelScalar()
        muted = volume.GetMute()
        pct = int(round(vol * 100))
        state = "已静音" if muted else "未静音"
        return f"音量: {pct}%（{state}）"
    except Exception as exc:
        return f"ERROR: 读取音量失败: {exc}"


def _win_set(value: int) -> str:
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        return "ERROR: 需要 pycaw"
    try:
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, value / 100.0)), None)
        return f"已设置音量: {value}%"
    except Exception as exc:
        return f"ERROR: 设置音量失败: {exc}"


def _win_mute(mute: bool) -> str:
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        return "ERROR: 需要 pycaw"
    try:
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        volume.SetMute(1 if mute else 0, None)
        return "已静音" if mute else "已取消静音"
    except Exception as exc:
        return f"ERROR: 操作失败: {exc}"


def _mac_get() -> str:
    rc, out, err = run_cmd(["osascript", "-e",
                            "output volume of (get volume settings)"])
    if rc != 0:
        return f"ERROR: {err}"
    return f"音量: {out.strip()}%"


def _mac_set(value: int) -> str:
    rc, out, err = run_cmd(["osascript", "-e",
                            f"set volume output volume {value}"])
    if rc != 0:
        return f"ERROR: {err}"
    return f"已设置音量: {value}%"


def _mac_mute(mute: bool) -> str:
    flag = "true" if mute else "false"
    rc, out, err = run_cmd(["osascript", "-e",
                            f"set volume output muted {flag}"])
    if rc != 0:
        return f"ERROR: {err}"
    return "已静音" if mute else "已取消静音"


def _linux_get() -> str:
    if has_cmd("pactl"):
        rc, out, _ = run_cmd(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        if rc == 0:
            m = re.search(r"(\d+)%", out)
            if m:
                rc2, out2, _ = run_cmd(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
                mute_state = "已静音" if "yes" in out2.lower() else "未静音"
                return f"音量: {m.group(1)}%（{mute_state}）"
    if has_cmd("amixer"):
        rc, out, _ = run_cmd(["amixer", "get", "Master"])
        if rc == 0:
            m = re.search(r"\[(\d+)%\]", out)
            if m:
                return f"音量: {m.group(1)}%"
    return unsupported("读取音量")


def _linux_set(value: int) -> str:
    if has_cmd("pactl"):
        rc, _, _ = run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"])
        if rc == 0:
            return f"已设置音量: {value}%"
    if has_cmd("amixer"):
        rc, _, _ = run_cmd(["amixer", "set", "Master", f"{value}%"])
        if rc == 0:
            return f"已设置音量: {value}%"
    return unsupported("设置音量")


def _linux_mute(mute: bool) -> str:
    flag = "1" if mute else "0"
    if has_cmd("pactl"):
        rc, _, _ = run_cmd(["pactl", "set-sink-mute", "@DEFAULT_SINK@", flag])
        if rc == 0:
            return "已静音" if mute else "已取消静音"
    if has_cmd("amixer"):
        rc, _, _ = run_cmd(["amixer", "set", "Master",
                            "mute" if mute else "unmute"])
        if rc == 0:
            return "已静音" if mute else "已取消静音"
    return unsupported("静音控制")


def volume_get() -> str:
    if IS_WINDOWS:
        return _win_get()
    if IS_MAC:
        return _mac_get()
    if IS_LINUX:
        return _linux_get()
    return unsupported("音量")


def volume_set(value) -> str:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "ERROR: value 必须是 0-100 的整数"
    if not 0 <= v <= 100:
        return "ERROR: 音量必须在 0-100"
    if IS_WINDOWS:
        return _win_set(v)
    if IS_MAC:
        return _mac_set(v)
    if IS_LINUX:
        return _linux_set(v)
    return unsupported("音量")


def volume_mute(mute: bool) -> str:
    if IS_WINDOWS:
        return _win_mute(mute)
    if IS_MAC:
        return _mac_mute(mute)
    if IS_LINUX:
        return _linux_mute(mute)
    return unsupported("静音")