#!/bin/sh
# uu_route.sh - clone the accelerating device's policy/DNAT rules onto another LAN IP.
#
# usage: /bin/sh /tmp/uu_route.sh <ip> show|on|off [template_device_ip]
# The template defaults to 192.168.50.91 (the device UU is accelerating now).
# This is a local stand-in for a cloud "Acc" push: same tunnel, same node session.

IP="$1"
ACT="$2"
TPL="${3:-192.168.50.91}"

case "$IP" in
  [0-9]*.[0-9]*.[0-9]*.[0-9]*) : ;;
  *) echo "usage: uu_route.sh <ip> show|on|off [template]"; exit 2 ;;
esac
case "$ACT" in show|on|off) : ;; *) echo "usage: uu_route.sh <ip> show|on|off"; exit 2 ;; esac

MARK_RULE="from $IP fwmark 0x163 lookup 163"
ROUTE_RULE="from $IP lookup 179"
MANGLE="-t mangle PREROUTING -s $IP/32 -i br0 -p udp -m udp --dport 53 -j MARK --set-xmark 0x163/0xffffffff"

clone_nat() {
  iptables -t nat -S PREROUTING 2>/dev/null | grep -F -- "-s $TPL/32" \
    | sed "s|^-A PREROUTING -s $TPL/32|-A PREROUTING -s $IP/32|"
}

do_show() {
  echo "-- ip rule ($IP)"
  ip rule 2>/dev/null | grep -F "from $IP " || echo "   (none)"
  echo "-- nat rules (actual, containing $IP)"
  iptables -t nat -S PREROUTING 2>/dev/null | grep -F "$IP" || echo "   (none)"
  echo "-- mangle rules (actual, containing $IP)"
  iptables -t mangle -S PREROUTING 2>/dev/null | grep -F "$IP" || echo "   (none)"
  echo "-- would clone from $TPL"
  clone_nat | sed 's/^/   /'
  echo "-- tunnel"
  ip -4 addr show tun163 2>/dev/null | grep -E 'inet|state'
  echo "-- table 179 prefixes: $(ip route show table 179 2>/dev/null | wc -l)"
}

do_on() {
  ip rule show 2>/dev/null | grep -qF "$ROUTE_RULE" || ip rule add from "$IP" lookup 179
  ip rule show 2>/dev/null | grep -qF "$MARK_RULE" || ip rule add from "$IP" fwmark 0x163 lookup 163
  iptables -t mangle -C PREROUTING -s "$IP/32" -i br0 -p udp -m udp --dport 53 \
    -j MARK --set-xmark 0x163/0xffffffff 2>/dev/null \
    || iptables -t mangle -A PREROUTING -s "$IP/32" -i br0 -p udp -m udp --dport 53 \
       -j MARK --set-xmark 0x163/0xffffffff
  clone_nat | while read -r r; do
    [ -z "$r" ] && continue
    chk=$(echo "$r" | sed 's/^-A /-C /')
    iptables -t nat $chk 2>/dev/null || iptables -t nat $r
  done
  echo "cloned $TPL -> $IP"
  do_show
}

do_off() {
  clone_nat | while read -r r; do
    [ -z "$r" ] && continue
    iptables -t nat -D PREROUTING $(echo "$r" | sed 's/^-A PREROUTING //') 2>/dev/null
  done
  iptables -t mangle -D PREROUTING -s "$IP/32" -i br0 -p udp -m udp --dport 53 \
    -j MARK --set-xmark 0x163/0xffffffff 2>/dev/null
  ip rule del from "$IP" fwmark 0x163 lookup 163 2>/dev/null
  ip rule del from "$IP" lookup 179 2>/dev/null
  echo "removed rules for $IP"
  do_show
}

case "$ACT" in
  show) do_show ;;
  on)   do_on ;;
  off)  do_off ;;
esac
