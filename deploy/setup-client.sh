#!/usr/bin/env bash
# Nối MỘT MÁY CON vào ccbus (chạy trên cả Ubuntu lẫn macOS).
# Dùng: ./deploy/setup-client.sh <url-server> <token-của-máy-này> [tên-project]
#   ví dụ: ./deploy/setup-client.sh http://100.101.102.103:7717 tok_abc my-app
set -euo pipefail

URL="${1:-}"
TOKEN="${2:-}"
PROJECT="${3:-}"

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  echo "Dùng: $0 <url-server> <token> [tên-project]" >&2
  exit 1
fi
URL="${URL%/}"

echo "==> Kiểm tra kết nối tới $URL"
if ! curl -fsS --max-time 10 "$URL/health" >/dev/null; then
  echo "Không gọi được $URL/health — kiểm tra server đã chạy và mạng/tailscale đã thông." >&2
  exit 1
fi

echo "==> Kiểm tra token"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
  -H "Authorization: Bearer $TOKEN" "$URL/api/status")"
if [ "$code" != "200" ]; then
  echo "Token bị từ chối (HTTP $code)." >&2
  exit 1
fi

echo "==> Đăng ký MCP server 'ccbus' cho Claude Code"
claude mcp remove ccbus --scope user >/dev/null 2>&1 || true
claude mcp add --transport http ccbus "$URL/mcp" --scope user \
  --header "Authorization: Bearer $TOKEN"

echo "==> Ghi biến môi trường cho CLI ccbus vào ~/.ccbus/client-env"
mkdir -p "$HOME/.ccbus"
umask 077
cat >"$HOME/.ccbus/client-env" <<EOF
export CCBUS_URL=$URL
export CCBUS_TOKEN=$TOKEN
export CCBUS_PROJECT=${PROJECT:-default}
EOF
chmod 600 "$HOME/.ccbus/client-env"

echo
echo "Xong. Kiểm tra bằng:  claude mcp list"
echo "Cho CLI:  echo '. ~/.ccbus/client-env' >> ~/.bashrc   # hoặc ~/.zshrc trên Mac"
if [ -n "$PROJECT" ]; then
  echo "Đừng quên thêm hướng dẫn vào CLAUDE.md của project:  ccbus init /đường/dẫn/project"
fi
