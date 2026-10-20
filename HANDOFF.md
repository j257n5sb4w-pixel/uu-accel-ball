# 接管网易UU加速器（ASUS RT-AX86U）— Agent 交接包

> 这份文档写给**另一个 AI agent**。读完应该能独立接管「给某台设备/某个游戏开加速」。
> 生成日期：2026-10；载荷 `uuplugin v14.10.6`；路由器固件 `3.0.0.4.388_24436`。

---

## 1. 你的任务

用命令行（不是浏览器）控制这台路由器上的网易UU加速器：

- 查：当前哪些设备在加速、加速的是哪个游戏/节点
- 开：给指定设备（MAC / IP / 主机名）开加速，可指定游戏、节点、服务器
- 关：停掉指定设备的加速
- 兜底：整机 start/stop/restart，或把已加速设备的策略规则克隆到另一个 IP

**不要重新逆向**，结论已经在这份包和 `REPORT.md` 里：路由器本地**没有**「给某设备加速」的接口，唯一可行入口是网易云端的 Web API（`https://router.uu.163.com/api`），登录态用一个 `sess` cookie 表示。包里已经带了有效登录态。

## 2. 环境要求

| 项 | 要求 |
|---|---|
| Python | 3.9+；`paramiko` **只有** SSH 相关命令需要（`status/start/stop/route`），云端命令不需要 |
| 网络 | 云端命令（`dev/acc/unacc/games`）只需能出网访问 `https://router.uu.163.com`，**不需要在你的局域网里**；SSH 命令才需要能访问 `192.168.50.1:22` |
| 平台 | Windows / Linux / macOS 都行，脚本是纯 Python 标准库（+ 可选 paramiko） |
| 其它 | 不需要浏览器、不需要 UU 客户端 |

> 也就是说：如果交给一个**云端 agent**（不在你家局域网），它依然能用 `dev / acc / unacc / games` 接管「设备+游戏」加速，只是用不了整机 `status/start/stop` 和本地规则克隆 `route`。

## 3. 凭据与固定参数

```
路由器 SSH : 192.168.50.1:22  账号 <ROUTER_USER>  密码 <ROUTER_PASSWORD>
路由器型号 : ASUS RT-AX86U (asuswrt)
UU 设备 SN : <ROUTER_SN>        # 路由器 label MAC，云端用它定位这台路由器
云端 API   : https://router.uu.163.com/api
登录态文件 : session.json              # {"cookie": "sess=<uuid>", "sn": "...", "sess": "..."}
```

`session.json` 里的 `sess` 是 HttpOnly cookie，有效期 **15 天**（`Max-Age=1296000`）。过期后只能请**用户本人**在浏览器登录一次，从 `Application → Cookies → https://router.uu.163.com → sess` 复制值，然后：

```
python uu.py login --cookie "sess=<值>"
```

## 4. 立刻可用的命令

所有命令都在本包目录下执行（Windows 用 `python`，Linux 用 `python3`）。

```bash
python uu.py dev                              # 设备表：加速状态 / IP / 主机名 / MAC / 类型 / 游戏 / 节点
python uu.py dev --json                       # 同上，原始 JSON

python uu.py acc 192.168.50.13                # 按当前设置加速这台设备
python uu.py acc 192.168.50.13 --game 荒野乱斗  # 指定游戏（自动挑「智能匹配」节点 + 「所有服务器」）
python uu.py acc ca:e0:14:41:af:62            # 也可以按 MAC
python uu.py acc moto-X70-Air                 # 也可以按主机名（唯一匹配时）
python uu.py acc 192.168.50.13 --game 荒野乱斗 --zone 亚服 --server 所有服务器

python uu.py unacc 192.168.50.13              # 停止该设备加速

python uu.py games mobile                     # 列出该平台可加速游戏（game_id + 名字）
python uu.py games pc

python uu.py status                           # 路由器侧：插件进程 / 隧道 / 当前被加速的 IP / 流量
python uu.py start | stop | restart           # 整机级（影响所有设备，慎用）
python uu.py route 192.168.50.120 on|off|show # 无账号兜底：克隆策略规则到另一个 IP
```

`dev` 输出示例：

```
acced     192.168.50.91   Abigail        <PC_MAC> windows  战地风云 1 / 亚洲
not_acc   192.168.50.13   moto-X70-Air   ca:e0:14:41:af:62 android  Steam / 中国大陆
```

`acc` 输出示例：

```
游戏 -> 荒野乱斗 / 亚服 / 自动
加速 192.168.50.13 (moto-X70-Air) -> ok
```

## 4.1 加速球 GUI（Windows，双击即用）

`uuball.pyw`（零依赖，tkinter）。双击 `UU加速球.lnk`，或 `pythonw uuball.pyw`。

- **形态**：120x120 白色半透明圆球，置顶、无边框、圆外透明（色键 `#fffefe` + `-alpha 0.88`）。加速中球心是**该游戏的完整封面**（等比缩进圆内，不裁切，logo 不会被切边），没有任何文字；未加速是白球 + “未加速 / 点我选择”；未登录是“未登录 / 点我登录”。
- **双层封面**（v3）：加速中圆盘不是一整张缩小的图，而是「背景铺满 + 前景完整」——背景取同一张海报的 `104x160`，本地 `copy(from_coords=(0,28,104,132))` 切中心正方形铺满圆，`subsample(4)+zoom(4)` 做马赛克软化、`dim_img(..., 0.42)` 压暗 42%；前景仍是 contain 后的 `52x80` 完整封面叠在中间。两层都按 `gid` 过滤，换游戏不会串图。缓存 `covers/<gid>-b104.png` 与 `-w<W>.png`。
- **启动动画**：0.42s 淡入（alpha 0→0.88，ease-out）+ 向上浮 16 逻辑像素，接 0.7s 一圈白光环从球边缘扩散到 R+6 后消失。
- **封面来源**：游戏库里的 `large_icon_url`（PNG 海报，如 304x468）；云端 `icon_url` 只有 32x32 且 CDN 的 `fop=imageView/1/w/N` 只缩不放，所以不用它。
- **整图放进圆里**：先 `fop_w(url, 40)` 下 40px 宽的小图探比例（~1 KB），按「对角线 = 圆直径」算目标尺寸 `fit_size()`（`pad=0.93`），再直接向 CDN 要这个尺寸（`?fop=imageView/1/w/<W>/q/99`）。实测 CDN 是等比放大到覆盖目标框、不裁剪（`w=104&h=104` 请求 304x468 返回 104x160），只给 `w` 就行。结果如 `52x80`，`hypot(52,80)/2 = 47.7 ≤ 52`，整图落在圆内，**不需要遮罩**，圆盘边缘是 `disc()` 的 AA 过渡。CDN 失败才退回原图 + 整数 `subsample`，仍放不下时才用 `_mask_corners()`。缓存 `covers/<game_id>-w<W>.png`（`find_cover()` 优先认 `-w`）。
- **只管本机**：自动探本机 IP，在 `/api/devices` 里锁定 `type=windows` 的那一台（当前 `192.168.50.91 / <PC_MAC>`），不再列出其它设备。
- **交互**：拖动移位（记住位置）；左键弹面板「搜索游戏 → 选区服 → 开始加速」（366x436，自动贴球左侧）；右键菜单（选择游戏/停止加速/刷新状态/退出）。
- **不再有延迟**：旧版那个数字是“到 UU 加速节点的 TCP 握手 RTT”（云端 `/status` 根本没有延迟字段，前端也不显示），不是游戏内延迟，已按需求移除。
- **配置/日志**：`%LOCALAPPDATA%\uu-ball`（`ball.json` / `gamelist.json` / `covers` / `run.log`），不可写时退到 `.uu-ball`。
- **自检**：`python uuball.pyw --selftest --panel`（打印 state/cover/games/geometry/panel/hits）、`--probe`、`--pos X,Y`、`--demo`。
- **DPI 坑**：Tk 不感知 DPI（逻辑坐标 1920x1080），本机 200% 扩展；截屏验证必须乘倍率（见 `REPORT.md` §6.1），否则会误判成“不透明白方块”。副屏 BitBlt 抓图整块黑，副屏无法做像素验证。

**v5 面板（自动探路由器 / 最近游玩 / 首字符分组）**

- 尺寸 `366 x 560`；搜索框位置没动（x18 y44 w330 h30），点球弹出的第一屏就是：
  `最近游玩`（最多 5 条，带上次区服/服务器，**双击即加速**）→ 按首字符分组的全部游戏（`0-9 / A..Z / 其他`）。
- 有输入时列表切成搜索结果（前缀命中优先），**搜索框下面那块「最近游玩」随之隐藏**，符合「想玩别的再去搜」。
- 分组标题行不可选（点它不会当成游戏选中）。
- 首字符 = GB2312 一级汉字表的分段首字，纯 Python 无第三方依赖；
  `initial_of()` / `sort_key()` 是模块级函数，直接可复用/可测。
- 区服 chip 选中后，若该区服有多个服务器，`服务器` 下拉才出现（例 `5E对战平台 / 智能匹配` → 杭州/北京/深圳/所有服务器）。
- 路由器自动探测：`detect_router()` = ball.json 里的 `router_ip` → `route print -4 0.0.0.0` 的默认网关 → 本机 /24 的 `.1`/`.254`，
  对每个候选 `probe_router()` 连 `:16363` 发 `GET /router`，回包含 `type:` 即命中（等于证明 uuplugin 活着）。
  没认到 25s 重试，认到后 5 分钟复检；命中后写回 `router_ip`/`router_sn`。
- 面板标题显示 `路由器型号 · 本机IP`（`RT-AX86U · 192.168.50.91`），没认到时是 `未连路由器`。
- `recent` 存在 `.uu-ball/ball.json`，最多 6 条，`{gid,name,zone,server,icon,ts}`，同 gid 去重置顶。
- 自检：`python uuball.pyw --selftest` 会多打印 `router = {...}` 和 `recent = [...]` 两行。

## 5. 当前状态（生成快照时）

| 设备 | IP | MAC | 类型 | 状态 | 已配游戏/节点 |
|---|---|---|---|---|---|
| Abigail（用户 PC） | 192.168.50.91 | <PC_MAC> | windows | **acced** | 空战奇兵8 希孚之翼 / 日本 |
| moto-X70-Air | 192.168.50.13 | ca:e0:14:41:af:62 | android | not_acc | Steam / 中国大陆 |
| 其余 9 台（手机/电视/扫地机/灯/摄像头…） | — | — | apple/android | not_acc | 未配置 |

路由器侧：`uuplugin` pid 在跑，`tun163` UP，加速规则指向 `.91`。
完整机器可读快照见 `state.json`（含 `devices`、`settings`、`cloud_status`、本地 `status` 输出）。

## 6. 云端 API 契约（脚本已封装，改脚本时看这里）

所有请求：

```
POST/GET https://router.uu.163.com/api/...
Headers:
  Content-Type: application/json      (有 body 时)
  User-Agent:  任意现代浏览器 UA
  Origin:      https://router.uu.163.com
  Referer:     https://router.uu.163.com/asus/pc.html
  Client-Origin: router.asus.com
  sess:        <sess uuid>            # 每个业务接口都要
  Cookie:      sess=<sess uuid>; <用户浏览器 cookie 里的其它键>   # 必须同时发
```

| 接口 | 方法 | 说明 |
|---|---|---|
| `/sess` | POST | body `{"sn":"<ROUTER_SN>","type":"asuswrt"}` → `{"sess":"<uuid>","status":"ok","uu_logged_in":true/false}`，**同时 Set-Cookie** |
| `/status` | GET | 路由器状态：`online`、`acc_mode`、`acc_area`、`acc_platforms`、`game_mode_setting.device_setting` |
| `/devices/?t=<ts>` | GET | `{"devices":[{acc_status,acc_period,deviceinfo:{mac,ip,type,hostname,acced},name,logo}]}` |
| `/acc` | POST | body `{"deviceinfo": <devices 里的完整 deviceinfo>}` → `{"status":"ok"}` |
| `/stop-acc` | POST | 同上 body → `{"status":"ok"}` |
| `/acc-mode-setting` | POST | body `{"acc_mode":"game","game_mode_setting":[<完整条目>]}` → `{"status":"ok"}` |
| `/gamelist?platform=pc\|mobile\|switch\|ps5\|…` | GET | `{"gamelist":{平台:{首字母:[游戏]}},"zonelist":{game_id:[{zone_id,zone_name}]},"serverlist":{zone_id:[{server_id,server_name}]}}` |

`acc-mode-setting` 的**完整条目**（缺字段就 `setting param error`）：

```json
{
  "key": "windows-<PC_MAC>",   // 必须是 <deviceinfo.type>-<deviceinfo.mac>
  "key_type": "device",
  "acc_mode": "game",
  "game_id": "63590157d925c8c72419354d",
  "game_name": "战地风云 1",
  "icon_url": "https://...(游戏 icon)",
  "zone_id": "5809c4a8e3a8b26096b0ef50", "zone_name": "亚洲", "zone_auto": false,
  "server_id": "65573a92b211a3f4bbfede0f", "server_name": "亚洲全区匹配", "server_auto": false,
  "is_fence_mode": false, "support_fence_mode": 0,
  "validate": {"valid": true}
}
```

`uu.py` 的 `build_setting()` 就是干这个的：按设备类型选平台 → 按游戏名/ID 找游戏 → 从 `zonelist` 挑「智能匹配」（没有就第一个）→ 从 `serverlist` 挑「所有服务器」（没有就第一个）。找不到就给空 `zone_id/server_id` 且 `zone_auto/server_auto = true`。

常见返回：

| 返回 | 含义 | 处理 |
|---|---|---|
| `{"status":"ok"}` | 成功（`/acc` 也可能返回 `acced`/`starting`） | 2–6 秒后 `dev` 复核 `acc_status` |
| `{"status":"not_login"}` | 登录态丢了 | 让用户重新给 `sess` cookie |
| `{"status":"fail"}` | 设备不可加速（不在路由器设备列表 / 非游戏设备 / 离线） | 换设备，别重试 |
| `{"status":"form_check_error","errors":{...}}` | body 结构不对 | 对照上面契约补字段 |
| `{"message":"setting param error","status":"fail"}` | `acc-mode-setting` 条目不全 | 用 `build_setting()` 生成，别手搓 |

## 7. 路由器本地有什么（不要浪费时间再找）

- `192.168.50.1:16363` 明文 HTTP，**只有一个路由**：`GET /router` → `type:asuswrt / sn:<mac> / model:RT-AX86U`；`POST` 和其余路径全 404。用二进制里 97 条路径字符串爆破过 74 条候选，无第二入口。
- `60000`、`14554`：私有二进制协议（HTTP/SOCKS5/TLS 问候都无响应或 RST）。`/jffs/uu.tar.gz` 里的插件是静态 ARM 二进制，字符串是「可打印 ASCII 上的 ROT13」混淆。
- `127.0.0.1:49637`、`172.19.163.1:37773`：插件内部组件（AF_UNIX socketpair + 内嵌 TcpServer）。
- 插件运行环境没有 `UU_*` 变量、没有 `.uu.db`、没有 nvram `uu*` 键 —— 绑定凭据不落盘，控制权在云端。

## 8. 兜底：数据面克隆（不需要账号）

隧道 `tun163` 是**路由器级单会话**，规则只按源 IP 区分设备。所以可以把一个正在加速的设备的规则按源 IP 克隆给任意 IP：

```bash
python uu.py route 192.168.50.120 show
python uu.py route 192.168.50.120 on      # 默认模板 192.168.50.91
python uu.py route 192.168.50.120 off
```

改的是：2 条 `ip rule`（table 179 游戏前缀 + fwmark 0x163）、mangle 的 DNS MARK、nat 的 5 条 DNAT。

限制：复用模板设备已解析的节点/端口与域名劫持映射；不同游戏需要不同映射时克隆不会更新（那正是云端 `Acc` 才能做的）；`tun163` 会话掉线后要重新 `on`。

## 9. 踩过的坑（照做能省几小时）

1. **别用 `sh`**：路由器 `PATH` 里 `/usr/sbin` 在前，`sh` 是 Broadcom 内存调试工具（`sw/sh/sb`），会打印 `Error: Invalid switch`。脚本一律 `/bin/sh`。
2. **别用 `cat >` 传文件**：会命中调试版 `cat`。用 `dd of=/tmp/x.sh 2>/dev/null` 再 `chmod 755`，`uu.py` 里已实现（`ensure_file()` 按字节数比对，避免跑旧脚本）。
3. **没有 SFTP**：路由器 dropbear 没开 sftp 子系统，取文件用 `cat` 走 exec。
4. **paramiko 默认 30 秒超时**：别在远端 `sleep 70`，本地 `Start-Sleep`。
5. **`sess` 既是 JSON 字段又是 HttpOnly cookie**：只发 header 不发 cookie，部分接口会静默降级；`uu.py` 两个都发。
6. **`/acc` 的 body 要 `/devices` 返回的完整 `deviceinfo`**（含 `hostname`、`acced`），手搓 `{mac,ip}` 会 `form_check_error`。
7. **设备设置按 `<type>-<mac>` 存**，同一台机器可能同时有 `windows-…` 和 `steam_deck-…` 两条，别混。
8. **手机平台只有 39 个可加速游戏**（PC 上千），找不到游戏不是接口错，是列表里没有。
9. **改游戏会重启该设备的加速**（短暂中断几秒）；对正在游戏的用户要先问。
10. **非 ASCII**：`--game 荒野乱斗` 在正常终端可用；如果 shell 传参编码有问题，改用 `game_id`。

## 10. 安全红线

- **不要动用户正在加速的设备**（当前是 `192.168.50.91`）除非用户明确要求；测试请挑 `not_acc` 的设备，测完**还原它原来的游戏设置**（先存 `orig`，测完 `acc-mode-setting` 发回去）。
- 不要 `stop` 整机/杀插件，除非用户要求 —— 会让所有设备掉加速。
- 不要往 `/jffs` 写持久化，除非用户要求。
- `session.json` 里的 cookie 是用户账号凭据，**不要外发**（贴日志/发到外部服务前先打码）。
- 云端有账号级限流/风控：不要循环刷 `acc/stop-acc`，两次操作间隔 ≥ 2 秒。

## 11. 验证清单（接手后先跑一遍）

1. `python uu.py dev` → 打印 11 台设备，`.91` 是 `acced`，说明登录态 + 网络 + 脚本都 OK。
2. `python uu.py status` → 插件 pid、`tun163 UP`、`ip rule` 里有 `.91`，说明 SSH 侧也 OK。
3. 挑一台 `not_acc` 设备：`python uu.py acc <ip>` → 2–6 秒后再 `dev`，状态变 `acced` → `python uu.py unacc <ip>` → 回到 `not_acc`。（这一步会有真实的几秒加速，请先跟用户确认设备。）

## 12. 包内文件

| 文件 | 字节 |
|---|---|
| `AGENT_TASK.md` | 1,433 |
| `HANDOFF.md` | 17,263 |
| `REPORT.md` | 24,141 |
| `UU加速球.lnk` | 1,507 |
| `session.json` | 139 |
| `state.json` | 14,186 |
| `uu.py` | 17,562 |
| `uu_route.sh` | 2,730 |
| `uu_snapshot.py` | 1,677 |
| `uuball.pyw` | 61,391 |
| `uuctl.sh` | 2,934 |

## 13. 已知未验证 / 风险

- ~~「给**已在加速中**的设备换游戏」未在用户设备上实测~~ → 已在本机 `192.168.50.91` 上实测多次（含面板 `--drive`）：会重建隧道、断流数秒，游戏需重连。
- 「规则克隆后另一台设备真的被加速」只验证到规则安装/回滚正确，缺第二台物理设备做流量验证。
- 云端接口是网易内部 Web API，无公开文档、可能随时改；返回结构变化时以 `state.json` 里的样本为准。

## 13. 打包成 exe（便携版，2026-10-20）

- 构建脚本：`build_exe.cmd`（PyInstaller 6.22.3，`--onedir --windowed`，依赖在 `_pylib`，
  由 `_whl3.py` 从镜像直接解 whl —— 沙箱里 pip 会因 `DENY(DC)` 失败）。
- 产物：`D:\DSH\work\uu\UU加速球\`（exe + `_internal\` + `使用说明.txt`）与
  `D:\DSH\work\uu\UU加速球-便携版.zip`。onefile 在沙箱内解包挂死，故用 onedir。
- 便携化：`APP_DIR` = exe 目录；配置/记录在 `<exe>\uu-data`（`ball.json`、`covers\`、`gamelist.json`）；
  `session.json`、`uuctl.sh`、`uu_route.sh` 首次运行由 `seed_files()` 落到 exe 旁。
- 新电脑：云端无本机记录时用 ip/mac/hostname 现造 deviceinfo 走 `/acc` 自动注册；
  未登录时点小球弹 Cookie 登录框（`LoginDialog` / `apply_cookie`）。
- **v1.0.2**：登录框小字改成两行 —— `登录并打开路由器的UU加速器后台` /
  `浏览器F12→ Application（应用程序）→ Cookies → https://router.uu.163.com → sess → value（值）`，
  下面蓝色一行提醒「该 cookie 自初次登录开始默认保存 15 天」（窗口加宽到 560×210 才放得下整行路径）；
  版本号进 `VERSION`，显示在右键菜单首行、窗口标题、`--version` / `--probe`。
