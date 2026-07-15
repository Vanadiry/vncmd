import datetime

import eyed3
from mutagen.flac import FLAC, Picture


def embed(
    music_path: str,
    music_type: str,
    cover_data: bytes | None,
    cover_mime: str | None,
    lyric_text: str | None,
    song_id: int | None,
    song_title: str | None,
    song_artist: str | None,
    song_album: str | None,
    publish_time: str | None,
) -> None:
    if music_type == "mp3":
        audio = eyed3.load(music_path)
        if audio.tag is None:
            audio.initTag()

        if cover_data and cover_mime:
            audio.tag.images.set(3, cover_data, cover_mime)

        if lyric_text:
            audio.tag.lyrics.set(lyric_text)

        if song_id is not None:
            audio.tag.copyright = str(song_id)
        if song_title is not None:
            audio.tag.title = song_title
        if song_artist is not None:
            audio.tag.artist = song_artist
        if song_album is not None:
            audio.tag.album = song_album
        if publish_time:
            try:
                pt = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                audio.tag.release_date = pt.strftime("%Y-%m-%d %H:%M:%S")
                audio.tag.recording_date = pt.strftime("%Y")
            except ValueError:
                pass

        audio.tag.save(encoding="utf-8")

    elif music_type == "flac":
        audio = FLAC(music_path)

        if cover_data and cover_mime:
            pic = Picture()
            pic.type = 3
            pic.mime = cover_mime
            pic.data = cover_data
            audio.add_picture(pic)

        if lyric_text:
            audio["lyrics"] = lyric_text

        if song_id is not None:
            audio["copyright"] = str(song_id)
        if song_title is not None:
            audio["title"] = song_title
        if song_artist is not None:
            audio["artist"] = song_artist
        if song_album is not None:
            audio["album"] = song_album
        if publish_time:
            try:
                pt = datetime.datetime.strptime(publish_time, "%Y-%m-%d %H:%M:%S")
                audio["date"] = pt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        audio.save()
