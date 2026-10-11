"""tools 主入口（薄转发）。

职责：
  · re-export schema 常量
  · 转出 dispatch_tool 供 core 使用
  · 转出常用 helper（sandbox / normalize）

工具实现分散在各子模块，由 _dispatch.py 聚合。
"""
from __future__ import annotations

from .schema import (
    TOOLS, TOOLS_READONLY,
    READONLY_TOOL_NAMES, CACHEABLE_TOOLS, WRITE_TOOLS,
)
from .sandbox import (
    _resolve_path, _as_int,
    set_access_mode, get_access_mode,
)
from .normalize import prepare_tool_call
from ._dispatch import dispatch_tool, is_core_handled
from ..computer.tools import mouse_action, keyboard_action, window_action

# core 层写工具分发所需的 preview / apply 函数（跨模块再导出）
from .video import (
    video_convert, video_convert_apply,
    video_clip, video_clip_apply,
    video_extract_audio, video_extract_audio_apply,
    video_thumbnail, video_thumbnail_apply,
    video_to_gif, video_to_gif_apply,
    video_compress, video_compress_apply,
    video_merge, video_merge_apply,
)
from .audio import (
    audio_convert, audio_convert_apply,
    audio_clip, audio_clip_apply,
    audio_volume, audio_volume_apply,
    audio_concat, audio_concat_apply,
)
from .pdf_advanced import (
    pdf_watermark, pdf_watermark_apply,
    pdf_compress, pdf_compress_apply,
    pdf_extract_images, pdf_extract_images_apply,
    pdf_rotate, pdf_rotate_apply,
    pdf_add_page_numbers, pdf_add_page_numbers_apply,
    pdf_metadata, pdf_metadata_apply,
)
from .orchestration import (
    compose_up, compose_up_apply,
    compose_down, compose_down_apply,
    compose_restart, compose_restart_apply,
    compose_exec, compose_exec_apply,
    k8s_apply, k8s_apply_apply,
    k8s_delete, k8s_delete_apply,
    k8s_scale, k8s_scale_apply,
    k8s_exec, k8s_exec_apply,
)
from .image_ops import image_process, image_apply
from .qrcode_tool import qrcode_generate, qrcode_generate_apply
from .qrcode_advanced import (
    qrcode_styled, qrcode_styled_apply,
    qrcode_batch, qrcode_batch_apply,
    qrcode_wifi, qrcode_vcard, qrcode_email,
    qrcode_sms, qrcode_geo,
)
from .crypto import (
    symmetric_encrypt, symmetric_encrypt_apply,
    symmetric_decrypt, symmetric_decrypt_apply,
    rsa_generate_keypair, rsa_generate_keypair_apply,
    rsa_encrypt, rsa_encrypt_apply,
    rsa_decrypt, rsa_decrypt_apply,
)
from .fileattrs import (
    file_attrs_preview, file_attrs_apply,
    file_perms_preview, file_perms_apply,
    file_owner_preview, file_owner_apply,
)


__all__ = [
    "TOOLS", "TOOLS_READONLY",
    "READONLY_TOOL_NAMES", "CACHEABLE_TOOLS", "WRITE_TOOLS",
    "dispatch_tool", "is_core_handled",
    "prepare_tool_call",
    "_resolve_path", "_as_int",
    "set_access_mode", "get_access_mode",
    "mouse_action", "keyboard_action", "window_action",
    "video_convert", "video_convert_apply",
    "video_clip", "video_clip_apply",
    "video_extract_audio", "video_extract_audio_apply",
    "video_thumbnail", "video_thumbnail_apply",
    "video_to_gif", "video_to_gif_apply",
    "video_compress", "video_compress_apply",
    "video_merge", "video_merge_apply",
    "audio_convert", "audio_convert_apply",
    "audio_clip", "audio_clip_apply",
    "audio_volume", "audio_volume_apply",
    "audio_concat", "audio_concat_apply",
    "pdf_watermark", "pdf_watermark_apply",
    "pdf_compress", "pdf_compress_apply",
    "pdf_extract_images", "pdf_extract_images_apply",
    "pdf_rotate", "pdf_rotate_apply",
    "pdf_add_page_numbers", "pdf_add_page_numbers_apply",
    "pdf_metadata", "pdf_metadata_apply",
    "compose_up", "compose_up_apply",
    "compose_down", "compose_down_apply",
    "compose_restart", "compose_restart_apply",
    "compose_exec", "compose_exec_apply",
    "k8s_apply", "k8s_apply_apply",
    "k8s_delete", "k8s_delete_apply",
    "k8s_scale", "k8s_scale_apply",
    "k8s_exec", "k8s_exec_apply",
    "image_process", "image_apply",
    "qrcode_generate", "qrcode_generate_apply",
    "qrcode_styled", "qrcode_styled_apply",
    "qrcode_batch", "qrcode_batch_apply",
    "qrcode_wifi", "qrcode_vcard", "qrcode_email",
    "qrcode_sms", "qrcode_geo",
    "symmetric_encrypt", "symmetric_encrypt_apply",
    "symmetric_decrypt", "symmetric_decrypt_apply",
    "rsa_generate_keypair", "rsa_generate_keypair_apply",
    "rsa_encrypt", "rsa_encrypt_apply",
    "rsa_decrypt", "rsa_decrypt_apply",
    "file_attrs_preview", "file_attrs_apply",
    "file_perms_preview", "file_perms_apply",
    "file_owner_preview", "file_owner_apply",
]