#!/usr/bin/env bash
# Thêm một máy mới vào ccbus mà KHÔNG đổi token của các máy đang chạy.
# Chạy trên MÁY CHỦ. Dùng: ./deploy/add-agent.sh <tên-máy>
#   ví dụ: ./deploy/add-agent.sh ssd
set -euo pipefail

AGENT="${1:-}"
CCBUS_HOME="${CCBUS_HOME:-$HOME/.ccbus}"
ENV_FILE="$CCBUS_HOME/env"

if [ -z "$AGENT" ]; then
  echo "Dùng: $0 <tên-máy>" >&2
  exit 1
fi
case "$AGENT" in
  *:*|*,*) echo "Tên máy không được chứa ':' hoặc ','." >&2; exit 1 ;;
esac
[ -f "$ENV_FILE" ] || { echo "Không thấy $ENV_FILE — chạy ./deploy/setup-host.sh trước." >&2; exit 1; }

TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"

python3 - "$ENV_FILE" "$AGENT" "$TOKEN" <<'PY'
import sys

env_file, agent, token = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(env_file, encoding="utf-8").read().splitlines()

for i, line in enumerate(lines):
    if not line.startswith("CCBUS_TOKENS="):
        continue
    pairs = [p for p in line.split("=", 1)[1].split(",") if p]
    if any(p.partition(":")[0] == agent for p in pairs):
        sys.exit(f"Máy '{agent}' đã có token trong {env_file}. Xoá dòng của nó trước nếu muốn cấp lại.")
    pairs.append(f"{agent}:{token}")
    lines[i] = "CCBUS_TOKENS=" + ",".join(pairs)
    break
else:
    lines.append(f"CCBUS_TOKENS={agent}:{token}")

open(env_file, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY

chmod 600 "$ENV_FILE"

# Server chỉ đọc CCBUS_TOKENS lúc khởi động, nên phải nạp lại thì token mới có tác dụng.
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  echo "==> Khởi động lại ccbus để nạp token mới"
  systemctl --user restart ccbus
  sleep 2
  systemctl --user --no-pager --lines=3 status ccbus || true
else
  echo "==> Không có systemd — khởi động lại server bằng tay để nạp token mới."
fi

HOST_ADDR="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
HOST_ADDR="${HOST_ADDR:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
HOST_ADDR="${HOST_ADDR:-127.0.0.1}"
PORT="$(sed -n 's/^CCBUS_PORT=//p' "$ENV_FILE" | head -1)"
PORT="${PORT:-7717}"

echo
echo "==================== LỆNH CHO MÁY '$AGENT' ===================="
echo "./deploy/setup-client.sh http://$HOST_ADDR:$PORT $TOKEN <tên-project>"
echo
echo "Hoặc làm tay:"
echo "claude mcp add --transport http ccbus http://$HOST_ADDR:$PORT/mcp --scope user \\"
echo "  --header \"Authorization: Bearer $TOKEN\""
