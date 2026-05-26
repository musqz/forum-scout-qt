#!/usr/bin/env bash
set -e

INSTALL_BIN="/usr/local/bin/forum-scout"
INSTALL_SHARE="/usr/local/share/forum-scout"
INSTALL_APPS="/usr/local/share/applications"

echo "Installing Forum Scout Qt..."

install -Dm755 forum-scout-qt.py "$INSTALL_BIN"
install -Dm644 forum-scout-qt.desktop "$INSTALL_APPS/forum-scout-qt.desktop"
install -d "$INSTALL_SHARE/translations"
install -Dm644 translations/*.json "$INSTALL_SHARE/translations/"

sed -i "s/__VERSION__/$(cat VERSION)/" "$INSTALL_BIN"

echo "Done. Run: forum-scout"
