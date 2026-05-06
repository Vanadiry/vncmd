import os

from function.config import (
    get_download_dir, get_download_content,
    get_embed_lyrics_mode, get_save_lyrics_mode,
    get_embed_cover_quality, get_save_cover_quality,
)
from function.audio import (
    get_type_from_url, cover_ext, build_filename, resolve_path,
)
from function.download import fetch_audio, fetch_cover, fetch_lyrics
from function.image import process_cover as process_cover_image
from function.lyrics import process as process_lyrics, output_files as output_lyrics_files
from function.metadata import embed as embed_metadata


def download_song(
    song_url,
    song_title,
    song_artist,
    song_album,
    song_id,
    cover_url,
    lyrics_api_url,
    publish_time,
    source="netease",
    download_dir=None,
):
    """
    Download a song with metadata, lyrics, and cover.

    Respects config: filename_format, download_content, lyrics_mode, cover_quality.
    Returns (success: bool, message: str, file_path: str | None)
    """
    if download_dir is None:
        download_dir = get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    content = get_download_content()
    want_song = "0" in content
    want_lyrics = "1" in content
    want_cover = "2" in content

    filename_base = build_filename(song_title, song_artist)

    # --- Fetch lyrics ---
    lyric_text, tlyric_text = "", ""
    if want_lyrics or want_song:
        if lyrics_api_url and source:
            lyric_text, tlyric_text = fetch_lyrics(lyrics_api_url, source)

    # --- Fetch and process cover ---
    cover_data = None
    if want_cover or want_song:
        cover_data = fetch_cover(cover_url)

    embed_cover_data, embed_cover_mime = None, None
    save_cover_data = None
    if cover_data:
        embed_cover_data, embed_cover_mime = process_cover_image(
            cover_data, cover_url, get_embed_cover_quality()
        )
        save_cover_data, _ = process_cover_image(
            cover_data, cover_url, get_save_cover_quality()
        )

    music_path, music_type = None, None
    lyric_paths = []
    cover_path = None

    # --- Download audio ---
    if want_song:
        music_type = get_type_from_url(song_url)
        music_path = resolve_path(filename_base, music_type, download_dir)
        label = f"{song_title} - {song_artist}"
        err = fetch_audio(song_url, music_path, label)
        if err:
            return False, f"Download failed: {err}", None
        if os.path.getsize(music_path) == 0:
            os.remove(music_path)
            return False, "Downloaded file is empty — likely VIP-only", None
        # Process lyrics for embedding
        embed_mode = get_embed_lyrics_mode()
        if embed_mode == "2" or not tlyric_text:
            embed_lyric = lyric_text
        else:
            embed_result = process_lyrics(lyric_text, tlyric_text, embed_mode, song_id)
            embed_lyric = "\n".join(embed_result.values())

        embed_metadata(
            music_path, music_type, embed_cover_data, embed_cover_mime,
            embed_lyric, song_id, song_title, song_artist,
            song_album, publish_time,
        )

    # --- Save lyrics ---
    if want_lyrics and lyric_text:
        save_mode = get_save_lyrics_mode()
        base_path = os.path.join(download_dir, filename_base)
        result = process_lyrics(lyric_text, tlyric_text, save_mode, song_id)
        lyric_paths = output_lyrics_files(result, base_path)

    # --- Save cover ---
    if want_cover and save_cover_data:
        ext = "jpg" if get_save_cover_quality() == "1" else cover_ext(cover_url)
        cover_path = resolve_path(filename_base, ext, download_dir)
        with open(cover_path, "wb") as f:
            f.write(save_cover_data)

    # --- Result ---
    parts = []
    if music_path:
        parts.append(f"{music_type.upper()} → {music_path}")
    for p in lyric_paths:
        parts.append(f"LRC → {p}")
    if cover_path:
        parts.append(f"Cover → {cover_path}")

    if not parts:
        return False, "Nothing was downloaded — check download_content config", None
    return True, "\n".join(parts), music_path
