# OneCedric 工具全量冒烟测试报告

- 测试时间：2026-10-10（本机 Windows / Python 3.14 环境）
- 工具总数：**250**
- 统计：{"SKIP": 111, "OK": 85, "RUN-ERR": 30, "REG-ONLY": 24}

## 结论

通过本轮测试发现并修复了 **9 处真实 Bug**（详见「已修复 Bug」），其余未通过项均为**环境依赖**（缺第三方库 / 未安装外部工具 / 未配置服务），并非代码缺陷。安装对应依赖后即可工作。

## 已修复 Bug

| # | 工具 | Bug | 修复 |
|---|------|-----|------|
| 1 | pdf_extract | `ImportError: MAX_PDF_CHARS/MAX_PDF_PAGES` 在 config.py 中不存在 | 在 `config.py` 补充常量（40_000 / 50） |
| 2 | pdf_metadata（及全部 pdf_advanced 写工具） | `_pypdf()` 失败返回 `(None, err)`，调用点解包 `None` 抛 TypeError | `_pypdf()` 失败改为返回 `((None,None), err)` |
| 3 | archive | core 引用了不存在的 `archive_op_v2` / `tools.dev.archive_op` | 改走 `tools/archive.py` 的 `archive_op` + 新增 `archive_extract_apply` |
| 4 | git | `git_tool/_format_git_result` 不存在（`tools.dev` 导入失败） | 在 `git_snap.py` 实现 `git_tool` + `_format_git_result`，core 改导入 |
| 5 | file_attrs | `from .tools import file_attrs_preview` 等导入失败 | core 改从 `tools.fileattrs` 导入 |
| 6 | qrcode_wifi/vcard/email/sms/geo/styled | core 从 `one_cedric.tools` 导入不存在的 `qrcode_styled` 等 | core 改从 `tools.qrcode_advanced` 导入 |
| 7 | video_*/audio_*/pdf_*/compose_*/k8s_*/image_process/qrcode_*/symmetric_*/rsa_* | core 从 `one_cedric.tools` 导入不存在的函数 | `tools/__init__.py` 补齐全部 re-export |
| 8 | python_check / python_libs | schema 声明但**未注册任何 handler**，调用必报「未知工具」 | 在 `_handlers_readonly.py` 注册 + 加入 `TOOLS_READONLY` |
| 9 | file_attrs op=get/bulk | handler 未实现 get/bulk，掉进兜底被拒 | `_handle_file_attrs_tool` 增加 get/bulk 分支，`_dispatch_write_single` 全部路由到该 handler |

## 未通过项（均为环境依赖）

| 工具 | 原因 | 修复方式 |
|------|------|----------|
| web_search / web_research | 需要 beautifulsoup4 + lxml | `pip install beautifulsoup4 lxml` |
| json_schema_validate | 需要 jsonschema | `pip install jsonschema` |
| simplify_chinese | 需要 opencc | `pip install opencc-python-reimplemented` |
| pdf_extract / pdf_metadata | 需要 pypdf | `pip install pypdf` |
| qrcode_decode | 需要 Pillow | `pip install Pillow` |
| qrcode_generate/email/sms/geo/wifi/vcard/styled | 需要 qrcode[pil] | `pip install qrcode[pil]` |
| rsa_* / symmetric_* | 需要 cryptography | `pip install cryptography` |
| video_probe / audio_probe | 需要 ffmpeg | `winget install ffmpeg` |
| browser_extract / browser_url | 需要 playwright | `pip install playwright` + `playwright install` |
| lsp_* | 未配置 `~/.one-cedric/lsp.toml` | 按提示添加 [servers] 配置 |
| screen_info | Computer use 未启用 | 启动时加 `--computer-use` 或配置开启 |
| ruff_check / mypy_check | 未安装 ruff / mypy | `pip install ruff mypy` |
| timezone_convert | Windows 无 IANA 时区库 | `pip install tzdata` |

## 明细

### ✅ 通过（85）— 实际执行成功

`ansi_palette` `ansi_scan` `ansi_strip` `ansi_to_html` `apply_patch` `archive` `base64_codec` `bash` `bash_bg` `black_check` `calculate` `code_stats` `cron_next` `csv_query` `csv_to_json` `date_calc` `dedupe_lines` `diff_files` `disk_tree` `dns_lookup` `edit_file` `env_info` `eslint_check` `file_attrs` `file_info` `file_ops` `find_app` `find_duplicates` `find_replace` `get_public_ip` `git` `github_latest_version` `glob` `grep_regex` `hash_data` `hash_file` `hash_text` `http_head` `http_request` `image_info` `image_process` `json_diff` `json_format` `json_query` `json_to_csv` `jwt_decode` `list_apps` `list_files` `lsp_status` `markdown_toc` `md_to_html` `now_info` `ocr_image` `ocr_status` `password_gen` `pip_list` `pip_show` `process_info` `py_find_def` `py_imports` `py_outline` `py_unused_imports` `python_check` `python_exec` `python_libs` `random_bytes` `read_file` `regex_extract` `search_in_files` `sqlite` `sqlite_schema` `sqlite_tables` `ssl_check` `strip_invisible` `system_metrics` `template_render` `text_similarity` `text_stats` `todo` `tokenize` `url_codec` `weather` `web_fetch` `word_frequency` `write_file`

### ⚠️ 环境依赖（30）— 实际执行返回错误（多为缺少第三方库/服务/配置）

`audio_probe` `browser_extract` `browser_url` `json_schema_validate` `lsp_definition` `lsp_diagnostics` `lsp_hover` `lsp_references` `lsp_symbols` `mypy_check` `pdf_extract` `pdf_metadata` `qrcode_decode` `qrcode_email` `qrcode_generate` `qrcode_geo` `qrcode_sms` `qrcode_styled` `qrcode_vcard` `qrcode_wifi` `rsa_generate_keypair` `ruff_check` `screen_info` `simplify_chinese` `symmetric_decrypt` `symmetric_encrypt` `timezone_convert` `video_probe` `web_research` `web_search`

### ⏭️ 跳过（111）— 有副作用或依赖真实外部服务，未实际执行（已确认注册与参数检查）

`amap_around` `amap_bicycling` `amap_distance` `amap_district` `amap_driving` `amap_geocode` `amap_input_tips` `amap_ip_location` `amap_poi_detail` `amap_regeocode` `amap_search_poi` `amap_transit` `amap_walking` `amap_weather` `ask_user` `browser_click` `browser_close` `browser_nav` `browser_open` `browser_screenshot` `browser_type` `browser_wait` `budget_status` `compose_config` `compose_down` `compose_exec` `compose_logs` `compose_restart` `compose_status` `compose_up` `cost_anomaly` `cost_export` `cost_forecast` `cost_report` `cron_add` `cron_enable` `cron_list` `cron_logs` `cron_remove` `docker` `download` `download_info` `dream_list` `dream_read` `dream_run` `dream_stats` `email_accounts` `email_delete` `email_download_attachment` `email_list_attachments` `email_list_folders` `email_list_messages` `email_mark` `email_move` `email_pop_list` `email_pop_read` `email_read` `email_reply` `email_search` `email_send` `k8s_apply` `k8s_contexts` `k8s_delete` `k8s_describe` `k8s_exec` `k8s_get` `k8s_logs` `k8s_scale` `k8s_top` `keyboard_action` `locate_current` `locate_rough` `locate_set_exact` `memory_forget` `memory_list` `memory_recall` `memory_remember` `mongo_aggregate` `mongo_find` `mongo_list_collections` `mongo_list_databases` `mongo_stats` `mouse_action` `multi_review` `mysql_describe` `mysql_list_tables` `mysql_query` `notify` `notify_actions` `notify_check` `open_app` `ping_host` `pkg_install` `pkg_list_installed` `pkg_manager_info` `pkg_search` `pkg_uninstall` `port_scan` `postgres_describe` `postgres_list_tables` `postgres_query` `screen_capture` `spawn_agent` `sysop` `traceroute` `wechat_moments_post` `wechat_moments_read` `wechat_read_recent` `wechat_send` `wechat_status` `window_action`

### 🔒 仅注册（24）— 写工具，除白名单外未实跑（有副作用）

`audio_clip` `audio_concat` `audio_convert` `audio_volume` `black_format` `docx` `excel` `pdf` `pdf_add_page_numbers` `pdf_compress` `pdf_extract_images` `pdf_rotate` `pdf_watermark` `pptx` `qrcode_batch` `rsa_decrypt` `rsa_encrypt` `video_clip` `video_compress` `video_convert` `video_extract_audio` `video_merge` `video_thumbnail` `video_to_gif`

### ❓ 未分类（0）— 既不在只读也不在写集合（应为 schema 分类 bug，本轮已修）
