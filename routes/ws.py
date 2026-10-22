import re
import json as _json
import logging

import requests

from data import load_data, save_data

log = logging.getLogger(__name__)


def register(sock):
    @sock.route("/ws/enrich")
    def ws_enrich(ws):
        data    = load_data()
        updated = 0
        needs   = [
            (i, d) for i, d in enumerate(data["downloaded"])
            if not (isinstance(d, dict) and d.get("title") and
                    not d["title"].startswith("http") and not d["title"].isdigit())
        ]
        ws.send(_json.dumps({"type": "start", "total": len(needs)}))
        for count, (i, d) in enumerate(needs, 1):
            url = d.get("url", d) if isinstance(d, dict) else d
            m   = re.search(r"/(\d+)(?:\.torrent)?$", url)
            if not m:
                ws.send(_json.dumps({"type": "progress", "current": count, "total": len(needs), "title": "skipped"}))
                continue
            page_title = ""
            try:
                resp = requests.get(
                    f"https://nyaa.si/view/{m.group(1)}", timeout=5,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                tm = re.search(r"<title>([^<]+)</title>", resp.text)
                if tm:
                    page_title = tm.group(1).replace(" :: Nyaa", "").strip()
                    data["downloaded"][i] = {
                        "url":   url,
                        "title": page_title,
                        "date":  d.get("date", "") if isinstance(d, dict) else "",
                    }
                    updated += 1
            except Exception:
                page_title = "error"
            ws.send(_json.dumps({
                "type": "progress", "current": count, "total": len(needs),
                "title": page_title[:80] or url,
            }))
        if updated:
            save_data(data)
        ws.send(_json.dumps({"type": "done", "updated": updated, "total": len(needs)}))
