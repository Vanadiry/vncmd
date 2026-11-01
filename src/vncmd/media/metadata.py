import datetime
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    TALB,
    TCOM,
    TDRL,
    TEXT,
    TIPL,
    TIT2,
    TPE1,
    TPE3,
    TPOS,
    TRCK,
    TXXX,
    USLT,
)
from mutagen.mp3 import MP3

from vncmd.media.lyrics import CREDIT_ROLES

# MP3 写法为帧 ID 或 TIPL 角色名
_CREDIT_FRAME_CLASSES = {"TCOM": TCOM, "TEXT": TEXT, "TPE3": TPE3}

# 自定义标签统一用小写，读取与写入都只认这个写法
TRACK_ID = "track_id"


def _music_type(path: str) -> str:
    """按后缀判断可写标签的音频格式"""
    suffix = Path(path).suffix.lower()
    if suffix in (".mp3", ".flac"):
        return suffix[1:]
    raise ValueError(f"不支持 track_id 的格式：{suffix or '无后缀'}")


def _read_track_id_mp3(tags) -> list[str]:
    if tags is None:
        return []
    return [
        frame.text[0]
        for frame in tags.getall("TXXX")
        if frame.desc == TRACK_ID and frame.text
    ]


def _read_track_id_flac(audio: FLAC) -> list[str]:
    return [str(value) for value in audio.get(TRACK_ID, [])]


def _read_info_mp3(tags) -> tuple[str, str, list[str]]:
    if tags is None:
        return "", "", []
    title_frames = tags.getall("TIT2")
    title = title_frames[0].text[0] if title_frames and title_frames[0].text else ""
    artists = [value for frame in tags.getall("TPE1") for value in (frame.text or [])]
    return title, ", ".join(artists), _read_track_id_mp3(tags)


def _read_info_flac(audio: FLAC) -> tuple[str, str, list[str]]:
    titles = audio.get("title", [])
    title = str(titles[0]) if titles else ""
    artists = [str(value) for value in audio.get("artist", [])]
    return title, ", ".join(artists), _read_track_id_flac(audio)


def read_track_info(path: str) -> tuple[str, str, list[str]]:
    """读取标题、艺术家与已有 track_id，支持 MP3 与 FLAC

    artist 多值时按上游习惯用逗号加空格拼接
    """
    music_type = _music_type(path)
    if music_type == "mp3":
        return _read_info_mp3(MP3(path).tags)
    return _read_info_flac(FLAC(path))


def read_track_id(path: str) -> list[str]:
    """读取文件里已有的 track_id，支持 MP3 与 FLAC

    返回列表而非单值，供后续回填工具识别重复标签
    """
    return read_track_info(path)[2]


def _write_track_id_mp3(tags, track_id: int | str) -> None:
    tags.setall(
        f"TXXX:{TRACK_ID}",
        [TXXX(encoding=3, desc=TRACK_ID, text=[str(track_id)])],
    )


def _write_track_id_flac(audio: FLAC, track_id: int | str) -> None:
    audio[TRACK_ID] = str(track_id)


def write_track_id(path: str, track_id: int | str) -> None:
    """把 track_id 写入 MP3 或 FLAC，重复值会被覆盖"""
    music_type = _music_type(path)
    if music_type == "mp3":
        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        _write_track_id_mp3(audio.tags, track_id)
    else:
        audio = FLAC(path)
        _write_track_id_flac(audio, track_id)
    audio.save()


def _set_text(tags, frame_id: str, frame_cls, text: str) -> None:
    # 先删再写，避免重试后留下重复帧
    tags.delall(frame_id)
    tags.add(frame_cls(encoding=3, text=[text]))


def _write_credits_mp3(tags, credits: dict[str, str]) -> None:
    # TIPL 只能 add 一次，所有角色攒进同一列表
    tipl: list[tuple[str, str]] = []
    for role, value in credits.items():
        how = CREDIT_ROLES[role][0]
        if how.startswith("TIPL:"):
            tipl.append((how.split(":", 1)[1], value))
            continue
        _set_text(tags, how, _CREDIT_FRAME_CLASSES[how], value)
    if tipl:
        tags.delall("TIPL")
        tags.add(TIPL(encoding=3, people=tipl))


def _embed_mp3(
    music_path: str,
    cover_data: bytes | None,
    cover_mime: str | None,
    lyric_text: str | None,
    song_title: str | None,
    song_artist: str | None,
    song_album: str | None,
    publish_time: str | None,
    track_no: int | None,
    cd_no: int | None,
    credits: dict[str, str] | None,
    track_id: int | None,
) -> None:
    try:
        audio = MP3(music_path)
    except Exception as e:
        raise ValueError(f"音频标签无法读取，文件可能不是 mp3：{music_path}") from e
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags

    if cover_data and cover_mime:
        tags.delall("APIC")
        tags.add(
            APIC(encoding=3, mime=cover_mime, type=3, desc="Cover", data=cover_data)
        )

    if lyric_text:
        tags.delall("USLT")
        tags.add(USLT(encoding=3, lang="chi", desc="", text=lyric_text))

    if song_title is not None:
        _set_text(tags, "TIT2", TIT2, song_title)
    if song_artist is not None:
        _set_text(tags, "TPE1", TPE1, song_artist)
    if song_album is not None:
        _set_text(tags, "TALB", TALB, song_album)
    if publish_time:
        try:
            pt = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        else:
            # 只写 TDRL，TDRC 为录制时间
            _set_text(tags, "TDRL", TDRL, pt.strftime("%Y-%m-%d"))

    if track_no is not None:
        _set_text(tags, "TRCK", TRCK, str(track_no))
    if cd_no is not None:
        _set_text(tags, "TPOS", TPOS, str(cd_no))

    if credits:
        _write_credits_mp3(tags, credits)
    if track_id is not None:
        _write_track_id_mp3(tags, track_id)

    audio.save()


def _embed_flac(
    music_path: str,
    cover_data: bytes | None,
    cover_mime: str | None,
    lyric_text: str | None,
    song_title: str | None,
    song_artist: str | None,
    song_album: str | None,
    publish_time: str | None,
    track_no: int | None,
    cd_no: int | None,
    credits: dict[str, str] | None,
    track_id: int | None,
) -> None:
    audio = FLAC(music_path)

    if cover_data and cover_mime:
        # 先清后加，避免重复嵌入封面
        audio.clear_pictures()
        pic = Picture()
        pic.type = 3
        pic.mime = cover_mime
        pic.data = cover_data
        audio.add_picture(pic)

    if lyric_text:
        audio["lyrics"] = lyric_text

    if song_title is not None:
        audio["title"] = song_title
    if song_artist is not None:
        audio["artist"] = song_artist
    if song_album is not None:
        audio["album"] = song_album
    if publish_time:
        try:
            pt = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        else:
            audio["date"] = pt.strftime("%Y-%m-%d")

    if track_no is not None:
        audio["tracknumber"] = str(track_no)
    if cd_no is not None:
        audio["discnumber"] = str(cd_no)

    if credits:
        for role, value in credits.items():
            audio[CREDIT_ROLES[role][1]] = value
    if track_id is not None:
        _write_track_id_flac(audio, track_id)

    audio.save()


def embed(
    music_path: str,
    music_type: str,
    cover_data: bytes | None,
    cover_mime: str | None,
    lyric_text: str | None,
    song_title: str | None,
    song_artist: str | None,
    song_album: str | None,
    publish_time: str | None,
    track_no: int | None = None,
    cd_no: int | None = None,
    credits: dict[str, str] | None = None,
    track_id: int | None = None,
) -> None:
    if music_type == "mp3":
        _embed_mp3(
            music_path,
            cover_data,
            cover_mime,
            lyric_text,
            song_title,
            song_artist,
            song_album,
            publish_time,
            track_no,
            cd_no,
            credits,
            track_id,
        )
    elif music_type == "flac":
        _embed_flac(
            music_path,
            cover_data,
            cover_mime,
            lyric_text,
            song_title,
            song_artist,
            song_album,
            publish_time,
            track_no,
            cd_no,
            credits,
            track_id,
        )
