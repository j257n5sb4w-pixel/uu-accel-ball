# UU 鍔犻€熺悆锛圲U Accelerator Ball锛?
涓€涓?**Windows 妗岄潰灏忕悆**锛岀敤鏉ョ粰鏈満锛圥C锛夊湪**璺敱鍣ㄤ笂鐨勭綉鏄?UU 鍔犻€熷櫒鎻掍欢**閲?涓€閿垏鎹㈠姞閫熺殑娓告垙 / 澶у尯锛屽苟甯搁┗鏄剧ず褰撳墠鍔犻€熸父鎴忕殑灏侀潰銆?
- 鐧借壊鍗婇€忔槑鍦嗗舰灏忕悆锛岀疆椤躲€佸彲鎷栧姩锛屾敹璧锋€佸彧鏄剧ず娓告垙灏侀潰
- 鐐瑰紑鏄悳绱㈤潰鏉匡細鏈€杩戞父鐜╋紙鍙屽嚮鐩存帴鍔犻€燂級锛嬫寜鎷奸煶棣栧瓧姣嶅垎缁勭殑鍏ㄩ儴娓告垙
- 鑷姩鎺㈡祴璺敱鍣ㄤ笂鐨?UU 鎻掍欢锛坄16363/TCP` 鏄庢枃 HTTP `GET /router`锛?- 鑷姩閿佸畾鏈満璁惧锛圛P 鈫?MAC 涓夌骇鍖归厤锛屾柊鐢佃剳鍙敤鏈満淇℃伅鑷姩娉ㄥ唽锛?- 璁板綍鎸佷箙鍖栵細灏忕悆浣嶇疆銆佹渶杩戠帺杩囩殑娓告垙/鍖烘湇銆佸皝闈㈢紦瀛橀兘鍦?`uu-data\`
- 鍙墦鍖呮垚渚挎惡 exe锛屾暣涓枃浠跺す鎷峰埌鍒殑鐢佃剳灏辫兘鐢?
> 涓庣綉鏄?/ UU 瀹樻柟鏃犲叧锛岀函灞炰釜浜鸿嚜鐢ㄥ伐鍏凤紱瀹冭皟鐢ㄧ殑鏄?`router.uu.163.com`
> 涓婅矾鐢卞櫒椤甸潰鑷繁鐨?`api`锛屼笉淇敼浠讳綍瀹樻柟浜岃繘鍒躲€?
## 蹇€熷紑濮嬶紙婧愮爜杩愯锛?
```bat
python uuball.pyw            :: 闇€瑕?Python 3.9+锛坱kinter锛?python uuball.pyw --selftest :: 涓嶅紑绐楋紝鎵撳嵃鎺㈡祴/鐧诲綍/璁惧/娓告垙搴撶粨鏋?```

棣栨杩愯鑻ュ皬鐞冩樉绀恒€屾湭鐧诲綍銆嶏紝鐐瑰畠 鈫?寮瑰嚭鐧诲綍妗?鈫?绮樿创娴忚鍣?Cookie锛?
1. 娴忚鍣ㄦ墦寮€ `https://router.uu.163.com/asus/pc.html` 骞剁櫥褰曪紙鍙湁鐭俊楠岃瘉鐮佺櫥褰曪級
2. F12 鈫?Network 鈫?鐐逛换鎰?`/api/...` 璇锋眰 鈫?澶嶅埗璇锋眰澶?`Cookie` 鏁翠覆锛堝惈 `sess=...`锛?3. 绮樿繘妗嗛噷鐐广€岀櫥褰曘€嶏紝浼氳瘽绾?15 澶╂湁鏁?
## 鎵撳寘鎴?exe

```bat
build_exe.cmd
```

鐢?PyInstaller锛坄--onedir --windowed`锛変骇鍑?`dist\UU鍔犻€熺悆\UU鍔犻€熺悆.exe`銆?`build_exe.cmd` 閲屾妸渚濊禆瑁呭湪 `_pylib`锛堢敱 `_whl3.py` 浠庨暅鍍忓彇 whl 瑙ｅ帇锛夛紝
涓嶆薄鏌撳叏灞€ site-packages銆?
> 娉ㄦ剰锛氬崟鏂囦欢 `--onefile` 鍦ㄥ彈闄愮幆澧冿紙绂佹瀛愯繘绋嬭В鍖呭埌 TEMP锛夐噷浼氬崱姝伙紝
> 鍥犳榛樿浜や粯 onedir銆傝鍗曟枃浠跺氨鑷繁鎶?`--onedir` 鎹㈡垚 `--onefile` 閲嶆墦銆?
## 宸ヤ綔鍘熺悊锛堜笁姝ワ級

1. **鎵炬彃浠?*锛歚GET http://<router>:16363/router` 杩斿洖
   `type:asuswrt / sn:... / model:...`锛岃兘鍥炲寘璇存槑 UU 鎻掍欢娲荤潃锛堣绔彛鐢辨彃浠惰嚜宸辩洃鍚級銆?2. **鎵炬湰鏈?*锛歚router.uu.163.com/api` 鐨勮澶囧垪琛ㄩ噷鎸?`ip+windows` 鈫?`ip` 鈫?`mac` 鍖归厤锛?   閮芥病鏈夊氨鐢?`{type:windows, mac, ip, hostname}` 鐜伴€犱竴涓紝`POST /acc` 鏃跺悗绔細娉ㄥ唽銆?3. **鍒囨父鎴?*锛歚POST /acc-mode-setting`锛堝甫 `game_id/zone_id/server_id`锛夆啋 `POST /acc`锛?   鍋滄璧?`POST /stop-acc`銆?
闈㈡澘涓庡皬鐞冨彧鍋氳繖涓変欢浜嬶紱`uu.py` 閲岀殑 SSH 閮ㄥ垎锛坄uuctl.sh`/`uu_route.sh`锛夋槸鍙€夌殑
杩愮淮宸ュ叿锛氭煡鐪嬫彃浠惰繘绋嬨€佸惎鍋滅湅闂ㄧ嫍銆佹妸鏌愬彴璁惧鐨勫姞閫熻鍒欏厠闅嗙粰鍙︿竴鍙般€?
## 鏂囦欢

| 鏂囦欢 | 浣滅敤 |
|---|---|
| `uuball.pyw` | 灏忕悆 + 闈㈡澘鍏ㄩ儴 UI锛坱kinter锛屾棤绗笁鏂逛緷璧栵級 |
| `uu.py` | 浜戠 API / SSH 鍛戒护琛岋紙`dev` `acc` `unacc` `games` `login` `status` 鈥︼級 |
| `uuctl.sh` / `uu_route.sh` | 璺敱鍣ㄤ晶鍔╂墜锛氭彃浠惰繘绋嬬鐞嗐€乣ip rule` + `iptables` 瑙勫垯鍏嬮殕 |
| `build_exe.cmd` | PyInstaller 鎵撳寘鑴氭湰 |
| `REPORT.md` | 閫嗗悜涓庡疄娴嬭褰曪紙鏈湴鎺у埗闈€佷簯绔?API銆佹暟鎹潰瑙勫垯锛?|
| `HANDOFF.md` | 浜ゆ帴鏂囨。锛氱幆澧冦€佸懡浠ゃ€佺姸鎬佸揩鐓?|

## 闅愮

浠撳簱閲屼笉鍚处鍙蜂細璇濓紙`session.json`锛夈€佽澶囧垪琛紙`state.json`锛夈€?璺敱鍣ㄥ嚟鎹紙宸叉浛鎹㈡垚 `<ROUTER_USER>` 绛夊崰浣嶇锛変笌瀹樻柟浜岃繘鍒躲€?杩愯鏃剁敓鎴愮殑 `uu-data\` 宸插湪 `.gitignore` 涓€?
## 璁稿彲

MIT
