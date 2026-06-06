#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"
NAS_PROJECT_ROOT="${NAS_PROJECT_ROOT:-/volume1/docker/market-live-terminal/app}"
NAS_ENV_FILE="${NAS_ENV_FILE:-$NAS_PROJECT_ROOT/.env.nas-full}"
NAS_COMPOSE_FILE="${NAS_COMPOSE_FILE:-deploy/docker-compose.nas-full.yml}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

require_cmd ssh

ssh -o ConnectTimeout=8 "$NAS_HOST" "
  set -e
  echo '=== host dns probe ==='
  python3 - <<'PY'
import socket
for host in ['qt.gtimg.cn', 'stock.gtimg.cn']:
    try:
        print(host, socket.gethostbyname(host))
    except Exception as exc:
        print(host, 'DNS_FAIL', exc)
PY
  echo
  echo '=== host http probe ==='
  python3 - <<'PY'
import urllib.request
for url in [
    'http://qt.gtimg.cn/q=s_sh600519',
    'http://stock.gtimg.cn/data/index.php?appn=detail&action=data&c=sh600519&p=0',
]:
    try:
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.qq.com'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read(160).decode('gbk', errors='ignore')
        print('OK', url, text[:120])
    except Exception as exc:
        print('FAIL', url, repr(exc))
PY
  echo
  echo '=== crawler container http probe ==='
  cd '$NAS_PROJECT_ROOT'
  docker compose --env-file '$NAS_ENV_FILE' -f '$NAS_COMPOSE_FILE' run --rm crawler python - <<'PY'
import urllib.request
for url in [
    'http://qt.gtimg.cn/q=s_sh600519',
    'http://stock.gtimg.cn/data/index.php?appn=detail&action=data&c=sh600519&p=0',
]:
    try:
        req = urllib.request.Request(url, headers={'Referer': 'http://finance.qq.com'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read(160).decode('gbk', errors='ignore')
        print('OK', url, text[:120])
    except Exception as exc:
        print('FAIL', url, repr(exc))
PY
"
