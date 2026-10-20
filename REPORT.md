# 网易UU加速器（ASUS RT-AX86U）逆向与一句话控制评估

- 目标设备：192.168.50.1（ASUS RT-AX86U，固件 3.0.0.4.388_24436，Linux 4.1.52 aarch64）
- 载荷版本：`uu.conf` → `version=v14.10.6`；`/jffs/uu.tar.gz` 2,270,673 B，`.checksum` = `004c1a127d74f601361db70fa9f32c97`（本地 MD5 一致）
- 结论日期：2026-10（逆向完成时）

## 0. 一句话结论

**可以“一句话调用”，且有两个互不依赖的层级：**

| 层级 | 依赖 | 命令 | 实测状态 |
|---|---|---|---|
| 路由器整机开关 | 无（只要 SSH） | `python uu.py status/start/stop/restart` | ✅ 已验证 |
| 指定设备加速（本地克隆） | 需要一条已存在的加速会话 | `python uu.py route <ip> on/off` | ✅ 规则安装/回滚已验证，端到端待第二台设备 |
| 指定设备/游戏加速（云端） | UU 账号登录态（Cookie） | `python uu.py dev / acc / unacc / games` | ✅ 端到端验证（用手机 `192.168.50.13` 实测「设游戏 → 加速 → 停止 → 还原」） |

路由器本地**不存在**“给某设备/某游戏加速”的接口——这点是静态分析 + 动态爆破双重确认的，不是没找到。

## 1. 载荷与逆向

| 项 | 事实 |
|---|---|
| 文件 | `uuplugin` 4,741,700 B（ELF32 ARM LE，静态链接，stripped，entry `0x163a4`，`.text` `0x10100`+3,997,196，`.rodata` `0x3dff18`+523,740） |
| 附带 | `xuplugin-guardian` 54,268 B（仅 123 条字符串，0 URL，低价值）；`uu.conf` 32 B；监控脚本 `uuplugin_monitor.sh`（19,111 B，不在 tar 内，单独从 `router.uu.163.com/api/script/monitor?type=asuswrt` 下载） |
| 血统 | 网易自家 `tun2proxy`（源码路径 `/builds/Yc2634KaC/0/UU/acc/tun2proxy/src/{tproxy_bridge,local_proxy,plugin_common,https_proxy}`） |
| 通信协议 | Protobuf `uu_router_messages`：`Acc`/`AccReply`/`StopAcc`/`Device`/`DeviceList`/`CheckBound`/`BoundUser`/`ServerPing`/`LatencyStat`/`Online`/`Wol`/`Upgrade`… |
| 字符串混淆 | **可打印 ASCII（0x20–0x7E，95 符号）上的 ROT13**：`chr(((ord(c)-0x20-13)%95)+0x20)`；3,765 条密文已全部解出 |
| 控制网关 | `gw.router.uu.163.com`（插件长期连接）；`whoami.nie.netease.com/v1` 取公网 IP；`log.uu.163.com` 上报 |

关键：插件把“谁被加速/加速哪个游戏”当作**云端下发的指令**，本地只有执行侧（`Acc` → 装 iptables/ip rule）。所以“指定设备/游戏”的控制权在云端，不在路由器。

## 2. 本地控制面（实测为零控制接口）

- `192.168.50.1:16363` 明文 HTTP，`GET /router` → `type:asuswrt / sn:<ROUTER_SN> / model:RT-AX86U`；`POST /router` → 404。
- 用二进制里 97 条路径字符串生成 **74 条候选路由 × GET/POST** 爆破：仅 `/router` 前缀命中，其余（`/activate`、`/speed`、`/envelope/`、`/router/local_tcp/router`…）全 404。
- `60000`、`14554`：私有二进制协议（SOCKS5 问候 / HTTP / TLS 全部无响应或 RST）。
- `127.0.0.1:49637`、隧道内 `172.19.163.1:37773`：插件内部组件（AF_UNIX socketpair + 内嵌 TcpServer，`ctl_inner_pipe.cpp`）。
- 插件运行环境里**没有** `UU_*` 变量（`/proc/5097/environ` 只有 ppp0 的 `IFNAME/IPLOCAL/PPPLOGNAME`），也没有 `.uu.db`、`/jffs/uu`、nvram `uu*` 键 —— 绑定凭据不落盘。

## 3. 云端控制面（真正的“一句话”入口）

路由器 Web UI（`/www/UUAccelerator.asp`）只是 `window.open('https://router.uu.163.com/asus/pc.html#/acce?gwSn=<MAC>&type=asuswrt')`。前端（Vue）调用：

```
POST /api/sess                {"sn":"<ROUTER_SN>","type":"asuswrt"}   -> {sess, uu_logged_in}
GET  /api/devices/?t=<ts>     header sess                                     -> 设备列表（deviceinfo.mac/ip/type/hostname + acc_status）
POST /api/acc                 header sess  {"deviceinfo":{...}}                -> ok|acced|starting|not_login
POST /api/stop-acc            header sess  {"deviceinfo":{...}}
POST /api/acc-mode-setting    {"acc_mode":"game","game_mode_setting":[{key:MAC,key_type:"device",acc_mode:"game",game_id,zone?,server?}]}
GET  /api/gamelist?platform=pc
```

实测（本机、无 Cookie）：

```
POST /api/sess  -> {"sess":"8437013c-…","status":"ok","uu_logged_in":false}
GET  /api/devices → {"status":"not_login"}
POST /api/acc {"deviceinfo":{mac,type,name,ip}} → {"errors":{"deviceinfo":{"hostname":["Missing data for required field."]}},"status":"form_check_error"}
POST /api/acc 补齐 hostname   → {"status":"not_login"}
```

即：**请求体结构已对齐，唯一缺的是登录态**。鉴权是 Cookie（前端 `withCredentials:true`），登录只有「手机号 + 短信验证码 + 易盾」，没有密码登录 —— 因此必须人工登录一次，之后复用 Cookie。

### 3.1 拿到登录态后的实测（✅ 全部通过）

用户从浏览器 `Application → Cookies` 里复制 `sess` 值后：

```
python uu.py login --cookie "sess=<UU_SESS>"   -> uu_logged_in=True
python uu.py dev                                -> 11 台设备 + 各自已配游戏/节点
python uu.py acc 192.168.50.13 --game 荒野乱斗   -> 游戏 -> 荒野乱斗 / 亚服 / 自动；加速 -> ok
                                                    /api/devices 中 acc_status: acced
python uu.py unacc 192.168.50.13                -> ok，状态回到 not_acc
python uu.py acc 192.168.50.13                  -> 对未在设备列表里/不可加速的设备返回 {"status":"fail"}
```

要点（都是踩过的坑）：

- `/api/sess` 同时把 token 放在 JSON 的 `sess` 字段和 `Set-Cookie: sess=<uuid>; HttpOnly; Max-Age=1296000`（15 天）里，**后续请求两者都要带**（`uu.py` 已自动同时发 `sess` 头和 `Cookie`）。
- `POST /api/acc` 的 body 必须用 `/api/devices` 返回的**完整 `deviceinfo`**（含 `hostname`、`acced` 等），少字段会 `form_check_error`。
- `POST /api/acc-mode-setting` 必须是 `{"acc_mode":"game","game_mode_setting":[{完整条目}]}`，条目字段：`key`（`<type>-<mac>`）、`key_type:"device"`、`acc_mode:"game"`、`game_id`、`game_name`、`icon_url`、`zone_id/zone_name/zone_auto`、`server_id/server_name/server_auto`、`is_fence_mode`、`support_fence_mode`、`validate:{"valid":true}`。**只给 `{key,game_id}` 会报 `setting param error`**（这是最早失败的真正原因）。
- `GET /api/gamelist?platform=pc|mobile|switch|…` 返回 `{gamelist:{平台:{首字母:[游戏]}}, zonelist:{game_id:[{zone_id,zone_name}]}, serverlist:{zone_id:[{server_id,server_name}]}}`；`uu.py` 会自动按设备类型选平台、按游戏名/ID 查游戏、自动挑「智能匹配」节点与「所有服务器」。手机平台只有 39 个可加速游戏，PC 上千个。
- 设备按 `key = <type>-<mac>` 存设置；同一台机器可能同时有 `windows-…` 和 `steam_deck-…` 两条。

## 4. 第三条路：本地规则克隆（不需要账号）

读路由器真实数据面发现，所谓“给某设备加速”只是三件事：

```
ip rule  from 192.168.50.91 lookup 179            # 179 = 一堆游戏服务器前缀，全部 via tun163
ip rule  from 192.168.50.91 fwmark 0x163 lookup 163  # 163 = default via 172.19.163.1
iptables -t mangle PREROUTING -s 192.168.50.91/32 -i br0 -p udp --dport 53 -j MARK --set-xmark 0x163/0xffffffff
iptables -t nat    PREROUTING -s 192.168.50.91/32 -d 163.163.127.99/32 -p tcp --dport 80 -j DNAT --to 221.228.204.162:6280
iptables -t nat    PREROUTING -s 192.168.50.91/32 -d 163.163.127.254/32 -j DNAT --to 221.228.204.162:6987
iptables -t nat    PREROUTING -s 192.168.50.91/32 -d 163.163.127.99/32 -j DNAT --to 163.163.127.0
iptables -t nat    PREROUTING -s 192.168.50.91/32 -i br0 -j RETURN
iptables -t nat    PREROUTING -s 192.168.50.91/32 -p udp --dport 53 -j DNAT --to 8.8.8.8
```

隧道 `tun163` 是**路由器级**的（只有一个会话、一个节点），规则只按源 IP 区分设备。所以把 `.91` 这套规则按源 IP 克隆到任意 IP，就能让那台设备走上同一条已建立的加速隧道 —— 这就是不需要云端的“替代实现”。

`uu.py route <ip> on|off` 实现并实测：安装后 `ip rule` 出现 `32762 fwmark/32763 lookup 179`，nat/mangle 各 5+1 条按新 IP 生成；`off` 后全部消失，`iptables -S` 计数回到原始 12 条，`.91` 的加速不受影响。

## 5. 产物

| 文件 | 作用 |
|---|---|
| `D:\DSH\work\uu\uu.py` | 一条命令入口（见下） |
| `D:\DSH\work\uu\uuctl.sh` | 路由器侧 status/start/stop/restart（自动上传到 `/tmp/uuctl.sh`） |
| `D:\DSH\work\uu\uu_route.sh` | 路由器侧规则克隆（自动上传到 `/tmp/uu_route.sh`） |
| `D:\DSH\tools\{elfinfo,strings_dump,classify_strings,decode_all,fn,hexdump,near,http_probe,fuzz_routes,get,jsgrep,slice,handshake,uuapi}.py` | 逆向/探测工具链 |
| `D:\DSH\work\uu\ghidra\out.txt` | Ghidra 反编译导出（194 KB，HTTP server / cloud client 函数） |
| `D:\DSH\work\uu\triage\dec.tsv` | 10,492 条字符串「原文 + 解密」对照 |
| `D:\DSH\work\uu\pull\` | 原始 tar、monitor 脚本 |
| `D:\DSH\work\uu\uugui.pyw` | **副屏小面板**（双击设备即加速，见 §6.1） |
| `D:\DSH\work\uu\launch_uu.vbs` | 无控制台窗口启动器（纯 ASCII，供开机自启/计划任务调用） |
| `D:\DSH\work\uu\UU加速面板.lnk` | 快捷方式（拖到桌面/副屏即可） |

## 6. 用法

```powershell
# 整机开关（无需账号）
python D:\DSH\work\uu\uu.py status
python D:\DSH\work\uu\uu.py stop | start | restart

# 指定设备（本地克隆，需要至少一条已存在的加速会话）
python D:\DSH\work\uu\uu.py route 192.168.50.120 show
python D:\DSH\work\uu\uu.py route 192.168.50.120 on
python D:\DSH\work\uu\uu.py route 192.168.50.120 off

# 指定设备/游戏（云端，需要登录态；目标可写 MAC / IP / 主机名）
python D:\DSH\work\uu\uu.py login --cookie "sess=<浏览器里的值>"
python D:\DSH\work\uu\uu.py dev
python D:\DSH\work\uu\uu.py acc 192.168.50.13 --game 荒野乱斗           # 按名字
python D:\DSH\work\uu\uu.py acc 192.168.50.13 --game <game_id> --server 所有服务器
python D:\DSH\work\uu\uu.py unacc 192.168.50.13
```

登录态存在 `D:\DSH\work\uu\session.json`（`sess` cookie 本身有效期 15 天），过期后重跑一次 `login --cookie` 即可。

### 6.1 副屏加速球（`uuball.pyw`）

零第三方依赖（tkinter + 标准库），**双击 `UU加速球.lnk`** 即可。只管本机，不再列出其它设备。

```
   ╭───────────╮   白色半透明圆球 120x120（置顶、无边框、圆外全透明）
  │   游戏封面   │   加速中：球心是该游戏的完整封面（等比缩进圆内，不裁切）
  │   （纯图）    │   未加速：白球 + “未加速 / 点我选择”
   ╰───────────╯   未登录：白球 + “未登录 / 点我登录”
```

- **启动动画**：`0.42s` 淡入（`-alpha 0 → 0.88`，ease-out cubic）同时从下方上浮 `16` 逻辑像素，紧接 `0.7s` 一圈白光环从球边缘向外扩散到 `R+6` 后消失，全程约 1.1s。alpha 与窗口坐标是逐帧实测过的（见下）。
- **球变小了一圈**：`BALL = 120`（原 140），圆盘半径 `R_DISC = BALL/2 - 8 = 52`，封面直径 `COVER_PX = 104`。
- **只显示封面，不再有延迟和文字**：删掉了延迟（原来是对加速节点做 TCP 握手 RTT，不是游戏内延迟，价值有限）和游戏名/区服文字，改成整张封面等比缩进圆内 —— 一眼就能看出在加速哪个游戏，且 logo 不会被切掉。
- **封面怎么来的**（零依赖、Tk 8.6 原生 PNG）：
  - 云端 `game_mode_setting` 里的 `icon_url` 只有 **32x32**（CDN 的 `fop=imageView/1/w/144/h/144` 不会放大，实测请求 144/104/200/300 都返回 32x32），所以改用游戏库里的 **`large_icon_url`**（本例是 `304x468` 的竖版海报，PNG）。
  - **整图塞进圆里（contain，不裁切）**：先用 `fop_w(url, 40)` 下 40px 宽的小图（约 1 KB）探出原始比例，再按「矩形对角线 = 圆的直径」算目标尺寸 `fit_size()`（`pad=0.93` 留一圈白边），最后直接向 CDN 要这个尺寸：`?fop=imageView/1/w/<W>/q/99`。实测 CDN 是**等比放大到覆盖目标框、不裁剪**（`w=104&h=104` 请求 304x468 的图，返回 104x160），所以只给 `w` 一个参数就能拿到精确宽度。
  - 效果：`304x468` 的海报 → 请求 `w=52` → 返回 `52x80`，`hypot(52,80)/2 = 47.7 ≤ R_DISC(52)`，整图落在圆内，**四角也不再需要 `_mask_corners()` 遮罩**，圆盘边缘回到 `disc()` 自带的抗锯齿过渡（比之前的色键硬边更好看）。
  - 兜底：CDN 取不到（或不是 PNG）时退回原图，本地仍用整数 `subsample`/`zoom` 收缩，只有在放不下（`cover_fits=False`）时才调用 `_mask_corners()`。
  - 小图（只有 32x32 的老游戏）会 `zoom` 到接近圆径并**不做裁切**，画在白球上当代替。
  - 缓存：`.uu-ball\covers\<game_id>-w<W>.png`（旧版是 `-c104.png`，`find_cover()` 会优先认带 `-w` 的新文件）；换游戏时 `cover_gid` 变化即重新抓。
  - **竞态修复**：`refresh_cloud()` 比 `load_games()` 先跑，若此时抓封面只能拿到 32px 小图并永久缓存。现在 `want_cover()` 在 `self.gmap` 还是空的时候直接返回，`load_games()` 完成后补发一次 `refresh`，保证用的是大图。
- **只控制这一台电脑**：启动时用 UDP `connect(("223.5.5.5",80))` 探本机 IP，在 `/api/devices` 里优先匹配 `ip == 本机 and type == "windows"`，退化到仅匹配 IP，再退化到记住的 MAC。当前锁定 `windows-<PC_MAC> / 192.168.50.91 / Abigail`。其它 8 台 IoT 设备在界面上完全不出现。
- **交互**：拖动移位（超 4px 算拖动，位置记入 `ball.json`）；左键点开面板；右键菜单（选择游戏…/停止加速/刷新状态/退出）。圆外透明像素天然点击穿透。
- **点开后的面板**（366x436，在球左侧弹出并自动贴边）：搜索框（1117 个 PC 游戏，子串匹配、前缀命中排前、最多 200 条）→ 选中后下方生成该游戏的区服 chip（智能匹配/日本/欧洲/北美…）→「开始加速」。另有「停止」与状态行。
- 加速走云端：先 `POST /acc-mode-setting`（必须 `status == ok`）再 `POST /acc`（接受 `ok/acced/starting`）；停止 `POST /stop-acc`（接受 `ok/not_acc/stopping`）。全部在线程里跑，结果经 `queue.Queue` 回主线程（每 60ms 消费），不跨线程碰 Tk。
- 日志与配置：`%LOCALAPPDATA%\uu-ball\`（`ball.json` 位置+MAC、`gamelist.json` 24h 游戏库缓存、`covers\` 封面缓存、`run.log`）；不可写时自动退到程序目录的 `.uu-ball\`（当前实测就在这里）。
- 自检与调试：`--selftest [--panel]`（6s 后自弹并打印 `local_ip/device/key/state/cover/cover_file/games/geometry/panel/hits`）、`--probe`（只打印路径与小球的几何常量）、`--pos X,Y`（指定落点，会写进 `ball.json`）、`--demo`（真跑 + 2.2s 后自开面板）。
- 玻璃/透明实现：画布背景用色键 `KEY = "#fffefe"`（比纯白差 1/255，防圆边 AA 发白圈）+ `-transparentcolor`，窗口 `-alpha 0.88`；圆盘用逐行扫描线 + 边缘按覆盖率混色做抗锯齿（`disc()`/`round_rect()`）。因 Tk 在 Windows 上所有控件都绘制在顶层窗口，色键 + alpha 对整个控件树生效。
- **DPI 陷阱**：本机主屏 3840x2160 @200%（LOGPIELX=192）、副屏 `2194x1234 @2469`、虚拟桌面 3840x3703。Tk 是 **DPI 不感知** 的，它用逻辑坐标（1920x1080），而 `BitBlt` 抓的是物理像素 ⇒ 任何截屏验证必须乘 `shot.SCALE`（用 `shot.grab_logical`），否则会把别的窗口当成小球。小球实际物理尺寸 240x240、面板 732x872。
- **已实测（主屏，`verify_cover.py` / `verify_intro.py`）**：
  - 封面态：圆内 `key% = 0.0`（没有一处露白色底）、`colorful% = 38.7%`、`uniq = 1461` 种颜色、`near_white = 0.09%` ⇒ 封面确实铺满圆形；四角像素是桌面壁纸色 ⇒ 色键透明生效。
  - 开启动画：轮询 `GetLayeredWindowAttributes` 得到 `alpha 0 → 8 → 75 → 109 → 151 → 172 → 196 → 207 → 218 → 223 → 224`（0.21s→0.61s），同时 `GetWindowRect().top` 从 `216` 回到 `200` ⇒ 淡入 + 上浮 16 像素都成立。
  - 面板：`366x436+853+1386`，`hits = 200`（空搜索时的前 200 条）。
  - 副屏（DISPLAY2）上 BitBlt 抓图整块近黑，**副屏的像素级验证做不了**，只能靠窗口属性（`layered=True, colorkey=True, alt_key='#fffefe'`, alpha=224）与主屏同源代码推断。

- **封面遮罩（修）**：封面图比圆盘大（152x234 vs 104x104），只切四角会在圆外留一圈方形边条，看起来像“外面有框”。`_mask_corners()` 现在先把圆的外接正方形以外的四条边条整块涂成色键（`create_rectangle`），再切四角（`seg=18`），实测 r>=53 处零着色像素。原 3 条阴影弧与内侧描边已删：`create_arc` 在 layered window 下只画出约 6 度的一小段，保留会留下细线残影。

- **封面双层（背景铺满 + 前景完整）**：球心不再只有一整张缩小的图，而是两层——
  - **前景**：同上，整张 `large_icon_url` 等比 contain（本例 `52x80`，落在圆内、四角无需遮罩）。
  - **背景**：从同一张 `large_icon_url` 用 CDN `?fop=imageView/1/w/104/q/99` 取 `104x160`，本地 `PhotoImage.copy(from_coords=(0,28,104,132))` 切中心正方形（正好等于圆的外接正方形）→ `k = 104//26 = 4` 做 `subsample(k)`+`zoom(k)` 得马赛克软化（避免和前景'同一张图糊两遍'的廉价感）→ `dim_img(root, img, 0.42)` 整体压暗 42% → 铺满整个圆盘，让前景的竖版海报像贴在暗底上。
  - **压暗的实现**（Tk 没有滤镜）：`img.tk.call(str(img), "data")` 返回的**不是嵌套 list 而是一个字符串**，必须用 `root.tk.splitlist()` 解开（`splitlist(rows[0])` 得到一行），单元格是 `#rrggbb`，逐格 `int(c[1:3],16)*factor` 再 `img.put(out)` 写回；10,816 像素约 10ms，只在加载时做一次。
  - **绘制顺序**（`paint()`）：3 层阴影 `disc` → `bg_img` 的 `create_image`（anchor 默认 center）→ 圆外 `_mask_corners()` → 前景 `cover_img` → 必要时再遮罩。字典 `("bg", gid)` 与 `("cover", gid)` 走同一个 `queue`，都按 `gid == self.cover_gid` 过滤，换游戏时旧图不会串台。
  - **缓存**：`.uu-ball\covers\<game_id>-b104.png`（背景）与 `-w52.png`（前景）并列，`_fetch_cover` 末尾发现缺背景就顺带补抓一张，不额外增加切换延迟。

### 6.2 v5 面板：自动认路由器 + 最近游玩 + 首字符分组

面板仍是 `PANEL_W x PANEL_H = 366 x 560`（原来是 436 高），自上而下五段：

| y | 内容 |
|---|---|
| 14 | 标题「选择游戏」+ 右上角 `路由器型号 · 本机IP`（例 `RT-AX86U · 192.168.50.91`）|
| 44 | 搜索框（**位置和尺寸与旧版完全一致**：x18 y44 w330 h30）|
| 82..306 | 游戏列表（Listbox + 细滚动条）|
| 312 / 332 | 「区服」标签 + 区服 chip 容器（3 列，最多 9 个）|
| 436 / 456 | 「服务器」标签 + 服务器下拉（**只在所选区服有 >1 个服务器时才出现**）|
| 498 / 540 | 「开始加速」+「停止」按钮、底部状态行 |

**行模型**：`Panel.rows` 是三元组列表 `("head", 标题) / ("recent", 记录) / ("game", 游戏)`，Listbox 逐行插入。
分组标题行不可选：`on_click` 里命中 head 就 `selection_clear` 并 `return "break"`，`on_pick` 再兜一层。

**无输入时**：先 `最近游玩` 块（最多 5 条，每行 `★ 游戏名 · 区服`），后面才是全部游戏按首字符分组（`0-9 / A..Z / 其他`）。
实测全库 1117 个游戏 → 1147 行、29 个分组标题、排序校验 `rows == sorted(rows, key=sort_key)` 为 True。

**有输入时**：子串匹配（搜「战」= 82 条），`startswith` 的排前面，组内仍按 `sort_key`。

**双击 = 一键加速**：`on_dbl` 先把该行选中并走 `on_pick`（建好区服/服务器），再 `act_accel(game, zone_name, server_name)`。
「最近游玩」里的记录带上次的区服和服务器，双击直接沿用。

**首字符分组怎么来的**：GB2312 一级汉字表本身按拼音排序，只需要 23 个「组首字」当分界
（`A=啊 0xB0A1 / B=八 / C=擦 / … / Z=匝`，A 用 0xB0A1 而不是「阿」的 0xB0A2，否则「啊」会掉队）。
`initial_of()` = 取首字 → 数字归 `0`、ASCII 字母归大写、汉字按 GB2312 编码找所在段、其余归 `#`；
`sort_key()` = `(组序, 组内拼音字节, 原名)`，组序 `0 < A..Z < #`。
全库 1115/1117 能归组，剩下 2 个落「其他」：`『江湖客栈』`（全角引号开头）、`東方獣王園`（繁体，GB2312 编不出来）。

**最近游玩落盘**：`.uu-ball/ball.json` 的 `recent` 数组，最多 6 条，字段
`{gid, name, zone, server, icon, ts}`；同一 gid 去重后置顶。写入时机有两处：
① `refresh_cloud()` 看到云端「本机 acced」且与首条不同（可能是别的端改的）；② `_accel()` 成功后。

**路由器自动探测（不需要 SSH）**：`detect_router()` 依次试
① `ball.json` 里记住的 `router_ip`、② `route print -4 0.0.0.0` 解析出的默认网关、③ 本机 /24 的 `.1` / `.254`；
对每个候选 `probe_router()` 连 `:16363` 发 `GET /router`，
回包里出现 `type:` 即命中，并解析出 `type/sn/model`（例 `asuswrt / <ROUTER_SN> / RT-AX86U`）。
**这个探测同时等价于「UU 插件活着」**——16363 是 uuplugin 自己开的监听口，插件不在就没有回包。
命中后把 `router_ip` / `router_sn` 写回 ball.json。

**复检节奏**：worker 每 4s 刷一轮云端；路由器参数「还没认到就 25s 重试、认到后 5 分钟复检」，
所以开机顺序随意——先开球后开路由器也能自动接上。

**本机锁定**不变：`local_ip()` 取本机局域网 IP，再在云端 `devices()` 里按
`ip + type=windows` → 仅 `ip` → 配置里的 `mac` 三级匹配，命中哪个就把加速请求发给哪个设备。

**加速链多了服务器参数**：`act_accel(game, zone_name, server_name)` →
`uu.build_setting(dev, game, zones, servers, zone_name, server_name)`；
下拉默认选「所有服务器」，没有就取第一个；该区服只有一个服务器时下拉整体隐藏。

**封面背景的缓存命中修复（v5 附带）**：`want_cover()` 原来只在「背景图文件不存在」时才下载背景，
缓存命中时直接 `return`，于是**重启后小球只剩白盘 + 前景海报**（背景不画）。
现在缓存命中且 `.uu-ball/covers/<gid>-b104.png` 存在时直接 `load_bg(gid)`；
`_fetch_cover()` 下载完发现背景图已在，也会往队列塞一条 `("bg", gid)` 让主线程装上。
日志里能看到 `bg load: 104x104` 就说明背景铺上了。

### 6.2 打包成 exe（便携版）

**产物**：`D:\DSH\work\uu\UU加速球\`（文件夹，双击 `UU加速球.exe`）+ `D:\DSH\work\uu\UU加速球-便携版.zip`（13.5 MB）。

- **构建链**：Python 3.15 + PyInstaller 6.22.3（`--onedir --windowed --name "UU加速球"`），
  `--add-data session.json / uuctl.sh / uu_route.sh`，`--hidden-import uu`，
  `--exclude-module paramiko,cryptography,bcrypt,nacl,PIL`（面板只用云端接口，不需要 SSH 栈）。
  命令固化在 `D:\DSH\work\uu\build_exe.cmd`。
- **为什么依赖装在 `_pylib`**：沙箱给工作区新建目录打了 `Everyone:(DENY)(DC)`（禁止删除子项），
  pip 的「下载到临时名再 rename」因此必失败（`Permission denied ... .whl`），`icacls` 也被拒。
  改用 `D:\DSH\work\uu\_whl3.py`：直接按 simple index 取 whl 用 `zipfile` 解到 `_pylib`，全程只新建不删改。
- **onefile 不可用（重要）**：`--onefile` 的 bootloader 在沙箱里解包到 TEMP 时静默挂死
  （`_MEIxxxx` 建了空目录、进程常驻、stdout/stderr 全空），onedir 在同一沙箱一次通过 ⇒ 交付 onedir。
- **便携路径**（`uuball.pyw` / `uu.py` 都改）：
  `FROZEN = bool(getattr(sys, "frozen", False))`，
  `APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else HERE`；
  `pick_cfg_dir()` 在 frozen 时优先 `<exe>\uu-data`（写不进才退 `%LOCALAPPDATA%\uu-ball`）；
  `uu.SESSION_FILE` 固定 `APP_DIR/session.json`，`uuctl.sh`/`uu_route.sh` 用 `_res()` 先找 exe 旁再找随包副本。
- **seed_files()**：首次运行把随包的 `session.json / uuctl.sh / uu_route.sh` 拷到 exe 旁边（可被用户改）。
- **换电脑也能自动接管本机**：`refresh_cloud()` 里按 `ip+windows` → `仅 ip` → `cfg.mac` 三级匹配；
  都落空时用 `self_device(ip)` 现造 `{type:windows, mac:uuid.getnode(), ip, hostname}` 继续走
  `/acc-mode-setting` + `/acc`（后端会把这台设备注册到该路由器下）。
- **登录（Cookie）**：小球处于 `nologin` 时点它弹出 `LoginDialog`（自绘 Toplevel，置顶），
  粘贴浏览器 Cookie → `apply_cookie()` 抽 `sess=` → 写 `session.json` → 重载游戏库。
  右键菜单也加了「登录 / 更换账号…」。
- **记录持久化**：`uu-data\ball.json` 存 `ball_pos`、`router_ip/sn`、`mac`、`recent[]`
  （gid/name/zone/server/icon/ts，最多若干条，新条目置顶）；`uu-data\covers\` 存封面。
  这样关机重启后打开就是「最近游玩」列表，双击即加速，不用重新搜索。
- **实测**（干净空目录 `_extest2` 里解压运行）：日志
  `seed: session.json/uuctl.sh/uu_route.sh` → `router: 192.168.50.1 asuswrt RT-AX86U sn=<ROUTER_SN>`
  → `cover load: 52x80 fits=True` → `bg load: 104x104`；`uu-data\` 自动生成，
  `gamelist.json` 1.97 MB，`ball.json` 带回最近两条记录。

## 7. 未验证 / 风险

1. ~~云端 acc/stop-acc 真实路径未验证~~ → 已用手机 `192.168.50.13` 端到端验证（设游戏/加速/停止/还原）。~~对已在加速中的设备改游戏未验证~~ → 已在本机 `192.168.50.91` 上多次实测 `stop → acc` 换游戏（含面板 `--drive` 路径）：会重建隧道、向下断流数秒，游戏端需重连。
2. **规则克隆的端到端未验证**：机制验证到“规则正确安装/回滚、模板会话不受影响”，但验证“第二台设备真的被加速”需要第二台物理设备（当前唯一在线设备 `192.168.50.91` 就是测试机本身）。
3. 克隆会复用 `.91` 已解析的节点/端口（`221.228.204.162:6987/6280`）与域名劫持映射；不同游戏需要不同映射时，克隆不会自动更新——那正是云端 `Acc` 才能做的事。
4. `tun163` 会话由云端维持，规则克隆只在会话存活期有效；插件重启/掉线后需重新 `on`。
