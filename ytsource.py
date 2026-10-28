# -*- coding: utf-8 -*-
"""
מקורות YouTube ל-MopVOD: בניית קטלוג לערוץ (כל פלייליסט = תוכנית, הסרטונים = פרקים) באותו מבנה JSON של כאן.

משמש בשני מקומות, ואותו קובץ בדיוק:
  - בריפו MopVOD: GitHub Actions מריץ `python ytsource.py --all` ומרענן את כל המקורות שב-sources.json
  - באפליקציית MopVODPlayer (windows/ytsource.py): הוספת מקור בונה את הקטלוג במחשב ומעלה אותו לריפו

קבצים בריפו:
  sources.json          רשימת המקורות: [{id, name, url}]
  youtube.json          אינדקס: [{id, name, url, logo, file, programs, episodes, updated}]
  vod/yt_<id>.json      קטלוג לכל מקור: {"name","url","logo","categories":[...]}

הפרקים שומרים את דף הסרטון ב-YouTube (לא קישור זרם, כי קישורי הזרם פגים). הנגן מפענח בזמן הניגון.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
SOURCES_FILE = "sources.json"
INDEX_FILE = "youtube.json"
VOD_SUBDIR = "vod"
MAX_VIDEOS_NO_PLAYLISTS = 300   # ערוץ בלי פלייליסטים: הסרטונים האחרונים


# ---------------------------------------------------------------- yt-dlp
def _ydl(flat=True, extra=None):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "ignoreerrors": True,
            "extract_flat": flat, "noplaylist": not flat}
    if extra:
        opts.update(extra)
    return yt_dlp.YoutubeDL(opts)


def best_thumb(entry):
    thumbs = entry.get("thumbnails") or []
    if thumbs:
        best = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
        return best.get("url") or ""
    return entry.get("thumbnail") or ""


def fmt_dur(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def source_id_for(url):
    m = re.search(r"/(channel|c|user)/([^/?#]+)", url) or re.search(r"/(@[^/?#]+)", url) or re.search(r"list=([^&]+)", url)
    raw = (m.group(m.lastindex) if m else url)
    return "yt_" + re.sub(r"[^A-Za-z0-9_@-]", "_", raw)[:60]


def search_channels(query, limit=10):
    """חיפוש ערוצים ב-YouTube לפי שם. כתובת YouTube שהודבקה מוחזרת כתוצאה אחת."""
    query = (query or "").strip()
    if not query:
        return []
    if re.match(r"https?://", query):
        info = _ydl(flat=True, extra={"playlistend": 1}).extract_info(query, download=False) or {}
        return [{"id": info.get("channel_id") or info.get("id") or query, "title": info.get("channel") or info.get("title") or query,
                 "url": info.get("channel_url") or info.get("uploader_url") or query,
                 "subscribers": info.get("channel_follower_count"), "kind": "channel" if info.get("channel_id") else "playlist"}]
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&sp=EgIQAg%253D%253D"
    info = _ydl(flat=True).extract_info(url, download=False) or {}
    out = []
    for e in (info.get("entries") or [])[:limit]:
        u = e.get("url") or e.get("channel_url") or ""
        if u and not u.startswith("http"):
            u = "https://www.youtube.com" + u
        if not u:
            continue
        out.append({"id": e.get("id") or u, "title": e.get("title") or e.get("channel") or u, "url": u,
                    "subscribers": e.get("channel_follower_count"), "kind": "channel"})
    return out


def _videos_to_episodes(entries):
    eps = []
    for e in entries:
        if not e or not e.get("id") or e.get("ie_key") not in (None, "Youtube"):
            continue
        vid = e.get("id")
        dur = e.get("duration")
        eps.append({
            "name": e.get("title") or vid,
            # כתובת תמונה יציבה (בלי חתימת sqp שמשתנה בכל קריאה, אחרת כל בנייה נראית כשינוי)
            "logo": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "date": None,
            "plot": e.get("description") or "",
            "page": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
            "id": vid,
            "duration": fmt_dur(dur) if dur else None,
            "resolve": "ytdlp",
        })
    return eps


def build_channel(url, title, status=None, max_playlists=None):
    """בונה קטלוג לערוץ/פלייליסט. status: dict שמתעדכן בהתקדמות (step, progress, cancel)."""
    status = status if status is not None else {}
    base = url.rstrip("/")
    is_playlist = "list=" in url
    categories = []
    now = time.strftime("%Y-%m-%d %H:%M")
    if is_playlist:
        status.update(step="קורא את הפלייליסט " + title)
        vi = _ydl(flat=True).extract_info(url, download=False) or {}
        eps = _videos_to_episodes(vi.get("entries") or [])
        if eps:
            categories.append({"name": vi.get("title") or title, "type": "vod", "source": "youtube", "resolve": "ytdlp",
                               "logo": best_thumb(vi) or eps[0]["logo"], "program_url": url, "updated": now,
                               "sub_categories": [{"name": "כל הפרקים", "channels": eps}]})
        return {"name": title, "url": url, "logo": best_thumb(vi), "categories": categories}

    status.update(step="קורא את רשימת הפלייליסטים של " + title)
    pl_info = _ydl(flat=True).extract_info(base + "/playlists", download=False) or {}
    playlists = [e for e in (pl_info.get("entries") or []) if e and e.get("url")]
    if max_playlists:
        playlists = playlists[:max_playlists]
    channel_thumb = best_thumb(pl_info)
    if playlists:
        total = len(playlists)
        for i, p in enumerate(playlists, 1):
            if status.get("cancel"):
                raise RuntimeError("בוטל")
            status.update(step=f"פלייליסט {i}/{total}: {p.get('title') or ''}", progress=i / total)
            vi = _ydl(flat=True).extract_info(p["url"], download=False) or {}
            eps = _videos_to_episodes(vi.get("entries") or [])
            if not eps:
                continue
            categories.append({
                "name": p.get("title") or ("פלייליסט " + str(i)),
                "type": "vod", "source": "youtube", "resolve": "ytdlp",
                "logo": best_thumb(p) or eps[0]["logo"],
                "program_url": p.get("url"),
                "updated": now,
                "sub_categories": [{"name": "כל הפרקים", "channels": eps}],
            })
    else:
        status.update(step="אין פלייליסטים, קורא את הסרטונים האחרונים של " + title)
        vi = _ydl(flat=True, extra={"playlistend": MAX_VIDEOS_NO_PLAYLISTS}).extract_info(base + "/videos", download=False) or {}
        eps = _videos_to_episodes(vi.get("entries") or [])
        if eps:
            categories.append({"name": "כל הסרטונים", "type": "vod", "source": "youtube", "resolve": "ytdlp",
                               "logo": channel_thumb, "program_url": base + "/videos", "updated": now,
                               "sub_categories": [{"name": "כל הפרקים", "channels": eps}]})
    return {"name": title, "url": url, "logo": channel_thumb, "categories": categories}


# ---------------------------------------------------------------- dates
# רשימות שטוחות של YouTube לא כוללות תאריך העלאה. משלימים אותו לכל סרטון בנפרד (yt-dlp, במקביל),
# שומרים בקטלוג, ובריצות הבאות רק פרקים חדשים נבדקים.
DATE_WORKERS = 8


def _episodes(data):
    for cat in data.get("categories", []):
        for sc in cat.get("sub_categories", []):
            for ep in sc.get("channels", []):
                yield ep


def carry_dates(old, new):
    """תאריכים (ותקצירים) שכבר ידועים מהקטלוג הקודם עוברים לקטלוג החדש לפי מזהה הפרק."""
    if not old:
        return 0
    known = {str(ep.get("id")): ep for ep in _episodes(old) if ep.get("date")}
    n = 0
    for ep in _episodes(new):
        o = known.get(str(ep.get("id")))
        if o:
            ep["date"] = o["date"]
            if o.get("plot") and not ep.get("plot"):
                ep["plot"] = o["plot"]
            n += 1
    return n


def _video_date(url):
    try:
        info = _ydl(flat=False, extra={"youtube_include_dash_manifest": False, "youtube_include_hls_manifest": False}).extract_info(url, download=False, process=False) or {}
    except Exception:  # noqa: BLE001
        return None, None
    d = info.get("upload_date") or info.get("release_date")
    return (f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else None), (info.get("description") or "")[:600]


def fill_dates(data, status=None, limit=None, workers=DATE_WORKERS):
    """משלים תאריך לפרקים שאין להם. limit = כמה לכל היותר בריצה הזו (הראשונים ברשימות = החדשים).
    מחזיר כמה הושלמו. נעצר אם 20 הניסיונות הראשונים נכשלו (למשל חסימה של YouTube לשרת)."""
    import concurrent.futures
    status = status if status is not None else {}
    todo = [ep for ep in _episodes(data) if not ep.get("date") and ep.get("url") and ep.get("resolve", "ytdlp") == "ytdlp"]
    if limit:
        todo = todo[:limit]
    if not todo:
        return 0
    done = ok = 0
    total = len(todo)
    status.update(step=f"משלים תאריכים 0/{total}", progress=0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(_video_date, ep["url"]): ep for ep in todo}
        for fut in concurrent.futures.as_completed(futures):
            ep = futures[fut]
            date, plot = fut.result()
            done += 1
            if date:
                ep["date"] = date
                if plot and not ep.get("plot"):
                    ep["plot"] = plot
                ok += 1
            if done % 25 == 0 or done == total:
                status.update(step=f"משלים תאריכים {done}/{total}", progress=done / total)
            if status.get("cancel"):
                break
            if done >= 20 and ok == 0:
                status.update(step="השלמת תאריכים נעצרה: YouTube לא עונה לבקשות הבודדות (ימולא בריצה הבאה)")
                break
    return ok


def sort_by_date(data):
    """בכל תוכנית: אם לכל הפרקים יש תאריך - מהחדש לישן (כך "הפרק הבא" בנגן נכון)."""
    for cat in data.get("categories", []):
        for sc in cat.get("sub_categories", []):
            eps = sc.get("channels", [])
            if eps and all(ep.get("date") for ep in eps):
                eps.sort(key=lambda ep: ep["date"], reverse=True)


def catalog_stats(data):
    n_eps = sum(len(sc["channels"]) for c in data.get("categories", []) for sc in c.get("sub_categories", []))
    return len(data.get("categories", [])), n_eps


def index_entry(sid, data, updated=None):
    programs, episodes = catalog_stats(data)
    return {"id": sid, "name": data.get("name"), "url": data.get("url"), "logo": data.get("logo") or "",
            "file": f"{VOD_SUBDIR}/{sid}.json", "programs": programs, "episodes": episodes,
            "source": "youtube", "updated": updated or time.strftime("%Y-%m-%d %H:%M")}


def catalog_changed(old, new):
    """האם הקטלוג השתנה (בלי חותמות הזמן)."""
    strip = lambda d: [dict(c, updated=None) for c in (d or {}).get("categories", [])]  # noqa: E731
    return strip(old) != strip(new)


# ---------------------------------------------------------------- CLI (GitHub Actions / local)
def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def rebuild_all(root, only=None, dates_per_source=2000):
    sources = _load(os.path.join(root, SOURCES_FILE), [])
    old_index = {e["id"]: e for e in _load(os.path.join(root, INDEX_FILE), {}).get("sources", [])}
    index = []
    for s in sources:
        sid = s.get("id") or source_id_for(s["url"])
        path = os.path.join(root, VOD_SUBDIR, sid + ".json")
        old = _load(path, None)
        if only and sid not in only:
            if old:
                index.append(old_index.get(sid) or index_entry(sid, old))
            continue
        print(f"== {s.get('name')}  ({s['url']})")
        status = {}
        try:
            if "archive.org" in s["url"]:
                import archivesource
                data = archivesource.build(s["url"], status)
            else:
                data = build_channel(s["url"], s.get("name") or sid, status)
        except Exception as e:  # noqa: BLE001
            print(f"   !! נכשל: {e}")
            if old:
                index.append(old_index.get(sid) or index_entry(sid, old))
            continue
        programs, episodes = catalog_stats(data)
        if not data["categories"] and old:
            print("   (ריק - שומרים את הקטלוג הקודם)")
            index.append(old_index.get(sid) or index_entry(sid, old))
            continue
        carried = carry_dates(old, data)
        filled = fill_dates(data, status, limit=dates_per_source)
        sort_by_date(data)
        missing = sum(1 for ep in _episodes(data) if not ep.get("date"))
        print(f"   תאריכים: {carried} ידועים, {filled} הושלמו עכשיו, {missing} עדיין חסרים")
        if old and not catalog_changed(old, data):
            print(f"   ללא שינוי: {programs} תוכניות, {episodes} פרקים")
            index.append(old_index.get(sid) or index_entry(sid, old))
            continue
        _save(path, data)
        index.append(index_entry(sid, data))
        print(f"   -> {path}  ({programs} תוכניות, {episodes} פרקים)")
    _save(os.path.join(root, INDEX_FILE), {"name": "MopVOD YouTube", "updated": time.strftime("%Y-%m-%d %H:%M"), "sources": index})
    print(f"   -> {INDEX_FILE}: {len(index)} מקורות")


def main():
    ap = argparse.ArgumentParser(description="בניית קטלוגי YouTube ל-MopVOD")
    ap.add_argument("--all", action="store_true", help="לבנות מחדש את כל המקורות שב-sources.json")
    ap.add_argument("--only", nargs="*", help="מזהי מקורות לבנייה (השאר נשארים כפי שהם)")
    ap.add_argument("--add", help="כתובת ערוץ/פלייליסט להוספה ל-sources.json ובנייה")
    ap.add_argument("--title", help="שם לתצוגה (עם --add)")
    ap.add_argument("--search", help="חיפוש ערוצים לפי שם (בדיקה)")
    ap.add_argument("--dates", type=int, default=2000, help="כמה תאריכים חסרים להשלים לכל מקור בריצה (0 = בלי)")
    args = ap.parse_args()
    if args.search:
        for r in search_channels(args.search):
            print(f"  {r['title']}  |  {r.get('subscribers')}  |  {r['url']}")
        return
    if args.add:
        sources = _load(os.path.join(HERE, SOURCES_FILE), [])
        sid = source_id_for(args.add)
        title = args.title or (search_channels(args.add) or [{"title": args.add}])[0]["title"]
        sources = [s for s in sources if s.get("id") != sid] + [{"id": sid, "name": title, "url": args.add}]
        _save(os.path.join(HERE, SOURCES_FILE), sources)
        rebuild_all(HERE, only=[sid], dates_per_source=args.dates)
        return
    if args.all or args.only:
        rebuild_all(HERE, only=args.only, dates_per_source=args.dates)
        return
    ap.print_help()


if __name__ == "__main__":
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
    main()
