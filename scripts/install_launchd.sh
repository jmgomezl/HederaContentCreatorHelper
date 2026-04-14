#!/usr/bin/env bash
# Install and load the HederaContentCreatorHelper launchd services on the Mac mini.
set -euo pipefail

REPO_DIR="/Users/juanma_bot/HederaContentCreatorHelper"
LA_DIR="$HOME/Library/LaunchAgents"

mkdir -p "$LA_DIR"
mkdir -p "$REPO_DIR/logs"

# Copy plists
cp "$REPO_DIR/scripts/com.hedera.content.dashboard.plist" "$LA_DIR/com.hedera.content.dashboard.plist"
cp "$REPO_DIR/scripts/com.hedera.content.weekly.plist" "$LA_DIR/com.hedera.content.weekly.plist"

# Unload if already loaded (idempotent)
launchctl unload "$LA_DIR/com.hedera.content.dashboard.plist" 2>/dev/null || true
launchctl unload "$LA_DIR/com.hedera.content.weekly.plist" 2>/dev/null || true

# Load both
launchctl load -w "$LA_DIR/com.hedera.content.dashboard.plist"
launchctl load -w "$LA_DIR/com.hedera.content.weekly.plist"

echo "=== Installed launchd services ==="
launchctl list | grep hedera || echo "(none listed yet - may take a moment)"
echo
echo "Dashboard:  will auto-start now and on every login"
echo "Weekly job: will fire every Sunday at 20:00 local time"
echo
echo "Logs:"
echo "  $REPO_DIR/logs/launchd-dashboard.{stdout,stderr}.log"
echo "  $REPO_DIR/logs/launchd-weekly.{stdout,stderr}.log"
