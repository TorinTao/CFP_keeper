"""Apply the deadline corrections that official pages proved (evidence-driven)."""
import json
import urllib.request

API = "http://127.0.0.1:8770/api/venues/{vid}/deadlines/{kind}/confirm"

FIXES = [
    # venue id, kind, date, tz, source url, snippet, note
    ("ipmi-2027", "abstract", "2026-12-07", "AoE", "https://2027.ipmi-conf.org/",
     "IMPORTANT DATES: Paper Abstract Due Dec 07, 2026 - end of day, AoE",
     "官网 2027 页核对：摘要截止 12-07（AoE）"),
    ("ipmi-2027", "full_paper", "2026-12-14", "AoE", "https://2027.ipmi-conf.org/",
     "Full Paper Submission Dec 14, 2026 - (no extensions)",
     "官网 2027 页核对：全文截止 12-14（此前误记为 12-07 摘要日）"),
    ("cvpr-2027", "notification", "2027-02-25", "AoE",
     "https://cvpr.thecvf.com/Conferences/2027/CallForPapers",
     "Reviews Released Jan 25, 2027 AOE; Rebuttal Period January 25 - February 1, 2027; "
     "Final Decisions Feb 25, 2027 AOE",
     "官网 CFP 页核对：最终决定 2027-02-25（AoE）"),
    ("iclr-2028", "abstract", "2026-09-18", "AoE",
     "https://iclr.cc/Conferences/2027/CallForPapers",
     "Abstract deadline Sep 18, 2026 AOE; Paper deadline Sep 25, 2026 AOE",
     "官网 CFP 页核对：摘要 2026-09-18（此前的 2027 年为误记）"),
    ("iclr-2028", "full_paper", "2026-09-25", "AoE",
     "https://iclr.cc/Conferences/2027/CallForPapers",
     "Abstract deadline Sep 18, 2026 AOE; Paper deadline Sep 25, 2026 AOE",
     "官网 CFP 页核对：全文 2026-09-25（此前的 2027 年为误记）"),
    ("icassp-2027", "full_paper", "2026-09-23", "AoE",
     "https://2027.ieeeicassp.org/call-for-papers/",
     "Full Paper Submission Deadline September 23, 2026",
     "官网 CFP 页核对：全文 2026-09-23（时区官网未标注，按惯例记 AoE）"),
]


def confirm(vid, kind, date, tz, url, snippet, note):
    payload = {"date": date, "time": "23:59", "tz": tz, "source_url": url,
               "snippet": snippet, "note": note}
    req = urllib.request.Request(
        API.format(vid=vid, kind=kind),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        body = json.loads(res.read().decode("utf-8"))
    return body["deadline"]["date"], body["deadline"]["source_status"]


for fix in FIXES:
    date, status = confirm(*fix)
    print(f"{fix[0]:14s} {fix[1]:12s} -> {date} {status}")
print("done")
