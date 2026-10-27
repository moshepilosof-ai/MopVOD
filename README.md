# KanArchive

כלי נפרד מ-MopTV שבונה קובצי JSON של ארכיון ה-VOD של כאן (kan.org.il):
לכל תוכנית קובץ אחד עם כל הפרקים, הקישורים לזרם, תמונה, תאריך ותקציר.
הפלט באותו מבנה JSON של MopTV, כך שבעתיד האפליקציה תוכל לטעון אותו ישירות.

הכלי **לא** נוגע ב-MopTV ולא ב-`channel.json`.

## קבצים

| קובץ | תפקיד |
|---|---|
| `kan_archive.py` | הסקריפט. קורא דפי תוכנית ופרק, כותב JSON, מעלה ל-GitHub לפי בקשה |
| `programs.json` | אילו תוכניות לאסוף (שם, כתובת דף התוכנית באתר כאן) |
| `out/vod/<id>.json` | קובץ ארכיון לכל תוכנית (נוצר בריצה) |
| `out/vod/index.json` | רשימת הארכיונים הקיימים, מספר פרקים, תאריכים |
| `cache/episodes/` | מטמון של פרקים שכבר נקראו. ריצה חוזרת מביאה רק פרקים חדשים |
| `github_token.txt` | הטוקן להעלאה ל-GitHub (לא נשמר בגיט) |

## הרצה

```
python kan_archive.py                          # כל התוכניות
python kan_archive.py --program kan11_zman_emet
python kan_archive.py --limit 30               # לבדיקה: רק 30 הפרקים האחרונים
python kan_archive.py --publish                # בנייה + העלאה ל-GitHub
python kan_archive.py --publish-only           # רק העלאה של מה שכבר ב-out/vod
```

ריצה ראשונה של המהדורה המרכזית (כ-2,300 פרקים) נמשכת כ-30 עד 40 דקות.
ריצות הבאות נמשכות דקה או שתיים, כי רק הפרקים החדשים נקראים מהאתר.

## הוספת תוכנית

1. באתר כאן, פתח את דף התוכנית והעתק את הכתובת (חייבת להכיל `/p-<מספר>/`).
2. הוסף רשומה ל-`programs.json` עם `id` באנגלית, `title` לתצוגה, ו-`url`.
3. הרץ `python kan_archive.py --program <id>`.

## העלאה ל-GitHub

הקבצים עולים לריפו `moshepilosof-ai/mop_channel` לתיקייה `vod/`.
נדרש Fine-grained Personal Access Token עם הרשאת Contents: Read and write על הריפו.
שמור אותו בקובץ `github_token.txt` ליד הסקריפט (או במשתנה סביבה `GITHUB_TOKEN`).

## מבנה הפלט

```json
{
  "categories": [
    {
      "name": "כאן 11 - זמן אמת",
      "type": "vod",
      "source": "kan.org.il",
      "updated": "2026-10-27 01:00",
      "sub_categories": [
        {
          "name": "עונה 10",
          "channels": [
            {
              "name": "זמן אמת - קו הגמ\"ר",
              "logo": "https://www.kan.org.il/media/.../image.jpg",
              "url": "https://r.il.cdn-redge.media/.../playlist.m3u8?fmp4",
              "date": "2026-06-10",
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
- פרקים ישנים מאוד (לפני 2023 בערך) לא תמיד מכילים קישור וידאו בדף, והם מדולגים.
