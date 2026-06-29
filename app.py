import base64
import os
import re
import time
import unicodedata
from collections import defaultdict
from functools import wraps

import requests
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# =========================================================
# SOFIA MUSIC SUPREMO
# Cole aqui as tuas chaves se preferires não usar .env.
# Spotify: https://developer.spotify.com/dashboard
# YouTube: https://console.cloud.google.com/apis/library/youtube.googleapis.com
# =========================================================
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "COLOCA_AQUI_O_SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "COLOCA_AQUI_O_SPOTIFY_CLIENT_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "COLOCA_AQUI_A_YOUTUBE_API_KEY")

DEFAULT_MARKET = os.getenv("DEFAULT_MARKET", "PT")
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "40"))
REQUEST_TIMEOUT = 15
DEFAULT_COVER_URL = "/static/default-cover.svg"

# Países usados para construir um "top global" sem chave.
GLOBAL_COUNTRIES = ["us", "gb", "pt", "br", "es", "fr", "de", "it", "nl", "ca", "au", "jp", "mx", "ao", "mz"]

# Alguns géneros rápidos para Spotify. O utilizador pode escrever qualquer género no frontend.
SPOTIFY_GENRES = [
    "kizomba", "semba", "zouk", "afro house", "kuduro", "afrobeats", "amapiano",
    "funaná", "fado", "música portuguesa", "pop", "rock", "rap", "hip hop",
    "r&b", "dance", "reggaeton", "bachata", "sertanejo", "jazz", "reggae",
    "soul", "latin", "electronic", "house", "techno"
]

_cache = {}
_spotify_token = {"access_token": None, "expires_at": 0}


def cache(seconds=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (func.__name__, tuple(args), tuple(sorted(kwargs.items())), tuple(sorted(request.args.items())) if request else None)
            now = time.time()
            if key in _cache:
                expires, value = _cache[key]
                if now < expires:
                    return value
            value = func(*args, **kwargs)
            _cache[key] = (now + seconds, value)
            return value
        return wrapper
    return decorator


def clean_text(value):
    if not value:
        return ""
    value = str(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_key(text):
    text = clean_text(text).lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def high_res_artwork(url):
    if not url:
        return ""
    return url.replace("100x100", "600x600").replace("60x60", "600x600").replace("30x30", "600x600")


def cover_or_default(url):
    url = clean_text(url)
    return url or DEFAULT_COVER_URL


def is_configured(value):
    return bool(value and not value.startswith("COLOCA_AQUI"))


def spotify_headers():
    token = get_spotify_token()
    return {"Authorization": f"Bearer {token}"}


def get_spotify_token():
    if not is_configured(SPOTIFY_CLIENT_ID) or not is_configured(SPOTIFY_CLIENT_SECRET):
        raise RuntimeError("Falta configurar SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET.")

    now = time.time()
    if _spotify_token["access_token"] and now < _spotify_token["expires_at"] - 60:
        return _spotify_token["access_token"]

    auth = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
    basic = base64.b64encode(auth).decode("utf-8")
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    _spotify_token["access_token"] = data["access_token"]
    _spotify_token["expires_at"] = now + int(data.get("expires_in", 3600))
    return _spotify_token["access_token"]


def spotify_track_to_item(track, source="spotify"):
    artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
    album = track.get("album") or {}
    images = album.get("images") or []
    cover = images[0].get("url", "") if images else ""
    title = clean_text(track.get("name"))
    artist = clean_text(artists)
    return {
        "source": source,
        "title": title,
        "artist": artist,
        "album": clean_text(album.get("name")),
        "cover": cover_or_default(cover),
        "popularity": int(track.get("popularity") or 0),
        "spotify_url": ((track.get("external_urls") or {}).get("spotify")) or "",
        "itunes_url": "",
        "youtube_query": build_youtube_query(title, artist),
    }


def dedupe_items(items, limit=DEFAULT_LIMIT):
    seen = set()
    out = []
    for item in items:
        title = clean_text(item.get("title"))
        artist = clean_text(item.get("artist"))
        if not title or not artist:
            continue
        key = normalize_key(f"{artist}-{title}")
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def build_youtube_query(title, artist):
    title = clean_text(title)
    artist = clean_text(artist)
    # "official audio" costuma dar menos vídeos bloqueados do que live/remix/letras aleatórias.
    return f"{artist} {title} official audio"


@app.route("/")
def index():
    return render_template("index.html", spotify_genres=SPOTIFY_GENRES, default_genre="kizomba")


@app.route("/api/status")
def api_status():
    return jsonify({
        "ok": True,
        "spotify_configured": is_configured(SPOTIFY_CLIENT_ID) and is_configured(SPOTIFY_CLIENT_SECRET),
        "youtube_configured": is_configured(YOUTUBE_API_KEY),
        "default_market": DEFAULT_MARKET,
    })


@app.route("/api/spotify/genre")
@cache(seconds=600)
def api_spotify_genre():
    genre = clean_text(request.args.get("genre") or "kizomba")
    market = clean_text(request.args.get("market") or DEFAULT_MARKET).upper()
    limit = min(int(request.args.get("limit") or DEFAULT_LIMIT), 50)

    try:
        items = fetch_spotify_genre_tracks(genre, market=market, limit=limit)
        return jsonify({"ok": True, "source": "spotify", "mode": "genre", "genre": genre, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "items": []}), 500


@app.route("/api/spotify/search")
@cache(seconds=300)
def api_spotify_search():
    query = clean_text(request.args.get("q") or "")
    market = clean_text(request.args.get("market") or DEFAULT_MARKET).upper()
    limit = min(int(request.args.get("limit") or DEFAULT_LIMIT), 50)
    if not query:
        return jsonify({"ok": False, "error": "Escreve o nome da música, artista ou playlist.", "items": []}), 400

    try:
        items = fetch_spotify_search(query, market=market, limit=limit)
        return jsonify({"ok": True, "source": "spotify", "mode": "search", "query": query, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "items": []}), 500


def fetch_spotify_genre_tracks(genre, market="PT", limit=40):
    # 1) Pesquisa por filtro de género; 2) fallback por texto normal.
    queries = [f'genre:"{genre}"', genre, f"top {genre}", f"best {genre}"]
    found = []
    for q in queries:
        response = requests.get(
            "https://api.spotify.com/v1/search",
            headers=spotify_headers(),
            params={"q": q, "type": "track", "market": market, "limit": 50},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        tracks = response.json().get("tracks", {}).get("items", [])
        found.extend(spotify_track_to_item(t, source="spotify") for t in tracks)

    # Ordena por popularidade para ficar com ar de TOP.
    found.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return dedupe_items(found, limit=limit)


def fetch_spotify_search(query, market="PT", limit=40):
    response = requests.get(
        "https://api.spotify.com/v1/search",
        headers=spotify_headers(),
        params={"q": query, "type": "track", "market": market, "limit": 50},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    tracks = response.json().get("tracks", {}).get("items", [])
    items = [spotify_track_to_item(t, source="spotify") for t in tracks]
    items.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return dedupe_items(items, limit=limit)


@app.route("/api/itunes/top")
@cache(seconds=900)
def api_itunes_top():
    country = clean_text(request.args.get("country") or "pt").lower()
    limit = min(int(request.args.get("limit") or DEFAULT_LIMIT), 50)
    genre_id = clean_text(request.args.get("genre_id") or "")
    try:
        if genre_id:
            items = fetch_itunes_top_by_genre(country=country, genre_id=genre_id, limit=limit)
        else:
            items = fetch_apple_music_top(country=country, limit=limit)
        return jsonify({"ok": True, "source": "itunes", "country": country, "genre_id": genre_id, "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "items": []}), 500


@app.route("/api/itunes/global")
@cache(seconds=1200)
def api_itunes_global():
    limit = min(int(request.args.get("limit") or DEFAULT_LIMIT), 50)
    try:
        items = fetch_global_apple_top(limit=limit)
        return jsonify({"ok": True, "source": "itunes", "country": "global", "items": items})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "items": []}), 500


@app.route("/api/itunes/genres")
@cache(seconds=86400)
def api_itunes_genres():
    try:
        genres = fetch_itunes_genres()
        return jsonify({"ok": True, "genres": genres})
    except Exception as exc:
        # Fallback manual para não deixar a app morta se a Apple falhar.
        fallback = [
            {"id": "14", "name": "Pop"}, {"id": "18", "name": "Hip-Hop/Rap"},
            {"id": "21", "name": "Rock"}, {"id": "15", "name": "R&B/Soul"},
            {"id": "17", "name": "Dance"}, {"id": "12", "name": "Latino"},
            {"id": "19", "name": "World"}, {"id": "20", "name": "Alternative"},
        ]
        return jsonify({"ok": True, "warning": str(exc), "genres": fallback})


def apple_music_feed_url(country="pt", limit=50):
    return f"https://rss.applemarketingtools.com/api/v2/{country}/music/most-played/{limit}/songs.json"


def fetch_apple_music_top(country="pt", limit=40):
    url = apple_music_feed_url(country=country, limit=min(max(limit, 10), 50))
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "SofiaMusicSupremo/1.0"})
    response.raise_for_status()
    data = response.json()
    results = data.get("feed", {}).get("results", [])
    items = []
    for idx, item in enumerate(results, start=1):
        title = clean_text(item.get("name"))
        artist = clean_text(item.get("artistName"))
        items.append({
            "source": "itunes",
            "rank": idx,
            "title": title,
            "artist": artist,
            "album": "",
            "cover": cover_or_default(high_res_artwork(item.get("artworkUrl100", ""))),
            "popularity": max(0, 101 - idx),
            "spotify_url": "",
            "itunes_url": item.get("url", ""),
            "youtube_query": build_youtube_query(title, artist),
        })
    return dedupe_items(items, limit=limit)


def fetch_global_apple_top(limit=40):
    scores = defaultdict(lambda: {"score": 0, "countries": set(), "best_rank": 999, "item": None})
    for country in GLOBAL_COUNTRIES:
        try:
            country_items = fetch_apple_music_top(country=country, limit=50)
        except Exception:
            continue
        for item in country_items:
            key = normalize_key(f"{item.get('artist')}-{item.get('title')}")
            rank = int(item.get("rank") or 50)
            # Mais pontos se aparece alto e em vários países.
            points = max(1, 60 - rank)
            scores[key]["score"] += points
            scores[key]["countries"].add(country.upper())
            scores[key]["best_rank"] = min(scores[key]["best_rank"], rank)
            if scores[key]["item"] is None or rank < int(scores[key]["item"].get("rank") or 999):
                scores[key]["item"] = dict(item)

    ranked = []
    for data in scores.values():
        item = data["item"]
        item["global_score"] = data["score"] + (len(data["countries"]) * 8)
        item["countries"] = sorted(data["countries"])
        item["rank"] = data["best_rank"]
        ranked.append(item)
    ranked.sort(key=lambda x: (x.get("global_score", 0), len(x.get("countries", []))), reverse=True)
    return dedupe_items(ranked, limit=limit)


def fetch_itunes_top_by_genre(country="pt", genre_id="14", limit=40):
    # Endpoint antigo do iTunes RSS ainda funciona em muitos países/géneros.
    url = f"https://itunes.apple.com/{country}/rss/topsongs/limit={min(max(limit, 10), 100)}/genre={genre_id}/json"
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "SofiaMusicSupremo/1.0"})
    response.raise_for_status()
    data = response.json()
    entries = data.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]
    items = []
    for idx, entry in enumerate(entries, start=1):
        title = clean_text((entry.get("im:name") or {}).get("label"))
        artist = clean_text((entry.get("im:artist") or {}).get("label"))
        images = entry.get("im:image") or []
        cover = images[-1].get("label", "") if images else ""
        link = entry.get("link") or {}
        if isinstance(link, list):
            link = link[0] if link else {}
        href = ((link.get("attributes") or {}).get("href")) if isinstance(link, dict) else ""
        items.append({
            "source": "itunes",
            "rank": idx,
            "title": title,
            "artist": artist,
            "album": clean_text((entry.get("im:collection") or {}).get("im:name", {}).get("label", "") if isinstance(entry.get("im:collection"), dict) else ""),
            "cover": cover_or_default(high_res_artwork(cover)),
            "popularity": max(0, 101 - idx),
            "spotify_url": "",
            "itunes_url": href,
            "youtube_query": build_youtube_query(title, artist),
        })
    return dedupe_items(items, limit=limit)


def fetch_itunes_genres():
    # id=34 é Music no mapa de géneros do iTunes.
    url = "https://itunes.apple.com/WebObjects/MZStoreServices.woa/ws/genres?id=34"
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "SofiaMusicSupremo/1.0"})
    response.raise_for_status()
    data = response.json()
    music = data.get("34", {})
    genres_map = music.get("subgenres", {}) or {}
    genres = []
    for gid, info in genres_map.items():
        genres.append({"id": str(gid), "name": clean_text(info.get("name"))})
        for sub_id, sub_info in (info.get("subgenres", {}) or {}).items():
            genres.append({"id": str(sub_id), "name": f"{clean_text(info.get('name'))} / {clean_text(sub_info.get('name'))}"})
    genres.sort(key=lambda x: x["name"].lower())
    return genres


@app.route("/api/youtube/search")
@cache(seconds=86400)
def api_youtube_search():
    query = clean_text(request.args.get("q") or "")
    if not query:
        return jsonify({"ok": False, "error": "Falta q", "video": None}), 400

    try:
        video = search_youtube_official(query)
        return jsonify({"ok": True, "video": video})
    except Exception as official_error:
        # Fallback opcional: usa yt-dlp apenas para encontrar ID, não para descarregar áudio.
        try:
            video = search_youtube_ytdlp(query)
            return jsonify({"ok": True, "video": video, "warning": f"YouTube API falhou, usei fallback: {official_error}"})
        except Exception as fallback_error:
            return jsonify({
                "ok": False,
                "error": f"Não encontrei vídeo no YouTube. API: {official_error}; fallback: {fallback_error}",
                "video": None,
            }), 500


def search_youtube_official(query):
    if not is_configured(YOUTUBE_API_KEY):
        raise RuntimeError("Falta configurar YOUTUBE_API_KEY.")
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoEmbeddable": "true",
            "safeSearch": "none",
            "maxResults": 5,
            "key": YOUTUBE_API_KEY,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("items", [])
    if not items:
        raise RuntimeError("sem resultados embeddable")

    # Preferir resultados com audio/official no título.
    def score(item):
        title = item.get("snippet", {}).get("title", "").lower()
        s = 0
        for word in ["official audio", "audio", "official", "visualizer", "lyrics"]:
            if word in title:
                s += 5
        for bad in ["live", "reaction", "cover", "karaoke", "instrumental"]:
            if bad in title:
                s -= 4
        return s

    best = sorted(items, key=score, reverse=True)[0]
    snippet = best.get("snippet", {})
    video_id = best.get("id", {}).get("videoId")
    if not video_id:
        raise RuntimeError("resultado sem videoId")
    thumbs = snippet.get("thumbnails", {})
    thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {"id": video_id, "title": clean_text(snippet.get("title")), "channel": clean_text(snippet.get("channelTitle")), "thumbnail": thumb}


def search_youtube_ytdlp(query):
    try:
        import yt_dlp
    except Exception as exc:
        raise RuntimeError("yt-dlp não instalado") from exc

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": True,
        "default_search": "ytsearch5",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch5:{query}", download=False)
    entries = info.get("entries") or []
    if not entries:
        raise RuntimeError("sem resultados yt-dlp")
    best = entries[0]
    video_id = best.get("id")
    if not video_id:
        url = best.get("url", "")
        match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", url)
        video_id = match.group(1) if match else url
    return {"id": video_id, "title": clean_text(best.get("title")), "channel": clean_text(best.get("uploader") or best.get("channel")), "thumbnail": best.get("thumbnail", "")}


@app.errorhandler(404)
def not_found(_):
    return jsonify({"ok": False, "error": "Rota não encontrada"}), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "1") == "1")
