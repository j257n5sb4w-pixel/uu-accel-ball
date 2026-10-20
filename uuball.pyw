# -*- coding: utf-8 -*-
"""UU 加速球 —— 桌面上一颗白色半透明小球，只控制本机这一台电脑。

左键点球   -> 弹出面板：最近游玩（双击=一键加速）/ 搜索 / 按首字符浏览 -> 加速
右键点球   -> 停止加速 / 刷新 / 退出
按住拖动   -> 换位置（位置会记住）

启动：pythonw uuball.pyw
自检：python uuball.pyw --selftest    打印内部状态后退出，不动云端
      python uuball.pyw --probe       只打印云端/本机解析结果
"""
import json
import math
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import shutil
import traceback
import urllib.request
import uuid

import tkinter as tk
import tkinter.ttk as ttk

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))
# 打包成 exe 后 = exe 所在目录；源码运行时等于 HERE
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else HERE
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import uu  # noqa: E402

APP_NAME = "UU 加速球"

# 分层窗口的透明色键：画布上等于这个颜色的像素 -> 完全透明（并且点击穿透）
KEY = os.environ.get("UUBALL_KEY") or "#fffefe"

# 调试用：整体不透明度（默认 0.88）。设成 1.0 可判断「alpha 与色键是否互相干扰」。
try:
    ALPHA_BALL = float(os.environ.get("UUBALL_ALPHA") or 0.88)
except ValueError:
    ALPHA_BALL = 0.88
BALL = 120                       # 小球外框边长（逻辑像素，比上一版小一圈）
R_DISC = BALL / 2.0 - 8.0        # 圆形半径
COVER_PX = int(round(R_DISC * 2))  # 封面按直径请求，PNG 正好铺满圆
BG_PX = int(round(R_DISC * 2))     # 背景方形边长：中心裁切后铺满整个圆
PANEL_W, PANEL_H = 366, 560

FONT = "Microsoft YaHei UI"
INK = "#1f2329"
MUTED = "#8a8f99"
ACCENT = "#1677ff"
BALL_FILL = "#fbfcfd"
SHADOW = "#dfe4ea"
CHIP_BG = "#f2f4f7"

# ----------------------------------------------------------------- 封面
def http_get(url, timeout=15.0):
    req = urllib.request.Request(url, headers={"User-Agent": "uu-ball/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fop_w(url, w):
    """向 UU 的 CDN 要「指定宽度、等比」的图（imageView 会按宽度缩放，不裁剪）。"""
    if not url:
        return ""
    base = url.split("?")[0]
    return "%s?fop=imageView/1/w/%d/q/99" % (base, w)


def fit_size(aw, ah, pad=0.93):
    """把 aw x ah 的图等比缩到能整个装进半径 R_DISC 的圆里。

    条件是外接矩形对角线 <= 圆的直径，所以 W/H 按对角线归一。
    """
    r = R_DISC * pad
    d = math.hypot(aw, ah) or 1.0
    k = (2.0 * r) / d
    return max(1, int(aw * k)), max(1, int(ah * k))


def png_size(data):
    """从 PNG 头取宽高；不是 PNG 返回 None。"""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def sized_icon(url, px):
    """UU 的 CDN 支持在 fop 里改宽高，直接要我们需要的像素。"""
    if not url:
        return ""
    if "fop=imageView" in url:
        url = re.sub(r"/w/\d+", "/w/%d" % px, url)
        url = re.sub(r"/h/\d+", "/h/%d" % px, url)
    return url


# ----------------------------------------------------------------- 基础设施
def _writable(d):
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".writable"), "w") as fh:
            fh.write("1")
        return True
    except Exception:
        return False


def pick_cfg_dir():
    """配置目录：exe 版优先放在 exe 旁边（整个文件夹拷走就能带走记录）。"""
    env = os.environ.get("UUBALL_CFG")
    cands = []
    if env:
        cands.append(env)
    if FROZEN:
        cands.append(os.path.join(APP_DIR, "uu-data"))
    cands.append(os.path.join(os.environ.get("LOCALAPPDATA")
                              or os.path.expanduser("~"), "uu-ball"))
    cands.append(os.path.join(HERE, ".uu-ball"))
    cands.append(os.path.join(APP_DIR, "uu-data"))
    for d in cands:
        if _writable(d):
            return d
    return cands[0]


CFG_DIR = pick_cfg_dir()
CFG_FILE = os.path.join(CFG_DIR, "ball.json")
CACHE_FILE = os.path.join(CFG_DIR, "gamelist.json")
COVER_DIR = os.path.join(CFG_DIR, "covers")
LOG_FILE = os.path.join(CFG_DIR, "run.log")
STARTUP_DIR = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
AUTOSTART_VBS = os.path.join(STARTUP_DIR, "UU-ball.vbs")


def _log(msg):
    try:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
        sys.stderr.flush()
    except Exception:
        pass


def ensure_streams():
    log = None
    for path in (LOG_FILE, os.path.join(HERE, "run.log")):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            log = open(path, "a", encoding="utf-8", buffering=1)
            break
        except Exception:
            continue
    if log is None:
        try:
            log = open(os.devnull, "w")
        except Exception:
            return None
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    try:
        log.write("\n=== start %s pid=%d argv=%s\n"
                  % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), sys.argv[1:]))
    except Exception:
        pass

    def hook(exc, val, tb):
        try:
            log.write("".join(traceback.format_exception(exc, val, tb)))
            log.flush()
        except Exception:
            pass

    sys.excepthook = hook
    try:
        threading.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    except Exception:
        pass
    return log


def load_cfg():
    try:
        with open(CFG_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cfg(d):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG_FILE, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass


def guard(root):
    def handler(exc, val, tb):
        _log("".join(traceback.format_exception(exc, val, tb)))
    root.report_callback_exception = handler


# ----------------------------------------------------------------- 画图工具
def _rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def mix(c1, c2, t):
    """t=0 -> c1, t=1 -> c2"""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _row(cv, y, xa, xb, fill, key, tag):
    """一行像素：两端按覆盖率混到 key（做抗锯齿），中间整行不透明。"""
    fs = int(math.ceil(xa))
    fe = int(math.floor(xb))
    if fe - fs >= 1:
        cv.create_line(fs, y, fe - 1, y, fill=fill, tags=tag)
    cl = fs - xa
    if 0.02 < cl < 0.98:
        cv.create_line(fs - 1, y, fs - 1, y, fill=mix(key, fill, cl), tags=tag)
    cr = xb - fe
    if 0.02 < cr < 0.98:
        cv.create_line(fe, y, fe, y, fill=mix(key, fill, cr), tags=tag)


def disc(cv, cx, cy, r, fill, key=KEY, tag="art"):
    y0 = int(math.floor(cy - r))
    y1 = int(math.ceil(cy + r))
    for y in range(y0, y1 + 1):
        dy = (y + 0.5) - cy
        if abs(dy) >= r:
            continue
        hw = math.sqrt(r * r - dy * dy)
        _row(cv, y, cx - hw, cx + hw, fill, key, tag)


def round_rect(cv, x0, y0, x1, y1, rad, fill, key=KEY, tag="card"):
    for y in range(int(y0), int(y1)):
        yc = y + 0.5
        if yc < y0 + rad:
            dy = (y0 + rad) - yc
        elif yc > y1 - rad:
            dy = yc - (y1 - rad)
        else:
            dy = 0.0
        if dy > rad:
            continue
        dx = rad - math.sqrt(max(0.0, rad * rad - dy * dy))
        _row(cv, y, x0 + dx, x1 - dx, fill, key, tag)


def short(s, n=8):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def dim_img(root, img, factor=0.45):
    """Tk 没有滤镜，只能把整张图读成颜色表、逐格乘系数、再写回去。"""
    try:
        out = []
        for row in root.tk.splitlist(img.tk.call(str(img), "data")):
            nr = []
            for c in root.tk.splitlist(row):
                nr.append("#%02x%02x%02x" % (int(int(c[1:3], 16) * factor),
                                             int(int(c[3:5], 16) * factor),
                                             int(int(c[5:7], 16) * factor)))
            out.append(nr)
        img.put(out)
    except Exception as exc:
        _log("dim: %r" % (exc,))
    return img


# ----------------------------------------------------------------- 网络探测
def virtual_bounds():
    """整个虚拟桌面的 (x, y, w, h)，多屏时比 winfo_screenwidth 可靠。"""
    try:
        import ctypes
        u = ctypes.windll.user32
        x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
        if w > 0 and h > 0:
            return (x, y, w, h)
    except Exception:
        pass
    return (0, 0, None, None)


def local_mac():
    try:
        n = uuid.getnode()
        return ":".join("%02x" % ((n >> (8 * i)) & 0xFF) for i in range(5, -1, -1))
    except Exception:
        return ""


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("223.5.5.5", 80))
        return s.getsockname()[0]
    except Exception:
        return ""
    finally:
        s.close()


# ----------------------------------------------------------------- 路由器嗅探
def _run_hidden(args, timeout=3.0):
    """跑控制台命令但不闪窗（pythonw 下没有控制台）。"""
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        p = subprocess.Popen(args, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, startupinfo=si,
                             creationflags=0x08000000)
        out, _ = p.communicate(timeout=timeout)
        return out.decode("mbcs", "replace")
    except Exception as exc:
        _log("run %r: %r" % (args, exc))
        return ""


def gateway_ip():
    """默认网关：问系统路由表，取不到再从本机 /24 猜 .1/.254。"""
    for line in _run_hidden(["route", "print", "-4", "0.0.0.0"]).splitlines():
        f = line.split()
        if len(f) >= 3 and f[0] == "0.0.0.0" and f[1] == "0.0.0.0":
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", f[2]) and not f[2].startswith("0."):
                return f[2]
    return ""


def probe_router(ip, timeout=1.2):
    """uuplugin 在 :16363 上有明文 HTTP，GET /router 回 type/sn/model。

    能拿到回包就说明路由器上的 UU 插件活着 —— 这个端口是它自己开的。
    """
    req = "GET /router HTTP/1.1\r\nHost: %s:16363\r\nConnection: close\r\n\r\n" % ip
    s = socket.socket()
    s.settimeout(timeout)
    buf = b""
    try:
        s.connect((ip, 16363))
        s.sendall(req.encode("ascii"))
        while len(buf) < 600:
            try:
                chunk = s.recv(600)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
    except Exception:
        return None
    finally:
        try:
            s.close()
        except Exception:
            pass
    txt = buf.decode("utf-8", "replace")
    if "type:" not in txt:
        return None
    info = {"ip": ip, "type": "", "sn": "", "model": ""}
    for line in txt.splitlines():
        k, _, v = line.partition(":")
        k = k.strip().lower()
        if k in info:
            info[k] = v.strip()
    return info if info["type"] else None


def detect_router(cfg):
    """记住的 IP -> 默认网关 -> 本机 /24 的 .1/.254，第一个回话的就是它。"""
    cands = []
    for ip in (cfg.get("router_ip"), gateway_ip()):
        if ip and ip not in cands:
            cands.append(ip)
    me = local_ip()
    if me.count(".") == 3:
        pfx = me.rsplit(".", 1)[0]
        for tail in (".1", ".254"):
            ip = pfx + tail
            if ip not in cands:
                cands.append(ip)
    for ip in cands:
        info = probe_router(ip)
        if info:
            return info
    # 网关不是路由器（双 NAT、AP 模式、旁路由）时，扫一遍整个 /24 最省事：
    # 254 个地址、64 并发、0.5s 超时，通常 1~2 秒收敛。
    if me.count(".") == 3:
        pfx = me.rsplit(".", 1)[0] + "."
        found = []
        from concurrent.futures import ThreadPoolExecutor

        def _one(tail):
            ip = pfx + str(tail)
            if ip == me:
                return
            got = probe_router(ip, timeout=0.5)
            if got:
                found.append(got)

        with ThreadPoolExecutor(max_workers=64) as pool:
            list(pool.map(_one, range(1, 255)))
        if found:
            _log("router: /24 命中 %s" % found[0]["ip"])
            return found[0]
    return None


# ----------------------------------------------------------------- 拼音首字母
# GB2312 一级汉字表本身就是按拼音排的，取每个字母组的首字当分界就够了，
# 不用带一张几千字的映射表。
_GBTAB = [("A", b"\xb0\xa1"), ("B", "八"), ("C", "擦"), ("D", "搭"),
          ("E", "蛾"), ("F", "发"), ("G", "噶"), ("H", "哈"), ("J", "击"),
          ("K", "喀"), ("L", "垃"), ("M", "妈"), ("N", "拿"), ("O", "哦"),
          ("P", "啪"), ("Q", "期"), ("R", "然"), ("S", "撒"), ("T", "塌"),
          ("W", "挖"), ("X", "昔"), ("Y", "压"), ("Z", "匝")]
_BOUND = [(k, c if isinstance(c, bytes) else c.encode("gb2312")) for k, c in _GBTAB]
_ORDER = {}
for _i, _c in enumerate("0ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _ORDER[_c] = _i + 1
_ORDER["#"] = 99


def _gb(ch):
    try:
        b = ch.encode("gb2312")
    except Exception:
        return None
    return b if len(b) == 2 else None


def initial_of(name):
    """分组标签：数字->0，字母->大写，汉字->拼音首字母，其余->#。"""
    ch = (name or " ")[0]
    if ch.isdigit():
        return "0"
    if ch.isascii() and ch.isalpha():
        return ch.upper()
    b = _gb(ch)
    if b is None:
        return "#"
    hit = None
    for k, a in _BOUND:
        if a <= b:
            hit = k
        else:
            break
    return hit or "#"


def sort_key(name):
    """清单排序：(分组序, 组内拼音序/字母序, 原名)。"""
    name = str(name or "")
    grp = initial_of(name)
    ch = (name or " ")[0]
    if ch.isdigit() or (ch.isascii() and ch.isalpha()):
        mid = ch.upper().encode("ascii")
    else:
        mid = _gb(ch) or b"\xfe"
    return (_ORDER.get(grp, 98), mid, name)


# ----------------------------------------------------------------- 主程序
class LoginDialog:
    """粘一段浏览器 Cookie 就能登录的小窗（UU 登录只有短信验证码）。"""

    def __init__(self, app, parent=None):
        self.app = app
        w = tk.Toplevel(parent or app.root)
        self.win = w
        w.title("UU 登录")
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg="#ffffff")
        ww, hh = 380, 176
        sw = w.winfo_screenwidth()
        sh = w.winfo_screenheight()
        x = max(0, (sw - ww) // 2)
        y = max(0, (sh - hh) // 3)
        w.geometry("%dx%d+%d+%d" % (ww, hh, x, y))
        tk.Label(w, text="粘入 UU 网页的 Cookie（含 sess=…）", bg="#ffffff",
                 fg=INK, font=(FONT, 10, "bold")).place(x=16, y=14)
        tk.Label(w, text="浏览器 F12 → Network → 任一 /api 请求 → 复制 Cookie",
                 bg="#ffffff", fg=MUTED, font=(FONT, 8)).place(x=16, y=40)
        self.var = tk.StringVar()
        ent = tk.Entry(w, textvariable=self.var, font=(FONT, 9),
                       relief="solid", bd=1)
        ent.place(x=16, y=64, width=ww - 32, height=26)
        ent.focus_set()
        tk.Button(w, text="取消", command=self.close, relief="flat",
                  bg=CHIP_BG, fg=INK, font=(FONT, 9),
                  activebackground="#e6e9ee").place(x=ww - 180, y=110, width=72, height=30)
        tk.Button(w, text="登录", command=self.ok, relief="flat",
                  bg=ACCENT, fg="#ffffff", font=(FONT, 9, "bold"),
                  activebackground="#0f5fd0").place(x=ww - 96, y=110, width=80, height=30)
        tk.Button(w, text="×", command=self.close, relief="flat",
                  bg="#ffffff", fg=MUTED, font=(FONT, 11),
                  activebackground="#f2f4f7", bd=0).place(x=ww - 34, y=4, width=28, height=26)
        ent.bind("<Return>", lambda e: self.ok())
        try:
            w.grab_set()
        except Exception:
            pass

    def ok(self):
        txt = self.var.get()
        self.close()
        self.app.apply_cookie(txt)

    def close(self):
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass


class App:
    def __init__(self, autostart_hidden=True):
        self.cfg = load_cfg()
        self.q = queue.Queue()
        self.sess = ""
        self.ip = ""
        self.dev = None
        self.key = ""
        self.games = []
        self.gmap = {}
        self.zones = {}
        self.servers = {}
        self.games_ts = 0.0
        self.r_disc = R_DISC
        self.cover_img = None
        self.bg_img = None
        self.router = None
        self.router_ts = 0.0
        self.recent = list(self.cfg.get("recent") or [])
        self.cover_gid = None
        self.cover_tried = {}
        self.busy = 0
        self.panel = None
        self.stopping = False
        self.state = {"mode": "idle", "game": "", "zone": "", "server": "",
                      "note": "", "gid": "", "icon": ""}

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        self.cv = tk.Canvas(self.root, width=BALL, height=BALL, bg=KEY,
                            highlightthickness=0, bd=0)
        self.cv.pack()
        guard(self.root)

        self.draw_art()
        self.bind_ball()
        self.place_ball()
        self.root.update_idletasks()
        try:
            self.root.attributes("-alpha", 0.0)
            self.root.attributes("-transparentcolor", KEY)
        except Exception as exc:
            _log("透明色设置失败: %r" % (exc,))

        self.menu = tk.Menu(self.root, tearoff=0, font=(FONT, 9))
        self.menu.add_command(label="选择游戏…", command=self.open_panel)
        self.menu.add_command(label="停止加速", command=lambda: self.act_stop())
        self.menu.add_separator()
        self.menu.add_command(label="登录 / 更换账号…", command=self.do_login)
        self.menu.add_command(label="刷新状态", command=self.force_refresh)
        self.menu.add_command(label="退出", command=self.quit)

        self.render()
        self.root.after(50, self.pump)
        self.root.after(120, self.boot)
        self.root.after(30, self.play_intro)

    # ------------------------------------------------------------ 小球绘制
    def draw_art(self):
        self.paint()

    def paint(self):
        """整颗球重画：白球打底；有封面就把封面盖满圆内；没封面就显示状态字。"""
        cv = self.cv
        cv.delete("all")
        cx = cy = BALL / 2.0
        r = R_DISC
        st = self.state
        mode = st.get("mode")
        img = self.cover_img if mode == "acc" else None
        bg = self.bg_img if mode == "acc" else None
        for i, rr in enumerate((r + 6.0, r + 4.2, r + 2.2)):
            disc(cv, cx, cy + 1.2, rr, mix(KEY, SHADOW, 0.22 + 0.20 * i), KEY)
        if bg is not None:
            # 背景铺满整个圆：方形图 + 遮罩切圆，白球只在没背景时露出来
            cv.create_image(cx, cy, image=bg)
            self._mask_corners(cx, cy, r)
        else:
            disc(cv, cx, cy, r, BALL_FILL, KEY)
        if img is not None:
            cv.create_image(cx, cy, image=img)
            iw, ih = img.width(), img.height()
            if not getattr(self, "cover_fits", False):
                self._mask_corners(cx, cy, r)
            return
        t1, t2 = "", ""
        if mode == "acc":
            t1 = "已加速"
        elif mode == "busy":
            t1 = short(st.get("note") or "处理中…", 7)
        elif mode == "nologin":
            t1 = "未登录"
            t2 = short(self.state.get("note") or "点我登录", 12)
        else:
            t1, t2 = "未加速", "点我选择"
        if t1:
            cv.create_text(cx, cy - (7 if t2 else 0), text=t1, justify="center",
                           font=(FONT, 9, "bold"), fill=INK)
        if t2:
            cv.create_text(cx, cy + 12, text=t2, justify="center",
                           font=(FONT, 7), fill=MUTED)

    def _mask_corners(self, cx, cy, r, seg=18):
        """把圆外的一切涂成 KEY（= 透明）。封面图比圆盘大，只切四角会留下
        一圈边框，所以先把圆的外接正方形以外的四条边条整块盖掉，再切四角。"""
        cv = self.cv
        cv.create_rectangle(0, 0, BALL, cy - r, fill=KEY, outline=KEY, width=0)
        cv.create_rectangle(0, cy + r, BALL, BALL, fill=KEY, outline=KEY, width=0)
        cv.create_rectangle(0, cy - r, cx - r, cy + r, fill=KEY, outline=KEY, width=0)
        cv.create_rectangle(cx + r, cy - r, BALL, cy + r, fill=KEY, outline=KEY, width=0)
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            pts = []
            for k in range(seg + 1):
                th = (math.pi / 2.0) * k / seg
                pts.append((cx + sx * r * math.cos(th), cy + sy * r * math.sin(th)))
            pts.append((cx + sx * r, cy + sy * r))
            cv.create_polygon(pts, fill=KEY, outline=KEY, width=0)

    def cover_file(self, gid, w=0):
        tag = "w%d" % w if w else "c%d" % COVER_PX
        return os.path.join(COVER_DIR, "%s-%s.png" % (gid, tag))

    def bg_file(self, gid):
        return os.path.join(COVER_DIR, "%s-b%d.png" % (gid, BG_PX))

    def find_cover(self, gid):
        """优先用「按圆内尺寸向 CDN 取的那份」，其次退回旧的原图缓存。"""
        try:
            for name in os.listdir(COVER_DIR):
                if name.startswith(gid + "-w") and name.endswith(".png"):
                    return os.path.join(COVER_DIR, name)
        except Exception:
            pass
        return self.cover_file(gid)

    def cover_url(self, gid, url):
        """优先用游戏库里的大图（真 PNG，可能是竖版海报），退回 icon_url。"""
        meta = self.gmap.get(gid) or {}
        return meta.get("large") or url or meta.get("icon") or ""

    def want_cover(self, gid, url):
        if not gid:
            return
        if not self.gmap:
            # 游戏库还没加载好，此时只拿得到 32px 的小图标；
            # 等 load_games 完成后再抓，才能用上 large_icon_url 的大图。
            return
        if self.cover_gid == gid:
            return
        self.cover_gid = gid
        self.cover_img = None
        self.bg_img = None
        path = self.find_cover(gid)
        if os.path.exists(path) and os.path.getsize(path) > 200:
            self.load_cover(path)
            if os.path.exists(self.bg_file(gid)):
                self.load_bg(gid)          # 缓存命中也要把背景装上
            else:
                best = self.cover_url(gid, url)
                if best and not self.cover_tried.get("b" + gid):
                    self.cover_tried["b" + gid] = 1
                    threading.Thread(target=self._fetch_bg, args=(gid, best),
                                     daemon=True).start()
            return
        best = self.cover_url(gid, url)
        if not best or self.cover_tried.get(gid):
            return
        self.cover_tried[gid] = 1
        threading.Thread(target=self._fetch_cover, args=(gid, best),
                         daemon=True).start()

    def _fetch_cover(self, gid, url):
        """按圆内可容纳的尺寸向 CDN 取图；取不到就退回原图。"""
        try:
            size = None
            probe = fop_w(url, 40)
            if probe:
                try:
                    size = png_size(http_get(probe, timeout=8.0))
                except Exception as exc:
                    _log("cover probe: %r" % (exc,))
            data = b""
            want_w = 0
            if size:
                want_w, _ = fit_size(size[0], size[1])
                try:
                    data = http_get(fop_w(url, want_w))
                except Exception as exc:
                    _log("cover sized: %r" % (exc,))
                if png_size(data) is None:
                    data = b""
            if not data:
                # 兜底：原图（后面会按整数倍缩小，必要时仍然遮罩成圆）
                want_w = 0
                data = http_get(url)
            if not data or len(data) < 200:
                _log("cover: 空响应")
                return
            real = png_size(data)
            if real is None:
                _log("cover: 不是 PNG，放弃")
                return
            try:
                os.makedirs(COVER_DIR, exist_ok=True)
            except Exception:
                pass
            path = self.cover_file(gid, want_w)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            _log("cover: %s -> %dx%d (want w=%d)" % (gid[-6:], real[0], real[1], want_w))
            self.q.put(("cover", gid))
            if os.path.exists(self.bg_file(gid)):
                self.q.put(("bg", gid))     # 已有背景图，交回主线程去装
            else:
                self._fetch_bg(gid, url)
        except Exception as exc:
            _log("cover: %r" % (exc,))

    def _fetch_bg(self, gid, url):
        """另取一张 104 宽的图，本地中心裁成方形给背景用（CDN 不会帮我们裁）。"""
        try:
            if not url:
                return
            data = http_get(fop_w(url, BG_PX))
            size = png_size(data)
            if not data or len(data) < 200 or size is None:
                _log("bg: 取图失败")
                return
            try:
                os.makedirs(COVER_DIR, exist_ok=True)
            except Exception:
                pass
            path = self.bg_file(gid)
            tmp = path + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            _log("bg: %s -> %dx%d" % (gid[-6:], size[0], size[1]))
            self.q.put(("bg", gid))
        except Exception as exc:
            _log("bg: %r" % (exc,))

    def load_bg(self, gid):
        """背景图：中心方形裁切 -> 缩小再放大的块状柔化 -> 压暗，正好铺满圆。"""
        self.bg_img = None
        try:
            path = self.bg_file(gid)
            if not os.path.exists(path):
                return
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            if not w or not h:
                return
            side = min(w, h)
            x1, y1 = (w - side) // 2, (h - side) // 2
            img = img.copy(from_coords=(x1, y1, x1 + side, y1 + side))
            k = max(1, side // 26)
            if k > 1:                      # 先缩小、再放回来 = 马赛克柔化
                img = img.subsample(k, k)
                img = img.zoom(k, k)
            if img.width() < BG_PX:        # 还太小就整数放大
                z = max(1, int(math.ceil(BG_PX / float(max(1, img.width())))))
                if z > 1:
                    img = img.zoom(z, z)
            if img.width() > BG_PX:        # 太大就裁中心正方形
                s = img.width()
                o = (s - BG_PX) // 2
                img = img.copy(from_coords=(o, o, o + BG_PX, o + BG_PX))
            self.bg_img = dim_img(self.root, img, 0.42)
            _log("bg load: %dx%d" % (self.bg_img.width(), self.bg_img.height()))
        except Exception as exc:
            _log("bg load: %r" % (exc,))
            self.bg_img = None

    def load_cover(self, path):
        """整图等比放进圆里：太小的整数放大，太大的整数缩小；
        放下之后就不需要方形遮罩了（自然落在圆内）。"""
        try:
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            if not w or not h:
                raise ValueError("empty image")
            target = 2.0 * R_DISC * 0.93
            d = math.hypot(w, h)
            if d < target * 0.6:                      # 小图：整数放大
                z = max(1, int(target / d))
                if z > 1:
                    img = img.zoom(z, z)
                    w, h = img.width(), img.height()
            d = math.hypot(w, h)
            if d > 2.0 * R_DISC * 0.99:               # 还是太大：整数缩小
                k = int(math.ceil(d / (2.0 * R_DISC * 0.93)))
                if k > 1:
                    img = img.subsample(k, k)
            self.cover_img = img
            self.cover_size = (img.width(), img.height())
            self.cover_fits = math.hypot(*self.cover_size) / 2.0 <= R_DISC
            _log("cover load: %dx%d fits=%s" % (self.cover_size[0], self.cover_size[1],
                                                self.cover_fits))
        except Exception as exc:
            _log("cover load: %r" % (exc,))
            self.cover_img = None
            self.cover_fits = False

    # ------------------------------------------------------------ 开启动画
    def play_intro(self):
        self._pos = (self.root.winfo_x(), self.root.winfo_y())
        self._intro = {"t0": time.perf_counter()}
        self._intro_tick()

    def _intro_tick(self):
        t = (time.perf_counter() - self._intro["t0"]) / 0.42
        if t > 1.0:
            t = 1.0
        e = 1.0 - (1.0 - t) ** 3          # ease-out cubic
        x, y = self._pos
        try:
            self.root.attributes("-alpha", max(0.03, ALPHA_BALL * e))
            self.root.geometry("+%d+%d" % (x, y + int(round((1.0 - e) * 16))))
        except Exception:
            return
        if t < 1.0:
            self.root.after(15, self._intro_tick)
        else:
            self.root.after(40, self.play_halo)

    def play_halo(self):
        self._halo = {"t0": time.perf_counter(), "id": None}
        self._halo_tick()

    def _halo_tick(self):
        h = self._halo
        t = (time.perf_counter() - h["t0"]) / 0.7
        cx = cy = BALL / 2.0
        if h["id"] is not None:
            try:
                self.cv.delete(h["id"])
            except Exception:
                pass
            h["id"] = None
        if t >= 1.0:
            return
        rr = R_DISC + 6.0 * (1.0 - (1.0 - t) ** 2)
        col = mix(KEY, "#ffffff", 0.80 * (1.0 - t))
        try:
            h["id"] = self.cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr,
                                         start=0, extent=359.99, style="arc",
                                         outline=col, width=2)
        except Exception:
            return
        self.root.after(22, self._halo_tick)

    def place_ball(self):
        pos = self.cfg.get("ball_pos")
        vx, vy, vw, vh = virtual_bounds()
        if vw is None:
            vw, vh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            x, y = int(pos[0]), int(pos[1])
        else:
            x, y = self.secondary_corner()
            if x is None:
                x, y = vx + vw - BALL - 60, vy + 90
        x = max(vx - BALL + 40, min(x, vx + vw - 40))
        y = max(vy, min(y, vy + vh - 40))
        self.root.geometry("%dx%d+%d+%d" % (BALL, BALL, x, y))

    def secondary_corner(self):
        """有副屏就把球放副屏右上角。"""
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

            rects = []
            proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                       ctypes.POINTER(RECT), wintypes.LPARAM)

            def cb(hmon, hdc, lprc, data):
                r = lprc.contents
                rects.append((r.left, r.top, r.right, r.bottom))
                return 1

            ctypes.windll.user32.EnumDisplayMonitors(None, None, proto(cb), 0)
            for l, t, r, b in rects:
                if not (l <= 0 < r and t <= 0 < b):
                    return (r - BALL - 46, t + 46)
        except Exception:
            pass
        return (None, None)

    # ------------------------------------------------------------ 交互
    def bind_ball(self):
        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.cv.bind("<Button-3>", self.on_menu)
        self.cv.configure(cursor="hand2")

    def on_press(self, ev):
        self._press = (ev.x_root, ev.y_root,
                       self.root.winfo_x(), self.root.winfo_y())
        self._moved = False

    def on_drag(self, ev):
        if not getattr(self, "_press", None):
            return
        dx = abs(ev.x_root - self._press[0])
        dy = abs(ev.y_root - self._press[1])
        if dx > 4 or dy > 4:
            self._moved = True
        x = self._press[2] + (ev.x_root - self._press[0])
        y = self._press[3] + (ev.y_root - self._press[1])
        self.root.geometry("+%d+%d" % (x, y))

    def on_release(self, ev):
        if getattr(self, "_moved", False):
            self.cfg["ball_pos"] = [self.root.winfo_x(), self.root.winfo_y()]
            save_cfg(self.cfg)
        else:
            self.toggle_panel()

    def on_menu(self, ev):
        try:
            self.menu.tk_popup(ev.x_root, ev.y_root)
        finally:
            self.menu.grab_release()

    def toggle_panel(self):
        if self.panel is not None:
            self.close_panel()
            return
        if self.state.get("mode") == "nologin":
            self.do_login()
            return
        self.open_panel()

    def do_login(self, parent=None):
        LoginDialog(self, parent)

    def apply_cookie(self, txt):
        try:
            cookie = (txt or "").strip()
            if not cookie:
                return
            m = re.search(r"sess=([0-9a-fA-F-]{8,})", cookie)
            sess = m.group(1) if m else ""
            if not sess and re.match(r"^[0-9a-fA-F-]{16,}$", cookie):
                sess = cookie
                cookie = "sess=" + cookie
            if not sess:
                raise ValueError("Cookie 里没有 sess=")
            sn = (self.router or {}).get("sn") or ""
            if not sn:
                raise ValueError("还没探测到路由器上的 UU 插件，"
                                 "先确认它开着（16363 端口）再登录")
            uu.set_sn(sn)
            data = {"sess": sess, "cookie": cookie, "sn": sn}
            with open(uu.SESSION_FILE, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, ensure_ascii=False, indent=1))
            self.sess = ""
            _log("login: saved sess=%s… -> %s" % (sess[:8], uu.SESSION_FILE))
            self.q.put(("state", {"mode": "busy", "note": "正在验证登录…"}))
            threading.Thread(target=self.verify_login, daemon=True).start()
        except Exception as exc:  # noqa: BLE001
            _log("login: %r" % (exc,))
            self.q.put(("state", {"mode": "nologin",
                                  "note": "登录失败：%s" % exc}))

    def verify_login(self):
        """登录后立刻打一次 /sess + /devices，把结果反馈到球上。"""
        try:
            sess, logged, _ = uu.cloud_session()
        except SystemExit:
            self.q.put(("state", {"mode": "nologin",
                                  "note": "失败：没探测到路由器"}))
            return
        except Exception as exc:  # noqa: BLE001
            self.q.put(("state", {"mode": "nologin",
                                  "note": "失败：%s" % exc}))
            return
        if not logged:
            _log("login: uu_logged_in=false")
            self.q.put(("state", {"mode": "nologin",
                                  "note": "Cookie 无效或已过期"}))
            return
        self.sess = sess
        _log("login: 验证通过")
        self.load_games()
        self.refresh_cloud()

    def open_panel(self):
        if self.panel is not None:
            return
        self.panel = Panel(self)

    def close_panel(self):
        if self.panel is not None:
            try:
                self.panel.win.destroy()
            except Exception:
                pass
            self.panel = None

    def quit(self):
        self.stopping = True
        self.snap = {"geom": "", "panel": "", "hits": -1}
        try:
            self.snap["geom"] = self.root.winfo_geometry()
        except Exception:
            pass
        try:
            c = self.cover_img
            self.snap["cover"] = (c.width(), c.height()) if c is not None else None
        except Exception:
            self.snap["cover"] = None
        if self.panel is not None:
            try:
                self.snap["panel"] = self.panel.win.winfo_geometry()
                self.snap["hits"] = len(self.panel.hits)
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------ 状态刷新
    def force_refresh(self):
        self.q.put(("refresh", None))

    def set_state(self, **kw):
        self.state.update(kw)
        self.render()

    def render(self):
        st = self.state
        if st.get("mode") == "acc":
            self.want_cover(st.get("gid") or "", st.get("icon") or "")
        else:
            self.cover_gid = None
            self.cover_img = None
        self.paint()

    # ------------------------------------------------------------ 启动流程
    def boot(self):
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        self.scan_router()
        self.refresh_cloud(first=True)
        self.load_games()
        self.q.put(("refresh", None))     # 游戏库就绪，重抓一次封面
        while not self.stopping:
            time.sleep(4.0)
            if self.busy:
                continue
            self.refresh_cloud()
            # 还没认到路由器就每 25s 重试（插件刚起/刚开机都能自动接上），
            # 认到之后 5 分钟复检一次，掉线也能被发现。
            wait = 300.0 if self.router else 25.0
            if time.time() - self.router_ts > wait:
                self.scan_router()

    # ------------------------------------------------------------ 路由器
    def scan_router(self):
        try:
            info = detect_router(self.cfg)
        except Exception as exc:
            _log("scan_router: %r" % (exc,))
            info = None
        self.router_ts = time.time()
        if not info:
            if self.router is None:
                _log("router: 没探测到 UU 路由器")
            return
        if self.router != info:
            _log("router: %s %s %s sn=%s" % (info["ip"], info.get("type"),
                                             info.get("model"), info.get("sn")))
        self.router = info
        uu.set_sn(info.get("sn") or "")
        self.check_session_owner(info.get("sn") or "")
        if self.cfg.get("router_ip") != info["ip"]:
            self.cfg["router_ip"] = info["ip"]
            self.cfg["router_sn"] = info.get("sn") or ""
            save_cfg(self.cfg)

    def check_session_owner(self, sn):
        """session.json 是从别的机器/别的路由器拷来的话，直接作废。

        云端 /api/sess 用 sn 判定「这是哪台路由器」。sn 对不上还沿用旧 cookie，
        就会去改别人家路由器上的加速设置 —— 别人拿到的安装包带着我们的
        session.json 时，正是这样把我们的加速改掉的。
        """
        if not sn:
            return
        try:
            st = uu.load_session()
        except Exception:
            return
        old = (st.get("sn") or "").strip()
        if old and old.lower() != sn.lower():
            uu.save_session({"sn": sn})
            self.sess = ""
            _log("session: 属于 %s，本机是 %s，已丢弃旧登录态" % (old, sn))
            self.q.put(("state", {"mode": "nologin",
                                  "note": "路由器变了，请重新登录"}))

    # ------------------------------------------------------------ 最近游玩
    def note_recent(self, gid, name, zone="", server="", icon=""):
        if not gid or not name:
            return
        cur = {"gid": gid, "name": name, "zone": zone or "",
               "server": server or "", "icon": icon or "",
               "ts": int(time.time())}
        top = self.recent[0] if self.recent else {}
        if (top.get("gid") == cur["gid"] and (top.get("zone") or "") == cur["zone"]
                and (top.get("name") or "") == cur["name"]):
            return
        lst = [r for r in self.recent if r.get("gid") != gid]
        lst.insert(0, cur)
        self.recent = lst[:6]
        self.cfg["recent"] = self.recent
        save_cfg(self.cfg)
        if self.panel is not None:
            try:
                self.panel.refilter()
            except Exception:
                pass

    def self_device(self, ip):
        info = {"type": "windows",
                "mac": self.cfg.get("mac") or local_mac(),
                "ip": ip,
                "hostname": socket.gethostname()}
        return {"deviceinfo": info, "acc_status": "not_acc"}

    def refresh_cloud(self, first=False):
        try:
            if not self.sess:
                self.sess, logged, _ = uu.cloud_session()
                if not logged:
                    self.q.put(("state", {"mode": "nologin",
                                          "note": "登录已过期"}))
                    return
            res = uu.devices(self.sess)
            if res is None:
                self.sess = ""
                self.q.put(("state", {"mode": "nologin"}))
                return
            ip = local_ip()
            self.ip = ip
            devs = res.get("devices") or []
            hit = None
            for d in devs:
                i = d.get("deviceinfo") or {}
                if i.get("ip") == ip and i.get("type") == "windows":
                    hit = d
                    break
            if hit is None:
                for d in devs:
                    i = d.get("deviceinfo") or {}
                    if i.get("ip") == ip:
                        hit = d
                        break
            if hit is None:
                # 只用「现在这台机器」的 MAC；配置文件里的 mac 可能是别的机器的
                # （换电脑/拷目录），拿它匹配会把别人的设备当成自己。
                lmac = local_mac()
                if lmac:
                    for d in devs:
                        i = d.get("deviceinfo") or {}
                        if str(i.get("mac", "")).lower() == lmac.lower():
                            hit = d
                            break
            if hit is None:
                # 换电脑后云端还没有本机记录：用本机信息先构造一个，
                # 真正 /acc 时后端会把设备注册进这台路由器的设备表。
                hit = self.self_device(ip)
                _log("device: 云端无本机记录，临时构造 ip=%s mac=%s"
                     % (ip, hit["deviceinfo"].get("mac")))
            self.dev = hit
            info = hit.get("deviceinfo") or {}
            self.cfg["mac"] = info.get("mac")
            self.key = "%s-%s" % (info.get("type"), info.get("mac"))
            sett = ((res.get("game_mode_setting") or {}).get("device_setting")
                    or {}).get(self.key) or {}
            acced = hit.get("acc_status") == "acced"
            if acced:
                top = self.recent[0] if self.recent else {}
                if (top.get("gid") != sett.get("game_id")
                        or (top.get("zone") or "") != (sett.get("zone_name") or "")):
                    self.note_recent(sett.get("game_id"), sett.get("game_name"),
                                     sett.get("zone_name"), sett.get("server_name"),
                                     sett.get("icon_url"))
                self.q.put(("state", {"mode": "acc",
                                      "game": sett.get("game_name") or "",
                                      "zone": sett.get("zone_name") or "",
                                      "server": sett.get("server_name") or "",
                                      "gid": sett.get("game_id") or "",
                                      "icon": sett.get("icon_url") or ""}))
            else:
                self.q.put(("state", {"mode": "idle"}))
        except SystemExit as exc:
            self.sess = ""
            no_router = str(exc) == "4"
            self.q.put(("state", {"mode": "nologin",
                                  "note": "没探测到路由器" if no_router
                                          else "登录已过期"}))
        except Exception as exc:
            _log("refresh_cloud: %r" % (exc,))

    # ------------------------------------------------------------ 游戏库
    def load_games(self):
        try:
            st = None
            try:
                with open(CACHE_FILE, encoding="utf-8") as fh:
                    st = json.load(fh)
            except Exception:
                st = None
            if not st or time.time() - st.get("ts", 0) > 86400:
                sess = self.sess or uu.cloud_session()[0]
                gl, zo, se = uu.load_gamelist(sess, "pc")
                st = {"ts": time.time(), "gamelist": gl, "zonelist": zo, "serverlist": se}
                try:
                    with open(CACHE_FILE, "w", encoding="utf-8") as fh:
                        json.dump(st, fh, ensure_ascii=False)
                except Exception:
                    pass
            self.zones = st.get("zonelist") or {}
            self.servers = st.get("serverlist") or {}
            self.games = uu.all_games(st.get("gamelist") or {})
            self.games.sort(key=lambda g: str(g.get("game_name", "")))
            self.gmap = {}
            for g in self.games:
                gid = g.get("game_id")
                if gid:
                    self.gmap[gid] = {"large": g.get("large_icon_url") or "",
                                      "icon": g.get("icon_url") or ""}
            self.q.put(("games", len(self.games)))
        except SystemExit:
            pass
        except Exception as exc:
            _log("load_games: %r" % (exc,))

    def zones_of(self, gid):
        return [z for z in (self.zones.get(gid) or []) if z.get("zone_id")]

    # ------------------------------------------------------------ 动作
    def act_accel(self, game, zone_name, server_name=None):
        self.busy += 1
        self.q.put(("state", {"mode": "busy", "note": "正在加速…"}))
        threading.Thread(target=self._accel,
                         args=(game, zone_name, server_name), daemon=True).start()

    def _accel(self, game, zone_name, server_name=None):
        try:
            sess = self.sess or uu.cloud_session()[0]
            dev = self.dev
            if dev is None:
                raise RuntimeError("还没有锁定本机")
            setting = uu.build_setting(dev, game, self.zones, self.servers,
                                       zone_name, server_name)
            r = uu.api_call("POST", "/acc-mode-setting",
                            {"acc_mode": "game", "game_mode_setting": [setting]}, sess=sess)
            if r.get("status") != "ok":
                raise RuntimeError("设置游戏失败: %s" % json.dumps(r, ensure_ascii=False)[:120])
            info = dev.get("deviceinfo") or {}
            r = uu.api_call("POST", "/acc", {"deviceinfo": info}, sess=sess)
            if r.get("status") not in ("ok", "acced", "starting"):
                raise RuntimeError("加速失败: %s" % json.dumps(r, ensure_ascii=False)[:120])
            self.note_recent(setting.get("game_id"), setting.get("game_name"),
                             setting.get("zone_name"), setting.get("server_name"),
                             setting.get("icon_url"))
            self.q.put(("done", "已加速 %s" % setting.get("game_name")))
            self.q.put(("state", {"mode": "acc", "game": setting.get("game_name", ""),
                                  "zone": setting.get("zone_name", "") or "自动",
                                  "server": setting.get("server_name", ""),
                                  "gid": setting.get("game_id", ""),
                                  "icon": setting.get("icon_url", "")}))
        except SystemExit:
            self.q.put(("done", "云端接口出错（登录态可能过期）"))
        except Exception as exc:
            _log("_accel: %r" % (exc,))
            self.q.put(("done", str(exc)[:90]))
        finally:
            self.busy = max(0, self.busy - 1)

    def act_stop(self):
        self.busy += 1
        self.q.put(("state", {"mode": "busy", "note": "正在停止…"}))
        threading.Thread(target=self._stop, daemon=True).start()

    def _stop(self):
        try:
            sess = self.sess or uu.cloud_session()[0]
            info = (self.dev or {}).get("deviceinfo") or {}
            r = uu.api_call("POST", "/stop-acc", {"deviceinfo": info}, sess=sess)
            if r.get("status") not in ("ok", "not_acc", "stopping"):
                raise RuntimeError("停止失败: %s" % json.dumps(r, ensure_ascii=False)[:120])
            self.q.put(("done", "已停止加速"))
            self.q.put(("state", {"mode": "idle"}))
        except SystemExit:
            self.q.put(("done", "云端接口出错（登录态可能过期）"))
        except Exception as exc:
            _log("_stop: %r" % (exc,))
            self.q.put(("done", str(exc)[:90]))
        finally:
            self.busy = max(0, self.busy - 1)

    # ------------------------------------------------------------ 队列泵
    def pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "state":
                    self.state.update(payload)
                    self.render()
                elif kind == "cover":
                    if payload and payload == self.cover_gid:
                        self.load_cover(self.find_cover(payload))
                        self.paint()
                elif kind == "bg":
                    if payload and payload == self.cover_gid:
                        self.load_bg(payload)
                        self.paint()
                elif kind == "refresh":
                    threading.Thread(target=self.refresh_cloud, daemon=True).start()
                elif kind == "done":
                    _log("done: %s" % payload)
                    if self.panel is not None:
                        self.panel.status(payload)
                        if payload.startswith("已加速") or payload.startswith("已停止"):
                            self.close_panel()
                elif kind == "games":
                    if self.panel is not None:
                        self.panel.refilter()
        except queue.Empty:
            pass
        except Exception as exc:
            _log("pump: %r" % (exc,))
        if not self.stopping:
            self.root.after(60, self.pump)

    def run(self):
        self.root.mainloop()


# ----------------------------------------------------------------- 搜索面板
class Panel:
    """点球弹出的面板：搜索框 + 最近游玩 + 按首字符分组的全部游戏 + 区服/服务器。"""

    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        self.cv = tk.Canvas(self.win, width=PANEL_W, height=PANEL_H, bg=KEY,
                            highlightthickness=0, bd=0)
        self.cv.place(x=0, y=0, width=PANEL_W, height=PANEL_H)
        round_rect(self.cv, 0, 0, PANEL_W, PANEL_H, 16, "#ffffff", KEY)

        self.sel = None
        self.zone_name = None
        self.server_name = None
        self.chips = {}
        self.rows = []
        self.hits = []

        self.tk_title()
        self.tk_search()
        self.tk_list()
        self.tk_zones()
        self.tk_servers()
        self.tk_buttons()

        self.place_window()
        self.win.update_idletasks()
        try:
            self.win.attributes("-alpha", 0.985)
            self.win.attributes("-transparentcolor", KEY)
        except Exception as exc:
            _log("panel 透明色失败: %r" % (exc,))

        self.win.bind("<Escape>", lambda e: app.close_panel())
        self.refilter()
        self.win.after(80, self.focus_entry)
        st = app.state
        if st["mode"] == "acc" and st["game"]:
            self.status("%s · %s" % (st["game"], st["zone"] or "自动"))

    # -------------------------------------------------------------- 控件
    def tk_title(self):
        tk.Label(self.win, text="选择游戏", bg="#ffffff", fg=INK,
                 font=(FONT, 11, "bold")).place(x=18, y=14)
        dev = (self.app.dev or {}).get("deviceinfo") or {}
        r = self.app.router or {}
        txt = "%s · %s" % (r.get("model") or "未连路由器", dev.get("ip", "?"))
        tk.Label(self.win, text=txt, bg="#ffffff", fg=MUTED,
                 font=(FONT, 8)).place(x=92, y=17)
        x = tk.Label(self.win, text="✕", bg="#ffffff", fg=MUTED,
                     font=(FONT, 11), cursor="hand2")
        x.place(x=PANEL_W - 34, y=13)
        x.bind("<Button-1>", lambda e: self.app.close_panel())

    def tk_search(self):
        self.var = tk.StringVar()
        self.entry = tk.Entry(self.win, textvariable=self.var, relief="flat", bd=0,
                              bg="#f3f5f7", fg=INK, insertbackground=INK,
                              font=(FONT, 11), highlightthickness=0)
        self.entry.place(x=18, y=44, width=PANEL_W - 36, height=30)
        self.var.trace_add("write", lambda *a: self.refilter())
        self.entry.bind("<Return>", lambda e: self.pick_first())

    def tk_list(self):
        wrap = tk.Frame(self.win, bg="#ffffff")
        wrap.place(x=18, y=82, width=PANEL_W - 36, height=224)
        self.lb = tk.Listbox(wrap, bd=0, relief="flat", highlightthickness=0,
                             activestyle="none", font=(FONT, 10), bg="#ffffff",
                             fg=INK, selectbackground="#e8f1ff", selectforeground=ACCENT,
                             exportselection=False)
        sb = tk.Scrollbar(wrap, width=8, bd=0, relief="flat", highlightthickness=0)
        sb.configure(command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.lb.pack(side="left", fill="both", expand=True)
        self.lb.bind("<Button-1>", self.on_click, add="+")
        self.lb.bind("<<ListboxSelect>>", self.on_pick)
        self.lb.bind("<Double-Button-1>", self.on_dbl)

    def tk_zones(self):
        tk.Label(self.win, text="区服", bg="#ffffff", fg=MUTED,
                 font=(FONT, 9)).place(x=18, y=312)
        self.zone_frame = tk.Frame(self.win, bg="#ffffff")
        self.zone_frame.place(x=18, y=332, width=PANEL_W - 36, height=98)

    def tk_servers(self):
        self.lbl_srv = tk.Label(self.win, text="服务器", bg="#ffffff", fg=MUTED,
                                font=(FONT, 9))
        self.lbl_srv.place(x=18, y=436)
        self.cmb_srv = ttk.Combobox(self.win, values=[], state="readonly",
                                    font=(FONT, 9), height=16)
        self.cmb_srv.place(x=18, y=456, width=PANEL_W - 36, height=28)
        self.cmb_srv.bind("<<ComboboxSelected>>", self.on_srv)
        self.show_servers(False)

    def tk_buttons(self):
        self.btn_ok = tk.Button(self.win, text="开始加速", bd=0, relief="flat",
                                bg=ACCENT, fg="#ffffff", activebackground="#0e5fd8",
                                activeforeground="#ffffff", font=(FONT, 10, "bold"),
                                cursor="hand2", command=self.confirm)
        self.btn_ok.place(x=18, y=PANEL_H - 62, width=210, height=38)
        self.btn_stop = tk.Button(self.win, text="停止", bd=0, relief="flat",
                                  bg=CHIP_BG, fg=INK, activebackground="#e6e9ee",
                                  font=(FONT, 10), cursor="hand2", command=self.stop)
        self.btn_stop.place(x=PANEL_W - 18 - 118, y=PANEL_H - 62, width=118, height=38)
        self.lbl_status = tk.Label(self.win, text="", bg="#ffffff", fg=MUTED,
                                   font=(FONT, 8), anchor="w")
        self.lbl_status.place(x=18, y=PANEL_H - 20, width=PANEL_W - 36)

    def place_window(self):
        r = self.app.root
        bx, by = r.winfo_x(), r.winfo_y()
        x = bx - PANEL_W - 12
        if x < 0:
            x = bx + BALL + 12
        y = by + BALL // 2 - PANEL_H // 2
        vx, vy, vw, vh = virtual_bounds()
        if vw is None:
            vw, vh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        x = max(vx, min(x, vx + vw - PANEL_W))
        y = max(vy, min(y, vy + vh - PANEL_H))
        self.win.geometry("%dx%d+%d+%d" % (PANEL_W, PANEL_H, x, y))

    def focus_entry(self):
        try:
            self.win.focus_force()
            self.entry.focus_set()
        except Exception:
            pass

    # -------------------------------------------------------------- 列表
    def refilter(self):
        q = (self.var.get() or "").strip().lower()
        games = self.app.games or []
        rows = []
        if q:
            hits = [g for g in games if q in str(g.get("game_name", "")).lower()]
            head = [g for g in hits if str(g.get("game_name", "")).lower().startswith(q)]
            rest = [g for g in hits if g not in head]
            head.sort(key=lambda g: sort_key(g.get("game_name")))
            rest.sort(key=lambda g: sort_key(g.get("game_name")))
            for g in (head + rest)[:200]:
                rows.append(("game", g))
        else:
            rec = (self.app.recent or [])[:5]
            if rec:
                rows.append(("head", "最近游玩"))
                for r in rec:
                    rows.append(("recent", r))
            last = None
            for g in sorted(games, key=lambda g: sort_key(g.get("game_name"))):
                grp = initial_of(g.get("game_name"))
                if grp != last:
                    rows.append(("head", "0-9" if grp == "0" else
                                 ("其他" if grp == "#" else grp)))
                    last = grp
                rows.append(("game", g))
        self.rows = rows
        self.hits = [v for k, v in rows if k == "game"]
        self.lb.delete(0, "end")
        for kind, val in rows:
            if kind == "head":
                self.lb.insert("end", " " + str(val))
            elif kind == "recent":
                self.lb.insert("end", "  ★ %s   · %s"
                               % (short(val.get("name"), 13),
                                  short(val.get("zone") or "自动", 7)))
            else:
                self.lb.insert("end", "    " + str(val.get("game_name", "")))
        for i, (kind, _v) in enumerate(rows):
            if kind == "head":
                self.lb.itemconfig(i, foreground=MUTED, background="#f6f7f9",
                                   selectbackground="#f6f7f9",
                                   selectforeground=MUTED)
            elif kind == "recent":
                self.lb.itemconfig(i, foreground=INK, background="#eef5ff",
                                   selectbackground="#dbe9ff",
                                   selectforeground=ACCENT)

    def first_row(self):
        for i, (kind, _v) in enumerate(self.rows):
            if kind in ("recent", "game"):
                return i
        return -1

    def pick_first(self):
        i = self.first_row()
        if i < 0:
            return
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        self.on_pick(None)

    def game_of(self, gid, name=""):
        for g in self.app.games or []:
            if gid and (g.get("game_id") == gid or g.get("_id") == gid):
                return g
        return {"game_id": gid, "game_name": name or "", "icon_url": ""}

    def on_click(self, ev):
        i = self.lb.nearest(ev.y)
        if 0 <= i < len(self.rows) and self.rows[i][0] == "head":
            self.lb.selection_clear(0, "end")
            return "break"
        return None

    def on_pick(self, ev):
        sel = self.lb.curselection()
        if not sel:
            return
        i = sel[0]
        if i >= len(self.rows):
            return
        kind, val = self.rows[i]
        if kind == "head":
            self.lb.selection_clear(0, "end")
            return
        if kind == "recent":
            self.sel = self.game_of(val.get("gid"), val.get("name"))
            self.build_chips(preselect=val.get("zone"),
                             preselect_srv=val.get("server"))
            return
        self.sel = val
        self.build_chips()

    def on_dbl(self, ev):
        i = self.lb.nearest(ev.y)
        if i < 0 or i >= len(self.rows) or self.rows[i][0] == "head":
            return
        sel = self.lb.curselection()
        if not sel or sel[0] != i:
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.on_pick(None)
        if self.sel is None:
            return
        if self.app.dev is None:
            self.status("还没连上 UU，稍等…")
            return
        self.status("正在加速…")
        self.app.act_accel(self.sel, self.zone_name, self.server_name)

    # -------------------------------------------------------------- 区服/服务器
    def build_chips(self, preselect=None, preselect_srv=None):
        for w in self.zone_frame.winfo_children():
            w.destroy()
        self.chips = {}
        self.zone_name = None
        self.server_name = None
        self.show_servers(False)
        if not self.sel:
            return
        gid = self.sel.get("game_id") or self.sel.get("_id")
        zs = self.app.zones_of(gid)
        names = [z.get("zone_name") for z in zs] or ["自动"]
        cur = preselect
        if not cur and (self.app.state.get("mode") == "acc"
                        and self.app.state.get("game") == self.sel.get("game_name")):
            cur = self.app.state.get("zone")
        for i, name in enumerate(names[:9]):
            b = tk.Button(self.zone_frame, text=name, bd=0, relief="flat",
                          bg=CHIP_BG, fg=INK, activebackground="#dbe6f7",
                          font=(FONT, 9), cursor="hand2",
                          command=lambda n=name: self.set_zone(n))
            x = (i % 3) * 108
            y = (i // 3) * 32
            b.place(x=x, y=y, width=100, height=26)
            self.chips[name] = b
        pick = None
        if cur:
            pick = next((n for n in self.chips if cur.lower() in n.lower()), None)
        if not pick:
            pick = names[0] if names else None
        if pick:
            self.set_zone(pick, preselect_srv)

    def set_zone(self, name, preselect_srv=None):
        self.zone_name = name
        for n, b in self.chips.items():
            if n == name:
                b.configure(bg=ACCENT, fg="#ffffff", activebackground="#0e5fd8")
            else:
                b.configure(bg=CHIP_BG, fg=INK, activebackground="#dbe6f7")
        self.build_servers(preselect_srv)

    def show_servers(self, on):
        try:
            if on:
                self.lbl_srv.place(x=18, y=436)
                self.cmb_srv.place(x=18, y=456, width=PANEL_W - 36, height=28)
            else:
                self.lbl_srv.place_forget()
                self.cmb_srv.place_forget()
        except Exception:
            pass

    def build_servers(self, preselect=None):
        self.server_name = None
        gid = (self.sel or {}).get("game_id") or (self.sel or {}).get("_id")
        zs = self.app.zones_of(gid)
        zid = None
        for z in zs:
            if z.get("zone_name") == self.zone_name:
                zid = z.get("zone_id")
                break
        sl = (self.app.servers.get(zid) or []) if zid else []
        names = [str(s.get("server_name")) for s in sl if s.get("server_name")]
        if len(names) <= 1:
            self.show_servers(False)
            self.server_name = names[0] if names else None
            return
        self.show_servers(True)
        self.cmb_srv.configure(values=names)
        pick = names[0]
        if preselect:
            hit = next((n for n in names if preselect.lower() in n.lower()), None)
            if hit:
                pick = hit
        elif "所有服务器" in names:
            pick = "所有服务器"
        self.cmb_srv.set(pick)
        self.server_name = pick

    def on_srv(self, ev=None):
        self.server_name = self.cmb_srv.get() or None

    # -------------------------------------------------------------- 动作
    def confirm(self):
        if not self.sel:
            self.status("先选一个游戏")
            return
        if self.app.dev is None:
            self.status("还没连上 UU，稍等…")
            return
        self.status("正在加速…")
        self.app.act_accel(self.sel, self.zone_name, self.server_name)

    def stop(self):
        self.status("正在停止…")
        self.app.act_stop()

    def status(self, msg):
        try:
            self.lbl_status.configure(text=str(msg)[:46])
        except Exception:
            pass


# ----------------------------------------------------------------- 入口
def _alive(pid):
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def single_instance():
    """pidfile + 存活检查。

    别拿固定端口或命名互斥体当锁：49739 会落进系统保留区（bind 报 10048），
    CreateMutexW 在这个环境里也会回 ERROR_INVALID_NAME，两者都会让程序
    莫名拒绝启动。
    """
    path = os.path.join(CFG_DIR, "ball.pid")
    old = 0
    try:
        with open(path, encoding="utf-8") as fh:
            old = int((fh.read() or "0").strip() or 0)
    except Exception:
        old = 0
    if old and old != os.getpid() and _alive(old):
        return None
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except Exception:
        pass
    return True


def selftest(seconds=6.0, open_panel=False):
    app = App()
    if open_panel:
        app.root.after(2500, app.open_panel)
    app.root.after(int(seconds * 1000), lambda: app.quit())
    app.run()

    def dump():
        print("cfg_dir     =", CFG_DIR)

    try:
        print("local_ip    =", app.ip)
        print("device      =", ((app.dev or {}).get("deviceinfo") or {}))
        print("key         =", app.key)
        print("state       =", app.state)
        snap1 = getattr(app, "snap", {})
        print("cover       =", snap1.get("cover"))
        print("cover_file  =", app.cover_file(app.cover_gid) if app.cover_gid else None)
        print("games       =", len(app.games))
        print("router      =", app.router)
        print("recent      =", [(r.get("name"), r.get("zone")) for r in app.recent])
        snap = getattr(app, "snap", {})
        print("geometry    =", snap.get("geom"))
        print("panel       =", snap.get("panel"))
        print("hits        =", snap.get("hits"))
    except Exception as exc:
        print("dump error:", exc)


def seed_files():
    """onefile 解包目录里的随包文件，首次运行拷一份到 exe 旁边（用户可改）。"""
    if not FROZEN:
        return
    for name in ("session.json", "uuctl.sh", "uu_route.sh"):
        src = os.path.join(HERE, name)
        dst = os.path.join(APP_DIR, name)
        try:
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copyfile(src, dst)
                _log("seed: %s" % name)
        except Exception as exc:
            _log("seed %s: %r" % (name, exc))


def main(argv):
    seed_files()
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
    except Exception:
        pass
    if "--pos" in argv:
        # 调试用：--pos 420,260 强制小球位置
        try:
            p = argv[argv.index("--pos") + 1]
            xx, yy = (int(v) for v in p.split(","))
            cfg = load_cfg()
            cfg["ball_pos"] = [xx, yy]
            save_cfg(cfg)
        except Exception as exc:
            _log("--pos 解析失败: %r" % (exc,))
    if "--demo" in argv:
        # 真的跑起来并自动展开面板，供人工/像素验证用
        d = App()
        d.root.after(2200, d.open_panel)
        d.run()
        return 0
    if "--selftest" in argv:
        selftest(6.0, "--panel" in argv)
        return 0
    if "--probe" in argv:
        print("local_ip =", local_ip())
        print("cfg_dir  =", CFG_DIR)
        print("ball     =", BALL, "disc_r =", R_DISC, "cover_px =", COVER_PX)
        return 0
    lock = single_instance()
    if lock is None:
        _log("已有一个实例在跑，退出")
        return 0
    app = App()
    app.run()
    return 0


if __name__ == "__main__":
    ensure_streams()
    raise SystemExit(main(sys.argv[1:]))
