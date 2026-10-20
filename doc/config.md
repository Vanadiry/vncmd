# 配置

配置文件存放在 `VNCMD_HOME/config.toml`。
Cookie 存放在 `VNCMD_HOME/cookie`，纯文本。

启动时会校验配置，不合法的配置会给出提示，未写出的配置项使用默认值。  
若配置文件不存在，会自动创建默认配置。  
同一时间只能运行一个 vncmd 实例。

程序已经提供了足够正常使用的默认配置，手动修改配置之前，请确保你了解每个配置的用途。

## 临时覆盖

`--config key=value` 可以临时改某一项配置，允许覆盖多个值。  
若要长期生效，请修改配置文件。

```bash
# 用例1：仅需要下载歌词
vncmd --config download.content=l song 2742965504

# 用例2：下载 320 kbps 音质，且变更下载路径
vncmd --config download.audio.quality=320 --config download.dir=/tmp song 2742965504
```

该参数为全局参数，需要在子命令之前使用。
`key` 使用完整的点号路径，例如 `[download.audio]` 段的 `quality`，为 `download.audio.quality`。
同一个键传两次时，后一个生效。

## [download]

### dir

下载目录。默认 `""`（空）。

支持绝对路径和基于 `~/.vSoft/vncmd` 的相对路径。留空则使用 `~/Downloads/vncmd-dl/`。

### filename_artist

艺术家在文件名里的位置。默认 `"back"`。

- `"back"`：曲目 - 艺术家
- `"front"`：艺术家 - 曲目
- `"drop"`：仅曲目

若有艺术家字段为空的曲目，则回退到 `drop`。

### content

下载内容。默认 `"alc"`。

- `"a"`：音频
- `"l"`：歌词
- `"c"`：封面

可以任意组合，任意顺序，例如 `"cl"` 表示只下载歌词和封面，`"a"` 表示只下载音频。

### concurrency

并发下载数。默认 `4`。

范围 1-16，过高可能触发风控。

### check

下载后做全量解码校验。默认 `true`。

开启后，会用 ffmpeg/flac 对音频完整解码，可以查出文件截断、容器损坏等不易发现的问题。  
需要系统中装有 ffmpeg/flac 工具。若部分或全部未安装，则会跳过对应校验。

### downloader

下载功能的实现方式。默认 `"builtin"`。

- `"builtin"`：使用内建下载实现
- `"curl"`：调用系统 curl

### curl_arg

追加给 curl 的参数。默认 `""`。

仅在 `downloader` 为 `"curl"` 时生效。  
按 shell 的切分规则解析，可以写多个参数。

## [download.audio]

### quality

音质。默认 `"max"`。

- `"128"`：128 kbps
- `"192"`：192 kbps
- `"320"`：320 kbps
- `"max"`：可用的最高音质

`max` 为服务端根据你 Cookie 所属账号的权限返回的可下载最高音质。  
若账号拥有 VIP 或已购买特定曲目/专辑，则设为 `max` 能够获取它们的 SQ/Hi-Res 无损音质（如有）。

### parse_credits

从歌词解析并嵌入更多元数据。默认 `false`。
（受到 `credit_scan_lines` 的行数限制）

启用（`true`）后，将自动从歌词头部解析 credit 数据，按对应格式的标准嵌入元数据。  
目前支持：作曲、作词、编曲、制作人、混音、录音、指挥（包括简中/繁中/部分英文）。

另外，以下一些连写情况会被特殊处理：

- `混音/母带`：记录混音，母带保留
- `作/編曲`、`作编曲`、`作曲/编曲`等：记录作曲和编曲

## [download.lyric]

### embed_mode

嵌入译文时，与原文的合并模式。默认 `"drop"`。

- `"line"`：交错。原文与译文逐行交错，匹配依赖时间戳，相差 300ms 以内的两句视为同一句
- `"block"`：拼接。译文流直接拼接在原文流下方
- `"drop"`：丢弃。仅嵌入原文流

### save_mode

保存嵌入译文时，与原文的合并模式。默认 `"line"`。

- `"line"`：交错。与 `embed_mode` 相同
- `"block"`：拼接。与 `embed_mode` 相同
- `"split"`：拆分。原文为 `.lrc`，译文为 `.2.lrc`
- `"drop"`：丢弃。仅保存原文流

若有不存在译文的曲目，则回退到 `drop`。

### auto_trim

裁剪无用歌词数据。默认 `false`。
（受到 `credit_scan_lines` 的行数限制）

启用后，会删除歌词中的以下内容：

- 整行为“纯音乐，请欣赏”的行
- 值为“无”的 credit 行，例如 `作词 : 无`
- 角色名为“歌词翻译”或“歌詞翻譯”的行

若同时启用 `parse_credits`，还会删除已被嵌入元数据的行。

如果裁剪完毕后，歌词中没有任何数据，将丢弃歌词。

### credit_scan_lines

扫描 credit 数据的行数。默认 `10`。在启用 `auto_trim` 或 `parse_credits` 时生效。

检测 `parse_credits` 或 `auto_trim` 中记录的要删除的行，只扫描前 N 行非元数据歌词。  
这能避免将正文中出现的角色关键词误判为 credit。

## [download.cover]

### embed_compress

嵌入音频的封面缩放。默认 `true`。

- `true`：等比缩放至 500px 以内（小图忽略），转换为 JPEG，透明通道替换为白色背景，质量自适应（60–85）。
- `false`：原图，不做任何处理。

### save_compress

独立封面文件缩放。默认 `false`。  
规则同 `embed_compress`。

## [cache]

### enabled

本地缓存。默认 `true`。

关闭后，歌词、曲目详情每次都会从 API 拉取，更慢但数据更新更及时。

### ttl

缓存有效期，单位为天。默认 `3`。

`0` 表示永不过期。

## [display]

### artist_color

艺术家按各自代表色着色。默认 `true`。

将展示的艺术家名字，按照 vncmd 内置的颜色对照表着色。  
目前收录类型有 Vocaloid、世界计划、VTuber等。
