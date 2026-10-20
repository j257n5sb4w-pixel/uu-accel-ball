#!/usr/bin/env python3
"""Write a machine-readable snapshot of the current UU state for handoff."""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uu  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handoff", "state.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

snap = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "router": {"host": uu.HOST, "user": uu.USER, "sn": uu.SN,
                   "type": uu.ROUTER_TYPE, "api": uu.API}}

try:
    snap["local_status"] = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "uu.py"),
         "status"], capture_output=True, text=True, timeout=60).stdout
except Exception as e:  # noqa: BLE001
    snap["local_status"] = "error: %s" % e

sess, logged, _ = uu.cloud_session()
snap["logged_in"] = logged
if logged:
    st = uu.api_call("GET", "/status", sess=sess)
    snap["cloud_status"] = st
    d = uu.devices(sess)
    snap["devices"] = d.get("devices") if d else None
    settings = (st.get("game_mode_setting") or {}).get("device_setting") or {}
    snap["settings"] = settings

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False, indent=1)
print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))
for x in snap.get("devices") or []:
    i = x["deviceinfo"]
    key = "%s-%s" % (i["type"], i["mac"])
    s = snap["settings"].get(key) or {}
    print("  %-8s %-15s %-24s %-38s %s" % (x["acc_status"], i["ip"], i["hostname"],
                                           i["mac"], s.get("game_name", "-")))
