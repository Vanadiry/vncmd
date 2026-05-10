# 其他

## 对于 macOS 的 Petrichor 播放器用户

Petrichor 目前使用“已知艺术家列表”模式匹配艺术家，这导致部分未在列表里的艺术家不能被正确读取，分类会有点问题。

你可以下载项目 [/tools/artists_gen.py](/tools/artists_gen.py)，在任意位置运行它。  
这会读取 `vncmd` 缓存中记录的艺术家列表，在 `artists_gen.py` 同目录下生成名为 `known_artists_DATE.txt` 的列表文件。

将这个文件放在 `/Applications/Petrichor.app/Contents/Resources` 目录中，程序就能正确识别艺术家了。

~~另外，Petrichor 播放器在处理“多个艺术家，且首位为 2 字以上汉字”的艺术家列表时会出问题，这不是 `vncmd` 的问题。~~  
这个 [Issue](https://github.com/kushalpandya/Petrichor/issues/280) 已经被修复了。  
