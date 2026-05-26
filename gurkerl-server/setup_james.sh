#!/bin/bash
# Sets up gurkerl-server as a launchd service on James.
# Run from ~/Code/gurkerl-list: bash gurkerl-server/setup_james.sh

set -e
REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
PLIST="$HOME/Library/LaunchAgents/com.james.gurkerl-server.plist"
LOG="$REPO_DIR/gurkerl-server/server.log"
ENV_FILE="$REPO_DIR/.env"

echo "=== Gurkerl server setup ==="
echo "Repo: $REPO_DIR"

# ── 1. Check .env ─────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "No .env found. Creating one now — enter your credentials:"
  echo ""
  read -p "SUPABASE_URL [https://mezayharkjyvnnhvdlww.supabase.co]: " SB_URL
  SB_URL="${SB_URL:-https://mezayharkjyvnnhvdlww.supabase.co}"
  read -p "SUPABASE_SERVICE_KEY (secret key from Supabase → Settings → API): " SB_KEY
  read -p "GURKERL_EMAIL: " GK_EMAIL
  read -s -p "GURKERL_PASSWORD: " GK_PASS
  echo ""
  cat > "$ENV_FILE" <<EOF
SUPABASE_URL=$SB_URL
SUPABASE_SERVICE_KEY=$SB_KEY
GURKERL_EMAIL=$GK_EMAIL
GURKERL_PASSWORD=$GK_PASS
EOF
  echo "✓ .env written to $ENV_FILE"
else
  echo "✓ .env already exists — skipping credential setup"
fi

# ── 2. Install Python dependencies ────────────────────────────────────────────
echo ""
echo "Installing Python dependencies..."
pip3 install -q -r "$REPO_DIR/gurkerl-server/requirements.txt"
echo "✓ Dependencies installed"

# ── 3. Write launchd plist ────────────────────────────────────────────────────
echo ""
echo "Writing launchd plist..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.james.gurkerl-server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$REPO_DIR/gurkerl-server/server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG</string>
    <key>StandardErrorPath</key>
    <string>$LOG</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF
echo "✓ Plist written to $PLIST"

# ── 4. Load (or reload) the service ──────────────────────────────────────────
echo ""
echo "Starting service..."
launchctl bootout "gui/$(id -u)/com.james.gurkerl-server" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✓ gurkerl-server is running"

echo ""
echo "Logs: tail -f $LOG"
echo "Done!"
