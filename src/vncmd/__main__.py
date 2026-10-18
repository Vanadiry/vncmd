"""让 python -m vncmd 能跑

原先那个入口是仓库根目录的 vncmd.py，与 vncmd 包同名。Python 解析同名
时包优先于模块，装完之后 `import vncmd` 拿到的是包，而包里没有 main，
控制台入口会直接坏掉。main 因此搬进 vncmd.cli，这里只做转发
"""

from vncmd.cli import main

if __name__ == "__main__":
    main()
