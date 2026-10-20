#!/usr/bin/env python3
"""uu.py - one-line control of the NetEase UU accelerator (ASUS RT-AX86U).

Two control planes were found by reverse engineering the router plugin:

  local  (no account needed) - process level, affects the whole router:
      python uu.py status | start | stop | restart | ensure

  local  (no account needed) - clone the accelerating device's policy rules
         onto another LAN IP (same tunnel/session, works while a session exists):
      python uu.py route <ip> [show|on|off] [template_ip]

  cloud  (per device / per game, needs your UU account login once):
      python uu.py login --cookie "..."            store browser cookie
      python uu.py dev                             LAN devices: acc state + game
      python uu.py acc <mac|ip|name> [--game X]    accelerate one device
                       [--zone 节点] [--server 服务器]
      python uu.py unacc <mac|ip|name>             stop accelerating one device
      python uu.py games [pc|mobile]               game list / ids

Cloud calls go to https://router.uu.163.com/api with header "sess".
login is phone + SMS code only, so the cookie has to come from a real
browser session (see `python uu.py login` with no arguments).
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

HOST = os.environ.get("RHOST", "")
USER = os.environ.get("RUSER", "CHANGE_ME_USER")
PASS = os.environ.get("RPASS", "CHANGE_ME_PASSWORD")
PORT = int(os.environ.get("RPORT", "22"))

HELPER = "/tmp/uuctl.sh"
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else HERE


def _res(name):
    # prefer the copy next to the exe (user-editable), then the bundled one
    for d in (APP_DIR, HERE):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return os.path.join(HERE, name)


HELPER_SRC = _res("uuctl.sh")
ROUTE_HELPER = "/tmp/uu_route.sh"
ROUTE_SRC = _res("uu_route.sh")
SESSION_FILE = os.path.join(APP_DIR, "session.json")

API = "https://router.uu.163.com/api"
# 路由器 SN（gwSn）。云端 /api/sess 的 sn 就是它 —— 千万别写成某台具体路由器
# 的值，否则别人装了这个程序、又带着别人的 Cookie，就会被当成「那台路由器」，
# 进而去改别人家的加速设置。由面板/CLI 按实际探测结果注入。
SN = os.environ.get("UU_SN", "")


def set_sn(sn):
    """设置当前路由器的 SN（空串表示还没探测到）。"""
    global SN
    SN = (sn or "").strip()
    return SN


def current_sn():
    """显式设置 > 环境变量 > 已保存会话里的 sn。"""
    if SN:
        return SN
    try:
        return (load_session().get("sn") or "").strip()
    except Exception:
        return ""
ROUTER_TYPE = "asuswrt"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PAGE = "https://router.uu.163.com/asus/pc.html"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------- router side
def connect():
    # paramiko is only needed for the SSH control plane (status/start/stop/route).
    # The cloud plane (login/dev/acc/unacc/games) works without it.
    try:
        import paramiko
    except ImportError:
        raise SystemExit(
            "需要 paramiko 才能走 SSH 控制面：pip install paramiko\n"
            "云端命令（dev / acc / unacc / games）不需要 paramiko，也不需要能连 192.168.50.1")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASS,
              timeout=15, banner_timeout=20, auth_timeout=20,
              allow_agent=False, look_for_keys=False)
    return c


def run(c, cmd, data=None, timeout=120.0):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    if data:
        stdin.write(data)
        stdin.flush()
        stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return out, err, stdout.channel.recv_exit_status()


def ensure_file(c, remote, src):
    """upload when missing OR when the local copy changed (size check)"""
    with open(src, "rb") as fh:
        data = fh.read()
    out, _, rc = run(c, "wc -c < %s 2>/dev/null" % remote)
    if rc == 0 and out.strip().isdigit() and int(out.strip()) == len(data):
        return
    # `sh` in /usr/sbin is the Broadcom debug tool -> dd is the reliable upload path
    out, err, rc = run(c, "dd of=%s 2>/dev/null" % remote, data)
    if rc != 0:
        raise SystemExit("upload of %s failed rc=%s err=%s" % (src, rc, err))
    run(c, "chmod 755 %s" % remote)


def ensure_helper(c):
    ensure_file(c, HELPER, HELPER_SRC)


def remote_script(c, remote, src, args):
    ensure_file(c, remote, src)
    out, err, rc = run(c, "/bin/sh %s %s" % (remote, args))
    sys.stdout.write(out)
    if err.strip():
        sys.stdout.write("\n[stderr] " + err)
    return rc


def route_cmd(args):
    """clone/remove the accelerating device's policy rules onto another LAN IP"""
    if not args:
        print("用法: python uu.py route <ip> [show|on|off] [模板设备ip]")
        return 2
    ip = args[0]
    act = args[1] if len(args) > 1 else "show"
    extra = " ".join(args[2:])
    c = connect()
    try:
        return remote_script(c, ROUTE_HELPER, ROUTE_SRC,
                             "%s %s %s" % (ip, act, extra))
    finally:
        c.close()


def local(cmd):
    c = connect()
    try:
        ensure_helper(c)
        out, err, rc = run(c, "/bin/sh %s %s" % (HELPER, cmd))
        sys.stdout.write(out)
        if err.strip():
            sys.stdout.write("\n[stderr] " + err)
        return rc
    finally:
        c.close()


# ---------------------------------------------------------------- cloud side
def load_session():
    try:
        with open(SESSION_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def save_session(d):
    with open(SESSION_FILE, "w", encoding="utf-8") as fh:
        json.dump(d, fh, indent=1)


def api_call(method, path, body=None, sess="", cookie=None):
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
           "Origin": "https://router.uu.163.com", "Referer": PAGE,
           "sess": sess, "Client-Origin": "router.asus.com"}
    if data is not None:
        hdr["Content-Type"] = "application/json"
    # /api/sess returns its token BOTH as a JSON field and as an HttpOnly cookie,
    # and later calls are bound to that cookie -> always send it.
    jar = []
    if sess:
        jar.append("sess=%s" % sess)
    if cookie:
        jar.append(cookie.strip().rstrip(";"))
    if jar:
        hdr["Cookie"] = "; ".join(jar)
    req = urllib.request.Request(API + path, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_CTX) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        print("HTTP %s %s -> %s %s" % (method, path, e.code,
                                       raw[:300].decode("utf-8", "replace")))
        raise SystemExit(3)
    except Exception as e:  # noqa: BLE001
        print("network error %s %s: %s: %s" % (method, path, type(e).__name__, e))
        raise SystemExit(3)
    try:
        return json.loads(raw.decode())
    except Exception:  # noqa: BLE001
        print("bad json: %r" % raw[:300])
        raise SystemExit(3)


def cloud_session(verbose=False):
    """Return (sess, logged_in, details). Always refreshes /api/sess."""
    st = load_session()
    sn = current_sn()
    if not sn:
        raise SystemExit(4)          # 4 = 还没探测到路由器
    set_sn(sn)
    res = api_call("POST", "/sess", {"sn": sn, "type": ROUTER_TYPE},
                   cookie=st.get("cookie"))
    sess = res.get("sess") or ""
    logged = bool(res.get("uu_logged_in"))
    if sess:
        st["sess"] = sess
        save_session(st)
    if verbose:
        print("sess=%s uu_logged_in=%s" % (sess, logged))
    return sess, logged, res


NOT_LOGIN_HELP = """\
没有登录态（UU 返回 not_login）。

登录只能用手机号 + 短信验证码（还有易盾验证码），没法纯命令行自动完成。做法：

1. 浏览器打开（登录一次，保持登录）：
   {page}#/acce?gwSn={sn}&type={rtype}
2. F12 -> Network -> 任意 /api/ 请求 -> 复制请求头里的 Cookie 整串
3. 存进去：
   python uu.py login --cookie "<粘贴的 Cookie>"
4. 再跑：
   python uu.py dev
"""


def not_login_help():
    return NOT_LOGIN_HELP.format(page=PAGE,
                                 sn=(current_sn() or "(未探测)").upper(),
                                 rtype=ROUTER_TYPE)


def cmd_login(args):
    cookie = None
    if "--cookie" in args:
        cookie = args[args.index("--cookie") + 1]
    elif args:
        cookie = args[0]
    if not cookie:
        print("用法: python uu.py login --cookie \"<浏览器 Cookie>\"\n")
        print(not_login_help())
        return 0
    cookie = cookie.strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    st = load_session()
    sn = current_sn()
    if not sn:
        print("还没探测到路由器（SN 未知），先跑 `python uu.py status`，")
        print("或用环境变量指定：set UU_SN=<路由器 MAC>")
        return 1
    st["cookie"] = cookie
    st["sn"] = sn
    save_session(st)
    sess, logged, _ = cloud_session(verbose=True)
    if logged:
        print("登录成功，已保存到 %s" % SESSION_FILE)
        return 0
    print("Cookie 已保存，但服务端仍返回 uu_logged_in=false。")
    print("可能 Cookie 不完整/已过期，或该路由器没绑定到这个 UU 账号。")
    return 1


def devices(sess):
    res = api_call("GET", "/devices/?t=%d" % int(__import__("time").time()), sess=sess)
    if res.get("status") == "not_login":
        return None
    return res


def cmd_dev(args):
    sess, logged, _ = cloud_session(verbose="--verbose" in args)
    if not logged:
        print(not_login_help())
        return 2
    res = devices(sess)
    if res is None:
        print(not_login_help())
        return 2
    if "--json" in args:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    st = api_call("GET", "/status", sess=sess)
    settings = (st.get("game_mode_setting") or {}).get("device_setting") or {}
    for d in res.get("devices") or []:
        info = d.get("deviceinfo") or {}
        key = "%s-%s" % (info.get("type"), info.get("mac"))
        s = settings.get(key) or {}
        game = s.get("game_name") or "-"
        zone = s.get("zone_name") or "-"
        print("%-9s %-15s %-26s %-17s %-8s %s / %s" % (
            d.get("acc_status"), info.get("ip"), (info.get("hostname") or "")[:26],
            info.get("mac"), info.get("type"), game, zone))
    return 0


def find_device(sess, target):
    """Find a device by MAC, IP or hostname substring (case-insensitive)."""
    t = str(target).strip().lower()
    tmac = t.replace("-", ":")
    res = devices(sess)
    if res is None:
        print(not_login_help())
        raise SystemExit(2)
    devs = res.get("devices") or res.get("data") or []
    for d in devs:
        info = d.get("deviceinfo") or {}
        if str(info.get("mac", "")).lower() == tmac:
            return d
    for d in devs:
        info = d.get("deviceinfo") or {}
        if str(info.get("ip", "")) == t:
            return d
    hits = [d for d in devs
            if t in str((d.get("deviceinfo") or {}).get("hostname", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print("匹配到多台设备，请改用 MAC 或 IP：")
        for d in hits:
            i = d.get("deviceinfo") or {}
            print("  %-15s %-26s %s" % (i.get("ip"), i.get("hostname"), i.get("mac")))
        raise SystemExit(4)
    print("找不到设备 %s。可先跑 python uu.py dev" % target)
    raise SystemExit(4)


PLATFORM_OF = {"windows": "pc", "apple": "mobile", "android": "mobile",
               "steam_deck": "mobile", "switch": "switch", "switch2": "switch",
               "ps4": "ps", "ps5": "ps", "xbox": "xbox", "xboxx": "xbox",
               "xboxs": "xbox", "oculus": "mobile", "pico": "mobile",
               "steam_deck": "mobile"}


def load_gamelist(sess, platform):
    r = api_call("GET", "/gamelist?platform=%s" % platform, sess=sess)
    return r.get("gamelist", {}), r.get("zonelist", {}), r.get("serverlist", {})


def all_games(gl):
    """Flatten {platform: {letter: [game, ...]}} into a de-duplicated list."""
    out, seen = [], set()

    def walk(o):
        if isinstance(o, list):
            for x in o:
                if isinstance(x, dict):
                    gid = x.get("game_id") or x.get("_id")
                    if gid and gid not in seen:
                        seen.add(gid)
                        out.append(x)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
    walk(gl)
    return out


def find_game(gl, token):
    t = str(token).strip().lower()
    games = all_games(gl)
    for g in games:
        if str(g.get("game_id")).lower() == t or str(g.get("_id")).lower() == t:
            return g
    exact = [g for g in games if str(g.get("game_name", "")).lower() == t]
    if exact:
        return exact[0]
    hits = [g for g in games if t in str(g.get("game_name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        print("找不到游戏 %s。用 python uu.py games <平台> 查看" % token)
        raise SystemExit(4)
    print("匹配到多个游戏，请写得更精确或用 game_id：")
    for g in hits[:20]:
        print("  %s  %s" % (g.get("game_id"), g.get("game_name")))
    raise SystemExit(4)


def build_setting(dev, game, zones, servers, zone_name=None, server_name=None):
    info = dev.get("deviceinfo") or {}
    gid = game.get("game_id") or game.get("_id")
    zl = [z for z in (zones.get(gid) or []) if z.get("zone_id")]
    zone = None
    if zone_name:
        zone = next((z for z in zl if zone_name.lower() in z["zone_name"].lower()), None)
    if zone is None and zl:
        zone = next((z for z in zl if z["zone_name"] == "智能匹配"), zl[0])
    sl = (servers.get(zone["zone_id"]) or []) if zone else []
    srv = None
    if server_name and sl:
        srv = next((s for s in sl if server_name.lower() in s["server_name"].lower()), None)
    if srv is None and sl:
        srv = next((s for s in sl if s["server_name"] == "所有服务器"), sl[0])
    return {
        "key": "%s-%s" % (info.get("type"), info.get("mac")),
        "key_type": "device",
        "acc_mode": "game",
        "game_id": gid,
        "game_name": game.get("game_name", ""),
        "icon_url": game.get("icon_url", ""),
        "is_fence_mode": False,
        "support_fence_mode": game.get("support_fence_mode", 0),
        "zone_id": (zone or {}).get("zone_id", ""),
        "zone_name": (zone or {}).get("zone_name", ""),
        "zone_auto": not bool(zone),
        "server_id": (srv or {}).get("server_id", ""),
        "server_name": (srv or {}).get("server_name", ""),
        "server_auto": not bool(srv),
        "validate": {"valid": True},
    }


def cmd_acc(args):
    target = args[0] if args else ""
    if not target:
        print("用法: python uu.py acc <mac|ip|hostname> [--game 游戏名或ID] "
              "[--zone 节点] [--server 服务器]")
        return 2
    game_tok = args[args.index("--game") + 1] if "--game" in args else None
    zone_tok = args[args.index("--zone") + 1] if "--zone" in args else None
    srv_tok = args[args.index("--server") + 1] if "--server" in args else None
    sess, logged, _ = cloud_session()
    if not logged:
        print(not_login_help())
        return 2
    dev = find_device(sess, target)
    info = dev.get("deviceinfo") or {}
    if game_tok:
        plat = PLATFORM_OF.get(str(info.get("type")), "pc")
        gl, zones, servers = load_gamelist(sess, plat)
        game = find_game(gl, game_tok)
        setting = build_setting(dev, game, zones, servers, zone_tok, srv_tok)
        r = api_call("POST", "/acc-mode-setting",
                     {"acc_mode": "game", "game_mode_setting": [setting]}, sess=sess)
        if r.get("status") != "ok":
            print("设置游戏失败: %s" % json.dumps(r, ensure_ascii=False))
            return 5
        print("游戏 -> %s / %s / %s" % (setting["game_name"],
                                        setting["zone_name"] or "自动",
                                        setting["server_name"] or "自动"))
    r = api_call("POST", "/acc", {"deviceinfo": info}, sess=sess)
    ok = r.get("status") in ("ok", "acced", "starting")
    print("加速 %s (%s) -> %s" % (info.get("ip"), info.get("hostname"), r.get("status")))
    if not ok:
        print(json.dumps(r, ensure_ascii=False))
    return 0 if ok else 5


def cmd_unacc(args):
    target = args[0] if args else ""
    if not target:
        print("用法: python uu.py unacc <mac|ip|hostname>")
        return 2
    sess, logged, _ = cloud_session()
    if not logged:
        print(not_login_help())
        return 2
    dev = find_device(sess, target)
    info = dev.get("deviceinfo") or {}
    r = api_call("POST", "/stop-acc", {"deviceinfo": info}, sess=sess)
    ok = r.get("status") in ("ok", "not_acc", "stopping")
    print("停止加速 %s (%s) -> %s" % (info.get("ip"), info.get("hostname"), r.get("status")))
    return 0 if ok else 5


def cmd_games(args):
    plat = args[0] if args else "pc"
    sess, logged, _ = cloud_session()
    if not logged:
        print(not_login_help())
        return 2
    r = api_call("GET", "/gamelist?platform=%s" % plat, sess=sess)
    print(json.dumps(r, ensure_ascii=False, indent=1)[:4000])
    return 0


def main() -> int:
    argv = sys.argv[1:]
    cmd = (argv[0] if argv else "status").lower()
    args = argv[1:]
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd in ("status", "start", "stop", "restart", "ensure"):
        return local(cmd)
    if cmd == "route":
        return route_cmd(args)
    if cmd == "login":
        return _with_sn(lambda: cmd_login(args))
    if cmd in ("dev", "devices", "ls"):
        return _with_sn(lambda: cmd_dev(args))
    if cmd in ("acc", "accel", "accelerate"):
        return _with_sn(lambda: cmd_acc(args))
    if cmd in ("unacc", "stop-acc", "deacc"):
        return _with_sn(lambda: cmd_unacc(args))
    if cmd in ("games", "gamelist"):
        return _with_sn(lambda: cmd_games(args))
    print("unknown command: %s\n" % cmd)
    print(__doc__)
    return 2


def _with_sn(fn):
    """云端命令前先确保 SN 已知：本地探测不到就走 SSH 读 activate_status。"""
    if current_sn():
        return fn()
    try:
        detect_sn_via_ssh()
    except Exception:  # noqa: BLE001
        pass
    try:
        return fn()
    except SystemExit as exc:
        if str(exc) == "4":
            print("还没探测到路由器 SN：先跑 `python uu.py status`，")
            print("或设环境变量 UU_SN=<路由器 MAC/SN>")
            return 4
        raise


def detect_sn_via_ssh():
    """SSH 读插件写的 /tmp/uu/activate_status（内容就是路由器 MAC）。"""
    c = connect()
    try:
        out, _, _ = run(c, "cat /tmp/uu/activate_status 2>/dev/null")
    finally:
        try:
            c.close()
        except Exception:  # noqa: BLE001
            pass
    sn = (out or "").strip().splitlines()
    sn = sn[0].strip() if sn else ""
    if sn:
        set_sn(sn)
    return sn


if __name__ == "__main__":
    raise SystemExit(main())
