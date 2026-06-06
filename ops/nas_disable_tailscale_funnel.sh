#!/usr/bin/env bash
set -euo pipefail

NAS_HOST="${NAS_HOST:-zhangdong@dxp4800pro}"

ssh -o ConnectTimeout=8 "$NAS_HOST" \
  "docker exec tailscale-nas tailscale funnel reset && docker exec tailscale-nas tailscale funnel status"
