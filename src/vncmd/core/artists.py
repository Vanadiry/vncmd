"""艺术家数组的公共拼接规则"""

from collections.abc import Iterable


def join_artists(artists: Iterable[object] | None) -> str:
    """把 ARTIST 数组拼成文件名、匹配与单值标签使用的字符串"""
    if isinstance(artists, str) or not artists:
        return artists if isinstance(artists, str) else ""
    return ", ".join(str(artist) for artist in artists)
