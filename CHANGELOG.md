# Changelog

## [0.2.3] - 2026-05-11

### Changed

- **默认配置目录路径**：从 `~/.vncmd` 迁移至 `~/.vSoft/vncmd`。
- **默认下载目录路径**：从 `~/Downloads/vncmd` 迁移至 `~/Downloads/vncmd-dl`。

## [0.2.2] - 2026-05-09

### Fixed

- **统一艺术家分隔符为逗号空格**：修复构建文件名和艺术家字段的方式，多个艺术家之间以 `, ` 分隔，播放器可正确拆分。
- **直接删除非法字符**：之前会将文件名的非法字符替换为 `-`，在部分播放器会被错误截断。因此现在直接删除非法字符。
- **下架歌曲 API 回退**：将之前 Tracker 使用的回退 API 添加到 `song` 命令中。现在可以用 `vncmd song` 来获取一部分下架曲目的信息了。

## [0.2.1] - 2026-05-09

### Fixed

- **修复歌单拉取不完整**：歌单 API 默认仅返回 10 首详情，改为 v6 接口 + `n` 参数一次性拉取全量。

### Added

- **下架曲目检测**：`vncmd playlist` 和 `vncmd tracker -f` 中自动检测并提醒已下架曲目。

## [0.2.0] - 2026-05-08

### Added

- 打包发布支持：`pyproject.toml`、`MANIFEST.in`

### Changed

- 移除 `requirements.txt`，统一使用 `pyproject.toml` 管理依赖
- 文档重构并添加英文翻译

## [0.1.0] - 2026-05-06

### Added

- 搜索、预览、下载单曲 / 歌单 / 专辑，支持多种音质
- Tracker：多来源歌单追踪，交互式冲突解决与自动同步，支持增量下载
- 断点续传与 dry-run 预览
- HTTP 自动重试
- `vncmd init` 配置初始化，Cookie 支持 VIP / 高音质
- 本地缓存：曲目详情与歌词
- 测试框架：pytest + pytest-cov + ruff
