# -*- coding: utf-8 -*-
"""
MopVOD - בונה קובצי JSON של ארכיון ה-VOD של כאן (kan.org.il) עבור MopTV.

פרויקט נפרד מ-MopTV: לא נוגע בקוד האפליקציה ולא ב-channel.json.
הפלט: out/MopVOD.json (הקובץ הראשי) + out/vod/<תוכנית>.json לכל תוכנית, באותו מבנה JSON של MopTV
(categories -> sub_categories -> channels) עם שדות נוספים לכל פרק (date, plot, page).
ברירת מחדל: MopVOD.json מכיל את רשימת התוכניות (קטן ומהיר לטעינה) והפרקים בקבצים לפי תוכנית.
עם --single: MopVOD.json מכיל הכל בפנים, בקובץ אחד.

שימוש:
    python mopvod.py                      # כל התוכניות שב-programs.json
    python mopvod.py --program kan11_zman_emet
    python mopvod.py --limit 30           # רק 30 הפרקים האחרונים לכל תוכנית (לבדיקה)
    python mopvod.py --single             # הכל בקובץ MopVOD.json אחד
    python mopvod.py --publish            # גם מעלה ל-GitHub (דורש טוקן, ראה README)

הסקריפט קורא דפים ציבוריים בלבד, בקצב מנומס (השהיה בין בקשות), ושומר מטמון
של פרקים שכבר נקראו ב-cache/ כך שריצה חוזרת מביאה רק פרקים חדשים.
"""
import argparse
import concurrent.futures
import base64
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
PROGRAMS_FILE = os.path.join(HERE, "programs.json")
OUT_DIR = os.path.join(HERE, "out")
VOD_SUBDIR = "vod"
MAIN_FILE = "MopVOD.json"
CACHE_DIR = os.path.join(HERE, "cache", "episodes")

# יעד הפרסום ב-GitHub (אותו ריפו של channel.json: MopVOD.json בשורש, קובצי התוכניות ב-vod/)
GITHUB_OWNER = "moshepilosof-ai"
GITHUB_REPO = "mop_channel"
GITHUB_BRANCH = "main"
GITHUB_DIR = "vod"
TOKEN_FILE = os.path.join(HERE, "github_token.txt")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36 MopVOD/1.0"
DELAY = 0.5          # שניות בין בקשות לאתר (לכל עובד)
WORKERS = 4          # קריאות פרקים במקביל
MAX_SEASON_PROBE = 40


# ---------------------------------------------------------------- HTTP
def fetch(url, retries=3, timeout=25):
    """מוריד דף/קובץ ומחזיר טקסט. מנסה שוב בשגיאות זמניות."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "he,en;q=0.8"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            time.sleep(DELAY)
            return data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    print(f"    !! fetch failed: {url} ({last})")
    return None


# ---------------------------------------------------------------- parsing
def series_id_from_url(url):
    m = re.search(r"/p-(\d+)/", url)
    if not m:
        raise ValueError("כתובת תוכנית חייבת להכיל /p-<מספר>/ : " + url)
    return m.group(1)


def episode_links(page_html, series_id):
    """מחזיר {episode_id: (season_number|None, url)} מתוך דף תוכנית/עונה."""
    pat = re.compile(r'href="(https://www\.kan\.org\.il/content/[^"]*?/p-' + series_id + r'/(?:s(\d+)/)?(\d+)/)"')
    found = {}
    for m in pat.finditer(page_html):
        url, season, ep_id = m.group(1), m.group(2), m.group(3)
        found.setdefault(ep_id, (int(season) if season else None, url))
    return found


def collect_program_episodes(program_url):
    """אוסף את כל הפרקים של תוכנית, כולל כל העונות. מחזיר (series_id, {ep_id: (season, url)})."""
    series_id = series_id_from_url(program_url)
    base = program_url if program_url.endswith("/") else program_url + "/"
    page = fetch(base)
    if page is None:
        raise RuntimeError("דף התוכנית לא נמצא: " + program_url)
    episodes = episode_links(page, series_id)
    has_seasons = ('data-season-id="' in page and 'data-season-id="0"' not in page) or any(s for s, _ in episodes.values())
    if has_seasons:
        # עמודי עונה: /sN/ . מספרי העונות לא מפורסמים במלואם בדף, לכן בודקים 1..N
        # ומפסיקים אחרי שתי עונות ריקות ברצף מעבר לגבוהה ביותר שראינו.
        seen = {s for s, _ in episodes.values() if s}
        top = max(seen) if seen else 1
        empty_run = 0
        n = 1
        while n <= MAX_SEASON_PROBE:
            if n in seen and n != top:
                n += 1
                continue
            sp = fetch(f"{base}s{n}/")
            got = episode_links(sp, series_id) if sp else {}
            new = {k: v for k, v in got.items() if v[0] == n}
            if new:
                episodes.update(new)
                seen.add(n)
                empty_run = 0
            else:
                empty_run += 1
                if n > top and empty_run >= 2:
                    break
            n += 1
    return series_id, episodes


def parse_episode(url):
    """קורא דף פרק ומחזיר dict עם name/date/logo/plot/url(hls)/page. None אם אין וידאו."""
    page = fetch(url)
    if page is None:
        return None
    info = {"page": url}
    # JSON-LD של VideoObject - המקור המסודר ביותר
    for m in re.finditer(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', page, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict) and d.get("@type") == "VideoObject":
            info["name"] = html.unescape(d.get("name") or "") or None
            info["plot"] = html.unescape(d.get("description") or "")
            info["logo"] = d.get("thumbnailUrl")
            info["date"] = d.get("uploadDate")
            info["url"] = d.get("contentUrl")
            if d.get("duration"):
                info["duration"] = d.get("duration")
    # נפילה חזרה: תגי og ו-JSON של הנגן
    if not info.get("name"):
        m = re.search(r'property="og:title" content="([^"]*)"', page)
        info["name"] = html.unescape(m.group(1)) if m else None
    if not info.get("plot"):
        m = re.search(r'property="og:description" content="([^"]*)"', page)
        info["plot"] = html.unescape(m.group(1)) if m else ""
    if not info.get("logo"):
        m = re.search(r'property="og:image" content="([^"]*)"', page)
        info["logo"] = html.unescape(m.group(1)) if m else ""
    if not info.get("url"):
        m = re.search(r'"hls":"([^"]+)"', page)
        info["url"] = m.group(1) if m else None
    if not info.get("date"):
        m = re.search(r'"datePublished":"([^"]+)"', page)
        info["date"] = m.group(1) if m else None
    if info.get("url") and info["url"].startswith("//"):
        info["url"] = "https:" + info["url"]
    if info.get("logo"):
        info["logo"] = info["logo"].split("?")[0]  # בלי פרמטרי חיתוך, התמונה המקורית
    if info.get("plot"):
        info["plot"] = info["plot"].strip()
    # תאריך מהכותרת ("| 16.02.26") כגיבוי, ובכל מקרה תאריך קצר לתצוגה
    short = None
    if info.get("name"):
        m = re.search(r"\|\s*(\d{2})\.(\d{2})\.(\d{2,4})\s*$", info["name"])
        if m:
            d_, mo, y = m.groups()
            y = y if len(y) == 4 else "20" + y
            short = f"{y}-{mo}-{d_}"
    if not short and info.get("date"):
        short = info["date"][:10]
    info["date"] = short
    if not info.get("url"):
        return None
    return info


# ---------------------------------------------------------------- discovery
# דפי "לובי" באתר כאן שמהם אוספים את רשימת כל התוכניות
LOBBIES = ["series", "kan-box", "archive", "newstv", "kan11"]
# מקטעי תוכן שנחשבים טלוויזיה (כאן 11). רדיו ופודקאסטים לא נכללים.
TV_SECTIONS = ("kan/kan-11", "kan/kan-actual", "kan/news-series", "kan-news/newstv",
               "archive1/vod", "archive1/projects", "archive1/remembering", "dig/digital", "kan/eurovision-2023")


def discover_programs(existing):
    """בונה את רשימת כל תוכניות הטלוויזיה של כאן מדפי הלובי. שומר מזהים של רשומות קיימות."""
    by_url = {e["url"].rstrip("/") + "/": e for e in existing}
    found = {}
    for lobby in LOBBIES:
        page = fetch(f"https://www.kan.org.il/lobby/{lobby}/")
        if not page:
            continue
        for m in re.finditer(r'<a[^>]*href="(https://www\.kan\.org\.il/content/([^"]+?)/p-(\d+)/)"[^>]*>', page):
            url, section, pid = m.group(1), m.group(2), m.group(3)
            if not section.startswith(TV_SECTIONS):
                continue
            t = re.search(r'(?:aria-label|title)="([^"]*)"', m.group(0))
            title = html.unescape(t.group(1)).strip() if t else None
            e = found.setdefault(pid, {"url": url, "title": None, "section": section})
            if title and not e["title"]:
                e["title"] = re.sub(r"^\d{1,3}\.\s*", "", title)  # בלי מספור מרשימות "הנצפים ביותר"
    print(f"   נמצאו {len(found)} תוכניות טלוויזיה ב-{len(LOBBIES)} דפי לובי")
    # כותרות חסרות - מדף התוכנית עצמו
    missing = [pid for pid, e in found.items() if not e["title"] and e["url"] not in by_url]
    print(f"   משלימים כותרות ל-{len(missing)} תוכניות מדפי התוכנית...")
    for i, pid in enumerate(missing, 1):
        page = fetch(found[pid]["url"])
        t = re.search(r'property="og:title" content="([^"]*)"', page or "") or re.search(r"<title>([^<]*)", page or "")
        title = html.unescape(t.group(1)).strip() if t else None
        if title:
            title = re.sub(r"\s*[-|]\s*(פרקים מלאים לצפייה ישירה|כאן).*$", "", title).strip()
        found[pid]["title"] = title or f"תוכנית {pid}"
        if i % 25 == 0:
            print(f"   ... {i}/{len(missing)}")
    programs = []
    for pid, e in sorted(found.items(), key=lambda kv: kv[1]["title"] or ""):
        old = by_url.get(e["url"])
        programs.append({
            "id": old["id"] if old else f"kan_{pid}",
            "title": old["title"] if old else f"כאן 11 - {e['title']}",
            "url": e["url"],
            "section": e["section"],
        })
    # רשומות ידניות שלא נמצאו בלובי נשארות
    for e in existing:
        if not any(p["url"] == e["url"].rstrip("/") + "/" for p in programs):
            programs.append(e)
    return programs


# ---------------------------------------------------------------- cache
def cache_path(ep_id):
    return os.path.join(CACHE_DIR, f"{ep_id}.json")


def load_cached(ep_id):
    p = cache_path(ep_id)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cached(ep_id, info):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path(ep_id), "w", encoding="utf-8") as f:
        json.dump(info if info is not None else {"novideo": True}, f, ensure_ascii=False)


# ---------------------------------------------------------------- build
def build_program(prog, limit=None):
    print(f"== {prog['title']}  ({prog['url']})")
    series_id, episodes = collect_program_episodes(prog["url"])
    ids = sorted(episodes.keys(), key=lambda x: int(x), reverse=True)  # מזהים גבוהים = חדשים יותר
    if limit:
        ids = ids[:limit]
    print(f"   {len(episodes)} קישורי פרקים נמצאו, קוראים {len(ids)}")
    by_season = {}
    fetched = skipped = cached = 0
    # פרקים שאינם במטמון נקראים במקביל (WORKERS), כל עובד עם ההשהיה הרגילה בין בקשות
    todo = [ep_id for ep_id in ids if load_cached(ep_id) is None]
    if todo:
        def _fetch_one(ep_id):
            info = parse_episode(episodes[ep_id][1])
            save_cached(ep_id, info)
            return ep_id
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, WORKERS)) as ex:
            for n_done, _ in enumerate(ex.map(_fetch_one, todo), 1):
                fetched += 1
                if n_done % 50 == 0:
                    print(f"   ... {n_done}/{len(todo)} פרקים חדשים נקראו")
    for i, ep_id in enumerate(ids, 1):
        season, url = episodes[ep_id]
        info = load_cached(ep_id)
        if info is None or info.get("novideo"):
            skipped += 1
            continue
        if ep_id not in todo:
            cached += 1
        item = {
            "name": html.unescape(info.get("name") or f"פרק {ep_id}"),
            "logo": info.get("logo") or "",
            "url": info["url"],
            "date": info.get("date"),
            "plot": html.unescape(info.get("plot") or ""),
            "page": info.get("page", url),
            "id": ep_id,
        }
        if season:
            item["season"] = season
        if info.get("duration"):
            item["duration"] = info["duration"]
        by_season.setdefault(season, []).append(item)
    print(f"   סיום: {fetched} נקראו מהאתר, {cached} מהמטמון, {skipped} בלי וידאו")

    subs = []
    for season in sorted(by_season.keys(), key=lambda s: (s is None, -(s or 0))):
        items = sorted(by_season[season], key=lambda it: (it.get("date") or "", int(it["id"])), reverse=True)
        subs.append({"name": f"עונה {season}" if season else "כל הפרקים", "channels": items})
    category = {
        "name": prog["title"],
        "type": "vod",
        "source": "kan.org.il",
        "program_url": prog["url"],
        "series_id": series_id,
        "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sub_categories": subs,
    }
    return {"categories": [category]}


def write_outputs(results, single=False):
    vod_dir = os.path.join(OUT_DIR, VOD_SUBDIR)
    os.makedirs(vod_dir, exist_ok=True)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    # קודם כותבים את קובצי התוכניות של הריצה הזו
    for prog, data in results:
        fname = f"{prog['id']}.json"
        with open(os.path.join(vod_dir, fname), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    # ואז בונים את MopVOD.json מכל קובצי התוכניות הקיימים (גם מריצות קודמות)
    main = {"name": "MopVOD", "updated": now, "sources": []}
    if single:
        main["categories"] = []
    for fname in sorted(f for f in os.listdir(vod_dir) if f.endswith(".json")):
        with open(os.path.join(vod_dir, fname), encoding="utf-8") as f:
            data = json.load(f)
        cat = data["categories"][0]
        prog = {"title": cat["name"]}
        count = sum(len(sc["channels"]) for sc in cat["sub_categories"])
        dates = [c.get("date") for sc in cat["sub_categories"] for c in sc["channels"] if c.get("date")]
        entry = {"name": prog["title"], "file": f"{VOD_SUBDIR}/{fname}", "episodes": count,
                 "seasons": len(cat["sub_categories"]), "updated": cat["updated"],
                 "newest": max(dates) if dates else None, "oldest": min(dates) if dates else None}
        main["sources"].append(entry)
        if single:
            main["categories"].append(cat)
        print(f"   -> {os.path.join(vod_dir, fname)}  ({count} פרקים, {os.path.getsize(os.path.join(vod_dir, fname)) // 1024} KB)")
    main_path = os.path.join(OUT_DIR, MAIN_FILE)
    with open(main_path, "w", encoding="utf-8") as f:
        json.dump(main, f, ensure_ascii=False, indent=1)
    print(f"   -> {main_path}  ({os.path.getsize(main_path) // 1024} KB{', כולל כל הפרקים' if single else ', רשימת תוכניות'})")


# ---------------------------------------------------------------- publish
def get_token():
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            tok = f.read().strip()
    if not tok:
        raise ValueError("חסר טוקן GitHub: שים אותו בקובץ github_token.txt ליד הסקריפט, או במשתנה הסביבה GITHUB_TOKEN")
    return tok


def github_put(path_in_repo, local_file, token, message):
    api = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{urllib.parse.quote(path_in_repo)}"
    hdr = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": UA}
    sha = None
    try:
        with urllib.request.urlopen(urllib.request.Request(api + f"?ref={GITHUB_BRANCH}", headers=hdr), timeout=30) as r:
            sha = json.load(r).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    with open(local_file, "rb") as f:
        content = base64.b64encode(f.read()).decode("ascii")
    body = {"message": message, "content": content, "branch": GITHUB_BRANCH}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode("utf-8"), headers={**hdr, "Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["content"]["html_url"]


def publish():
    token = get_token()
    vod_dir = os.path.join(OUT_DIR, VOD_SUBDIR)
    for f in sorted(f for f in os.listdir(vod_dir) if f.endswith(".json")):
        url = github_put(f"{GITHUB_DIR}/{f}", os.path.join(vod_dir, f), token, f"MopVOD: update {f}")
        print(f"   פורסם: {url}")
    url = github_put(MAIN_FILE, os.path.join(OUT_DIR, MAIN_FILE), token, f"MopVOD: update {MAIN_FILE}")
    print(f"   פורסם: {url}")


# ---------------------------------------------------------------- main
def main():
    global DELAY, WORKERS
    ap = argparse.ArgumentParser(description="בניית ארכיון VOD של כאן ל-JSON")
    ap.add_argument("--program", help="מזהה תוכנית מתוך programs.json (ברירת מחדל: כולן)")
    ap.add_argument("--limit", type=int, help="לקרוא רק N פרקים אחרונים לכל תוכנית")
    ap.add_argument("--single", action="store_true", help="לכתוב את כל הפרקים לתוך MopVOD.json אחד (ברירת מחדל: רשימת תוכניות + קובץ לכל תוכנית)")
    ap.add_argument("--publish", action="store_true", help="להעלות את out ל-GitHub אחרי הבנייה")
    ap.add_argument("--publish-only", action="store_true", help="רק להעלות את מה שכבר ב-out")
    ap.add_argument("--delay", type=float, default=DELAY, help="השהיה בין בקשות (שניות)")
    ap.add_argument("--workers", type=int, default=WORKERS, help="כמה פרקים לקרוא במקביל")
    ap.add_argument("--discover", action="store_true", help="לגלות את כל תוכניות הטלוויזיה של כאן ולכתוב אותן ל-programs.json (בלי לבנות)")
    args = ap.parse_args()
    DELAY = args.delay
    WORKERS = args.workers

    if args.discover:
        with open(PROGRAMS_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["programs"] = discover_programs(cfg.get("programs", []))
        with open(PROGRAMS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        print(f"   -> {PROGRAMS_FILE}: {len(cfg['programs'])} תוכניות")
        return

    if args.publish_only:
        publish()
        return

    with open(PROGRAMS_FILE, encoding="utf-8") as f:
        programs = json.load(f)["programs"]
    if args.program:
        programs = [p for p in programs if p["id"] == args.program]
        if not programs:
            raise ValueError("אין תוכנית בשם " + args.program)

    results = []
    for prog in programs:
        try:
            results.append((prog, build_program(prog, args.limit)))
        except Exception as e:  # noqa: BLE001
            print(f"   !! {prog['title']}: {e}")
    if results:
        write_outputs(results, single=args.single)
    if args.publish:
        publish()


if __name__ == "__main__":
    try:
        main()
    except ValueError as e:
        print("שגיאה:", e)
        sys.exit(1)
