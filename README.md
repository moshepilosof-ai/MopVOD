# MopVOD

ארכיון ה-VOD של כאן 11 (kan.org.il) כקובצי JSON במבנה של MopTV, עם רענון אוטומטי ב-GitHub Actions.
לכל תוכנית קובץ עם כל הפרקים: קישור לזרם, תמונה, תאריך ותקציר.

הריפו הזה נפרד מ-MopTV ולא נוגע ב-`channel.json`. האפליקציה תוכל לטעון את `MopVOD.json` בגרסה עתידית.

## הקבצים שהטלוויזיה תקרא

| כתובת | תוכן |
|---|---|
| `https://raw.githubusercontent.com/moshepilosof-ai/MopVOD/main/MopVOD.json` | האינדקס: רשימת התוכניות, מספר פרקים ועונות, טווח תאריכים (כ-100 KB) |
| `https://raw.githubusercontent.com/moshepilosof-ai/MopVOD/main/vod/<id>.json` | קובץ לכל תוכנית עם כל הפרקים לפי עונות |

השדה `file` בכל רשומה באינדקס מצביע על קובץ התוכנית (למשל `vod/kan11_zman_emet.json`).

## רענון אוטומטי (GitHub Actions)

`.github/workflows/update.yml` מריץ את האיסוף על שרת של GitHub ארבע פעמים ביום
(5:30, 11:30, 17:30, 22:30 שעון ישראל בחורף). כל ריצה:

1. `--discover`: בודקת בדפי הלובי של כאן אם נוספו תוכניות חדשות ומעדכנת את `programs.json`.
2. עוברת על כל התוכניות והעונות, קוראת מהאתר רק פרקים שעדיין לא קיימים בקובצי `vod/`.
3. שומרת (commit) רק את הקבצים שבאמת השתנו.

הרצה ידנית: לשונית **Actions** בריפו, **Update VOD archive**, **Run workflow**.
ההיסטוריה של הריצות ומה נוסף בכל אחת מופיעה באותה לשונית ובהיסטוריית ה-commits.

## קבצים בריפו

| קובץ | תפקיד |
|---|---|
| `mopvod.py` | הסקריפט. קורא דפי תוכנית ופרק באתר כאן וכותב JSON |
| `programs.json` | אילו תוכניות לאסוף (שם, כתובת דף התוכנית באתר כאן). מתעדכן אוטומטית ב-`--discover` |
| `MopVOD.json` | האינדקס |
| `vod/<id>.json` | קובץ ארכיון לכל תוכנית |
| `.github/workflows/update.yml` | הרענון המתוזמן |
| `build_windows.cmd` | בניית `MopVOD.exe` להרצה מקומית בלי Python |
| `cache/episodes/` | מטמון מקומי (לא בגיט). לא חובה: פרקים שכבר ב-`vod/` לא נקראים שוב גם בלעדיו |

## הרצה מקומית

```
python mopvod.py                          # כל התוכניות שב-programs.json
python mopvod.py --program kan11_zman_emet
python mopvod.py --limit 30               # לבדיקה: רק 30 הפרקים האחרונים לכל תוכנית
python mopvod.py --discover               # עדכון רשימת התוכניות מדפי הלובי של כאן
python mopvod.py --single                 # הכל בתוך MopVOD.json אחד (גדול, כ-16MB)
python mopvod.py --publish                # בנייה + העלאה דרך ה-API (בלי git, דורש טוקן)
```

ריצה ראשונה על ריפו ריק נמשכת שעות (כ-21,000 פרקים). ריצה חוזרת נמשכת כ-20 עד 30 דקות,
רובן סריקת דפי העונות; מהאתר נקראים רק פרקים חדשים.

### בלי Python (Windows)

`build_windows.cmd` בונה `windows\dist\MopVOD.exe`. שים את ה-EXE באותה תיקייה עם `programs.json`,
ואז לחיצה כפולה אוספת פרקים חדשים (החלון נשאר פתוח בסוף). ה-EXE מקבל את אותם פרמטרים כמו הסקריפט.
אחרי ריצה מקומית, `git commit` ו-`git push` מעלים את התוצאה, או `--publish` עם טוקן ב-`github_token.txt`
(Fine-grained token עם Contents: Read and write על הריפו הזה).

## הוספת תוכנית ידנית

1. באתר כאן, פתח את דף התוכנית והעתק את הכתובת (חייבת להכיל `/p-<מספר>/`).
2. הוסף רשומה ל-`programs.json` עם `id` באנגלית, `title` לתצוגה, ו-`url`.
3. הרץ `python mopvod.py --program <id>` או חכה לריצה המתוזמנת.

## מבנה הפלט

`MopVOD.json`:

```json
{
  "name": "MopVOD",
  "updated": "2026-10-28 13:42",
  "sources": [
    { "name": "כאן 11 - זמן אמת", "file": "vod/kan11_zman_emet.json",
      "episodes": 175, "seasons": 10, "newest": "2026-09-21", "oldest": "2023-04-22" }
  ]
}
```

`vod/kan11_zman_emet.json`:

```json
{
  "categories": [
    {
      "name": "כאן 11 - זמן אמת",
      "type": "vod",
      "source": "kan.org.il",
      "updated": "2026-10-28 13:42",
      "sub_categories": [
        {
          "name": "עונה 10",
          "channels": [
            {
              "name": "זמן אמת עונה 10 | פרק 6 - קו הגמ\"ר",
              "logo": "https://www.kan.org.il/media/.../image.jpg",
              "url": "https://r.il.cdn-redge.media/.../playlist.m3u8?fmp4",
              "date": "2026-06-09",
              "plot": "תקציר הפרק",
              "page": "https://www.kan.org.il/content/kan/kan-11/p-12043/s10/1050745/",
              "season": 10,
              "id": "1050745"
            }
          ]
        }
      ]
    }
  ]
}
```

הזרמים הם HLS פתוחים (H.264, 25 פריימים, 360p עד 1080p), ללא טוקן וללא DRM,
מאותו CDN של השידור החי של כאן.

## הערות

- הכלי קורא דפים ציבוריים בלבד, עם השהיה של חצי שנייה בין בקשות.
- אם האתר של כאן ישנה מבנה, ייתכן שיהיה צורך לעדכן את הביטויים הרגולריים ב-`parse_episode`.
- התאריך נלקח מהכותרת (למשל "| 16.02.26") ואם אין, מתאריך ההעלאה לאתר. לפרקים שהועלו
  מחדש באתר החדש (2023) תאריך ההעלאה אינו תאריך השידור המקורי.
- פרקים ישנים מאוד שאין להם קישור וידאו בדף מדולגים ונספרים כ"בלי וידאו".
- ערוץ 13 אינו כלול: האתר חוסם גישה אוטומטית.
