#!/bin/sh
# uuctl.sh - single-command control for the NetEase UU router plugin (ASUSWRT RT-AX86U).
# Usage: /bin/sh /tmp/uuctl.sh {status|start|stop|restart|ensure}
# NOTE: uuplugin exposes no local CLI/API; this wrapper only manages its processes
#       and reports the policy-routing/tunnel state it produces.

UU_DIR=/tmp/uu
EXE="$UU_DIR/uuplugin"
CONF="$UU_DIR/uu.conf"
MON="$UU_DIR/uuplugin_monitor.sh"
PID_FILE=/var/run/uuplugin.pid

gp() { ps w | grep "$1" | grep -v grep | awk '{print $1}'; }
plugin_pid() { gp "/tmp/uu/uuplugin "; }
monitor_pid() { gp "uuplugin_monitor.sh"; }
guardian_pid() { gp "xuplugin-guardian"; }

status() {
    echo "== UU accelerator status =="
    p=$(plugin_pid); m=$(monitor_pid); g=$(guardian_pid)
    echo "uuplugin  : ${p:--}   (pidfile: $(cat $PID_FILE 2>/dev/null))"
    echo "monitor   : ${m:--}   (watchdog, respawns plugin)"
    echo "guardian  : ${g:--}"
    echo "activate  : $(cat $UU_DIR/activate_status 2>/dev/null)"
    echo "version   : $(grep '^version' $CONF 2>/dev/null)"
    if ip link show tun163 2>/dev/null | grep -q "state UNKNOWN"; then
        echo "tunnel    : tun163 UP"
    else
        echo "tunnel    : tun163 DOWN"
    fi
    echo "accelerating:"
    ip rule show 2>/dev/null | grep -E "lookup (163|179)" | sed 's/^/  /'
    echo "traffic:"
    ip -s link show tun163 2>/dev/null | sed -n '3,6p' | sed 's/^/  /'
}

ensure_monitor() {
    [ -x "$MON" ] || { echo "missing $MON"; return 1; }
    if [ -n "$(monitor_pid)" ]; then
        echo "monitor already running ($(monitor_pid))"
        return 0
    fi
    cd "$UU_DIR" || return 1
    nohup /bin/sh "$MON" >/dev/null 2>&1 &
    sleep 2
    if [ -n "$(monitor_pid)" ]; then
        echo "monitor started ($(monitor_pid))"
        return 0
    fi
    echo "monitor failed to start"
    return 1
}

start() {
    if [ -n "$(plugin_pid)" ]; then
        echo "uuplugin already running ($(plugin_pid))"
        ensure_monitor
        return $?
    fi
    [ -x "$EXE" ] || { echo "missing $EXE"; return 1; }
    ensure_monitor >/dev/null 2>&1
    i=0
    while [ $i -lt 20 ]; do
        if [ -n "$(plugin_pid)" ]; then
            echo "uuplugin started ($(plugin_pid))"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    echo "start timeout"
    return 1
}

stop() {
    # order: monitor (respawner) -> guardian -> plugin
    for pat in "uuplugin_monitor.sh" "xuplugin-guardian" "/tmp/uu/uuplugin "; do
        for pid in $(gp "$pat"); do
            kill "$pid" 2>/dev/null && echo "killed $pid ($pat)"
        done
    done
    sleep 2
    for pid in $(gp "/tmp/uu/uuplugin "); do
        kill -9 "$pid" 2>/dev/null && echo "killed -9 $pid"
    done
    return 0
}

case "$1" in
    status) status ;;
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    ensure) ensure_monitor ;;
    *) echo "usage: $0 {status|start|stop|restart|ensure}"; exit 2 ;;
esac
