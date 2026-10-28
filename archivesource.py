# -*- coding: utf-8 -*-
"""
מתאם ל-Internet Archive (archive.org): סרטים בנחלת הכלל, פתוחים, בלי DRM ובלי הרשמה.

כתובות נתמכות:
  https://archive.org/details/<collection>      אוסף (למשל feature_films, silent_films, SciFi_Horror)
  https://archive.org/details/<item>            סרט בודד
  https://archive.org/search?query=<q>          תוצאות חיפוש (רק סרטים)

מבנה הקטלוג: קטגוריה אחת לאוסף, "עונות" לפי עשורים (שנות ה-20, ה-30...), ובכל עונה הסרטים לפי פופולריות.
הקישור של כל סרט הוא דף הפריט; קובץ הווידאו (MP4) נבחר בזמן הניגון (resolve="archive"), כי לכל פריט כמה קבצים.
עותק זהה של הקובץ הזה נמצא בריפו MopVOD (לרענון היומי ב-GitHub Actions).
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request

UA = "MopVOD/1.0 (+https://github.com/moshepilosof-ai/MopVOD)"
MAX_ITEMS = 1000          # כמה סרטים לכל היותר לאוסף (הפופולריים ביותר)
PAGE = 500
VIDEO_EXT = (".mp4", ".m4v", ".webm", ".ogv")


def is_archive_url(url):
    host = urllib.parse.urlsplit(url or "").hostname or ""
    return host == "archive.org" or host.endswith(".archive.org")


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _clean(text, limit=600):
    if isinstance(text, list):
        text = " ".join(str(t) for t in text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _date_of(doc):
    d = doc.get("date")
    if isinstance(d, list):
        d = d[0] if d else None
    if d and re.match(r"\d{4}-\d{2}-\d{2}", str(d)):
        return str(d)[:10]
    y = doc.get("year")
    if isinstance(y, list):
        y = y[0] if y else None
    if y and re.match(r"^\d{4}$", str(y)):
        return f"{y}-01-01"
    return None


def _decade_name(date):
    if not date:
        return "ללא שנה"
    y = int(date[:4])
    dec = y // 10 * 10
    return f"שנות ה-{dec % 100:02d}" if 1900 <= dec < 2000 else (f"{dec}-{dec + 9}" if dec >= 2000 else f"{dec}")


def parse_url(url):
    """מחזיר ('collection'|'item'|'search', ערך)."""
    u = urllib.parse.urlsplit(url)
    m = re.match(r"^/details/([^/?#]+)", u.path)
    if m:
        ident = m.group(1)
        try:
            meta = _get_json(f"https://archive.org/metadata/{ident}/metadata").get("result") or {}
        except Exception:  # noqa: BLE001
            meta = {}
        kind = "collection" if meta.get("mediatype") == "collection" else "item"
        return kind, ident, meta
    if u.path.startswith(("/search", "/advancedsearch")):
        q = urllib.parse.parse_qs(u.query).get("query") or urllib.parse.parse_qs(u.query).get("q") or [""]
        return "search", q[0], {}
    raise RuntimeError("כתובת archive.org לא מזוהה. צריך /details/<אוסף> או /search?query=...")


def _search(query, status=None, limit=MAX_ITEMS):
    docs = []
    page = 1
    while len(docs) < limit:
        rows = min(PAGE, limit - len(docs))
        q = urllib.parse.urlencode({"q": query, "fl[]": ["identifier", "title", "year", "date", "description", "downloads", "runtime"],
                                    "sort[]": "downloads desc", "rows": rows, "page": page, "output": "json"}, doseq=True)
        res = _get_json("https://archive.org/advancedsearch.php?" + q).get("response") or {}
        batch = res.get("docs") or []
        docs.extend(batch)
        if status is not None:
            status.update(step=f"קורא רשימת סרטים: {len(docs)}/{min(limit, res.get('numFound', 0))}", progress=len(docs) / max(1, min(limit, res.get("numFound", 1))))
        if len(batch) < rows:
            break
        page += 1
    return docs


def _episode(doc):
    ident = doc["identifier"]
    date = _date_of(doc)
    title = doc.get("title")
    if isinstance(title, list):
        title = title[0] if title else ident
    rt = doc.get("runtime")
    if isinstance(rt, list):
        rt = rt[0] if rt else None
    return {
        "name": _clean(title or ident, 200),
        "logo": f"https://archive.org/services/img/{ident}",
        "url": f"https://archive.org/details/{ident}",
        "date": date,
        "plot": _clean(doc.get("description")),
        "page": f"https://archive.org/details/{ident}",
        "id": ident,
        "duration": str(rt) if rt else None,
        "resolve": "archive",
    }


def build(url, status=None, limit=MAX_ITEMS):
    """קטלוג במבנה MopVOD לכתובת archive.org."""
    status = status if status is not None else {}
    kind, value, meta = parse_url(url)
    now = time.strftime("%Y-%m-%d %H:%M")
    if kind == "item":
        docs = _search(f"identifier:{value}", status, limit=1)
        if not docs:
            raise RuntimeError("הפריט לא נמצא")
        ep = _episode(docs[0])
        name = ep["name"]
        return {"name": name, "url": url, "logo": ep["logo"],
                "categories": [{"name": name, "type": "vod", "source": "archive.org", "resolve": "archive", "logo": ep["logo"],
                                "program_url": url, "updated": now, "sub_categories": [{"name": "כל הפרקים", "channels": [ep]}]}]}
    if kind == "collection":
        query = f"collection:{value} AND mediatype:movies"
        name = _clean(meta.get("title") or value, 120)
        logo = f"https://archive.org/services/img/{value}"
    else:
        query = f"({value}) AND mediatype:movies"
        name = "Internet Archive: " + value
        logo = ""
    status.update(step="קורא את " + name)
    docs = _search(query, status, limit=limit)
    eps = [_episode(d) for d in docs if d.get("identifier")]
    if not eps:
        raise RuntimeError("לא נמצאו סרטים")
    by_decade = {}
    for ep in eps:
        by_decade.setdefault(_decade_name(ep["date"]), []).append(ep)
    def _key(k):
        m = re.match(r"שנות ה-(\d\d)", k)
        if m:
            return (0, -int("19" + m.group(1)))
        m = re.match(r"(\d{4})", k)
        return (0, -int(m.group(1))) if m else (1, 0)
    subs = [{"name": k, "channels": v} for k, v in sorted(by_decade.items(), key=lambda kv: _key(kv[0]))]
    cat = {"name": name, "type": "vod", "source": "archive.org", "resolve": "archive", "logo": logo,
           "program_url": url, "updated": now, "sub_categories": subs}
    return {"name": name, "url": url, "logo": logo, "categories": [cat]}


def resolve(page_url):
    """קובץ הווידאו הטוב ביותר של פריט: MP4 (H.264) עד 1080p, הגדול ביותר; אחרת webm/ogv. ניגון ישיר ב-<video>."""
    m = re.match(r"^https?://(?:www\.)?archive\.org/details/([^/?#]+)", page_url or "")
    if not m:
        raise RuntimeError("כתובת archive.org לא תקינה")
    ident = m.group(1)
    data = _get_json(f"https://archive.org/metadata/{ident}")
    files = data.get("files") or []
    md = data.get("metadata") or {}
    cands = []
    for f in files:
        name = f.get("name") or ""
        low = name.lower()
        if not low.endswith(VIDEO_EXT):
            continue
        fmt = (f.get("format") or "").lower()
        h = int(float(f.get("height") or 0))
        size = int(float(f.get("size") or 0))
        score = 0
        if low.endswith((".mp4", ".m4v")):
            score += 100
            if "h.264" in fmt or "mpeg4" in fmt:
                score += 10
        if low.endswith(".webm"):
            score += 50
        if 0 < h <= 1080:
            score += h / 100
        elif h > 1080:
            score -= 20
        cands.append((score, size, name, f))
    if not cands:
        raise RuntimeError("לפריט הזה אין קובץ וידאו שניתן לנגן")
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    best = cands[0][3]
    length = best.get("length")
    dur = None
    try:
        sec = int(float(length)) if length and ":" not in str(length) else None
        if sec:
            dur = f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"
        elif length:
            dur = str(length)
    except Exception:  # noqa: BLE001
        dur = None
    d = md.get("date") or md.get("year")
    if isinstance(d, list):
        d = d[0] if d else None
    return {
        "title": _clean(md.get("title") or ident, 200),
        "date": (str(d)[:10] if d and re.match(r"\d{4}-\d{2}-\d{2}", str(d)) else (f"{d}-01-01" if d and re.match(r"^\d{4}$", str(d)) else None)),
        "duration": dur,
        "plot": _clean(md.get("description")),
        "logo": f"https://archive.org/services/img/{ident}",
        "direct": f"https://archive.org/download/{ident}/" + urllib.parse.quote(best["name"]),
    }


if __name__ == "__main__":
    import sys
    u = sys.argv[1] if len(sys.argv) > 1 else "https://archive.org/details/SciFi_Horror"
    st = {}
    d = build(u, st, limit=int(sys.argv[2]) if len(sys.argv) > 2 else 50)
    cat = d["categories"][0]
    print(d["name"], "|", [(s["name"], len(s["channels"])) for s in cat["sub_categories"]])
    ep = cat["sub_categories"][0]["channels"][0]
    print("first:", ep["name"], ep["date"], ep["url"])
    print("resolve:", resolve(ep["url"]))
