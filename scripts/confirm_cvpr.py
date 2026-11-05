"""Re-confirm CVPR's paper deadline with a clean UTF-8 payload.

(PowerShell mangled the Chinese snippet into "??" — this posts proper JSON.)
"""
import json
import urllib.request

payload = {
    "date": "2026-11-16",
    "time": "23:59",
    "tz": "AoE",
    "source_url": "https://cvpr.thecvf.com/Conferences/2027/CallForPapers",
    "snippet": "Important Dates: Paper Enrollment Deadline Nov 10, 2026; "
               "Submission Deadline Nov 16, 2026 11:59 PM AOE; "
               "Supplementary Materials Deadline Nov 23, 2026",
    "note": "官网 Call for Papers 页核对：全文提交截止 Nov 16, 2026（AoE）",
}
req = urllib.request.Request(
    "http://127.0.0.1:8770/api/venues/cvpr-2027/deadlines/full_paper/confirm",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    method="POST",
    headers={"Content-Type": "application/json; charset=utf-8"},
)
with urllib.request.urlopen(req, timeout=10) as res:
    body = json.loads(res.read().decode("utf-8"))
print("confirmed:", body["deadline"]["date"], body["deadline"]["source_status"])
print("note:", body["deadline"]["note"])
