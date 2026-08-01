#!/usr/bin/env bash
# Cài ccbus lên MÁY CHỦ (máy chạy server — chọn máy bật thường xuyên nhất, địa chỉ ổn định).
# Dùng: ./deploy/setup-host.sh [tên-máy-1 tên-máy-2 ...]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CCBUS_HOME="${CCBUS_HOME:-$HOME/.ccbus}"
ENV_FILE="$CCBUS_HOME/env"
PORT="${CCBUS_PORT:-7717}"
PROJECT="${CCBUS_DEFAULT_PROJECT:-default}"
AGENTS=("$@")
if [ ${#AGENTS[@]} -eq 0 ]; then
  AGENTS=(acer vivo cong-ty mac)
fi

mkdir -p "$CCBUS_HOME"

echo "==> Tạo virtualenv tại $CCBUS_HOME/venv"
if command -v uv >/dev/null 2>&1; then
  uv venv "$CCBUS_HOME/venv" >/dev/null
  uv pip install --python "$CCBUS_HOME/venv/bin/python" -e "$REPO_DIR" >/dev/null
else
  python3 -m venv "$CCBUS_HOME/venv"
  "$CCBUS_HOME/venv/bin/pip" install --quiet --upgrade pip
  "$CCBUS_HOME/venv/bin/pip" install --quiet -e "$REPO_DIR"
fi

if [ -f "$ENV_FILE" ]; then
  echo "==> $ENV_FILE đã tồn tại, giữ nguyên token cũ"
  echo "    (muốn đổi hết token: mv $ENV_FILE $ENV_FILE.bak rồi chạy lại script này)"
else
  echo "==> Sinh token cho: ${AGENTS[*]}"
  pairs=""
  for agent in "${AGENTS[@]}"; do
    token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    pairs+="${pairs:+,}${agent}:${token}"
  done
  umask 077
  cat >"$ENV_FILE" <<EOF
CCBUS_DB=$CCBUS_HOME/bus.db
CCBUS_HOST=0.0.0.0
CCBUS_PORT=$PORT
CCBUS_DEFAULT_PROJECT=$PROJECT
CCBUS_ALLOWED_HOSTS=*
CCBUS_TOKENS=$pairs
EOF
  chmod 600 "$ENV_FILE"
fi

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  echo "==> Cài systemd user unit"
  mkdir -p "$HOME/.config/systemd/user"
  install -m 644 "$REPO_DIR/deploy/ccbus.service" "$HOME/.config/systemd/user/ccbus.service"
  systemctl --user daemon-reload
  systemctl --user enable ccbus
  # restart chứ không phải `enable --now`: chạy lại script sau khi sửa env thì
  # service đang chạy phải nạp lại cấu hình mới
  systemctl --user restart ccbus
  loginctl enable-linger "$USER" 2>/dev/null || true
  sleep 2
  systemctl --user --no-pager --lines=5 status ccbus || true
else
  echo "==> Không có systemd. Chạy tay bằng:"
  echo "    set -a; . $ENV_FILE; set +a; $CCBUS_HOME/venv/bin/ccbus-server"
fi

HOST_ADDR="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
HOST_ADDR="${HOST_ADDR:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
HOST_ADDR="${HOST_ADDR:-127.0.0.1}"

echo
echo "==================== LỆNH CHO TỪNG MÁY CON ===================="
# shellcheck disable=SC2016
python3 - "$ENV_FILE" "$HOST_ADDR" "$PORT" <<'PY'
import sys
env_file, host, port = sys.argv[1], sys.argv[2], sys.argv[3]
tokens = ""
for line in open(env_file, encoding="utf-8"):
    if line.startswith("CCBUS_TOKENS="):
        tokens = line.split("=", 1)[1].strip()
for pair in tokens.split(","):
    name, _, token = pair.partition(":")
    print(f"\n# --- trên máy {name} ---")
    print(f'claude mcp add --transport http ccbus http://{host}:{port}/mcp --scope user \\')
    print(f'  --header "Authorization: Bearer {token}"')
PY
echo
echo "Kiểm tra:  curl -s http://$HOST_ADDR:$PORT/health"
