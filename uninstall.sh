#!/usr/bin/env bash
set -e

echo "Uninstalling Forum Scout Qt..."

rm -f  /usr/local/bin/forum-scout
rm -f  /usr/local/share/applications/forum-scout-qt.desktop
rm -rf /usr/local/share/forum-scout

echo "Done."
