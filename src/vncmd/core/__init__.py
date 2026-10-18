"""底层：被上层所有模块依赖的那几个

config 与 output 是全局最底层的两个，被十个模块各自依赖。
它们之间有一处函数内导入 —— config._die 要用 output 的 console，
而 output 顶层已经导入了 config 的 is_artist_color，
所以那一处必须延迟，否则成环
"""
