# UU 加速球（UU Accelerator Ball）

一个 **Windows 桌面小球**，用来给本机（PC）在**路由器上的网易 UU 加速器插件**里
一键切换加速的游戏 / 大区，并常驻显示当前加速游戏的封面。

- 白色半透明圆形小球，置顶、可拖动，收起态只显示游戏封面
- 点开是搜索面板：最近游玩（双击直接加速）＋按拼音首字母分组的全部游戏
- 自动探测路由器上的 UU 插件（`16363/TCP` 明文 HTTP `GET /router`）
- 自动锁定本机设备（IP → MAC 三级匹配，新电脑可用本机信息自动注册）
- 记录持久化：小球位置、最近玩过的游戏/区服、封面缓存都在 `uu-data\`
- 可打包成便携 exe，整个文件夹拷到别的电脑就能用

> 与网易 / UU 官方无关，纯属个人自用工具；它调用的是 `router.uu.163.com`
> 上路由器页面自己在用的 `api`，不修改任何官方二进制。

## 下载（Windows 便携版）

[v1.0.0 release](https://github.com/j257n5sb4w-pixel/uu-accel-ball/releases/latest)
里的 `uu-ball-v1.0.0-win64.zip`：解压 → 双击 `UU加速球.exe`。
包内不含任何账号会话，第一次运行需要粘一次 Cookie（见下）。

## 快速开始（源码运行）

```bat
python uuball.pyw            :: 需要 Python 3.9+（tkinter），无第三方依赖
python uuball.pyw --selftest :: 不开窗，打印探测/登录/设备/游戏库结果
```

首次运行若小球显示「未登录」，点它 → 弹出登录框 → 粘贴浏览器 Cookie：

1. 浏览器打开 `https://router.uu.163.com/asus/pc.html` 并登录（只有短信验证码登录）
2. F12 → Network → 点任意 `/api/...` 请求 → 复制请求头 `Cookie` 整串（含 `sess=...`）
3. 粘进框里点「登录」，会话约 15 天有效

## 打包成 exe

```bat
build_exe.cmd
```

用 PyInstaller（`--onedir --windowed`）产出 `dist\UU加速球\UU加速球.exe`。
`build_exe.cmd` 里的依赖装在 `_pylib`（由 `_whl3.py` 从镜像取 whl 解压），
不污染全局 site-packages。

> 注意：单文件 `--onefile` 在受限环境（禁止子进程解包到 TEMP）里会卡死，
> 因此默认交付 onedir。要单文件就自己把 `--onedir` 换成 `--onefile` 重打。

## 工作原理（三步）

1. **找插件**：`GET http://<router>:16363/router` 返回
   `type:asuswrt / sn:... / model:...`，能回包说明 UU 插件活着（该端口由插件自己监听）。
2. **找本机**：`router.uu.163.com/api` 的设备列表里按 `ip+windows` → `ip` → `mac` 匹配；
   都没有就用 `{type:windows, mac, ip, hostname}` 现造一个，`POST /acc` 时后端会注册。
3. **切游戏**：`POST /acc-mode-setting`（带 `game_id/zone_id/server_id`）→ `POST /acc`；
   停止走 `POST /stop-acc`。

面板与小球只做这三件事；`uu.py` 里的 SSH 部分（`uuctl.sh` / `uu_route.sh`）是可选的
运维工具：查看插件进程、启停看门狗、把某台设备的加速规则克隆给另一台。

## 文件

| 文件 | 作用 |
|---|---|
| `uuball.pyw` | 小球 + 面板全部 UI（tkinter，无第三方依赖） |
| `uu.py` | 云端 API / SSH 命令行（`dev` `acc` `unacc` `games` `login` `status` …） |
| `uuctl.sh` / `uu_route.sh` | 路由器侧助手：插件进程管理、`ip rule` + `iptables` 规则克隆 |
| `build_exe.cmd` | PyInstaller 打包脚本 |
| `REPORT.md` | 逆向与实测记录（本地控制面、云端 API、数据面规则） |
| `HANDOFF.md` | 交接文档：环境、命令、状态快照 |

## 隐私

仓库里不含账号会话（`session.json`）、设备列表（`state.json`）、
路由器凭据（已替换成 `<ROUTER_USER>` / `<ROUTER_PASSWORD>` / `<ROUTER_SN>` 占位符）
与官方二进制。运行时生成的 `uu-data\` 已在 `.gitignore` 中。

## 许可

MIT，见 `LICENSE`。
