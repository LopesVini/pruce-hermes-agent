#!/bin/sh
# Run the official pairing-only entry point, without rewriting Hermes/Plow .env.
set -eu
export HOME=/var/lib/hermes
session_path="$(/opt/hermes/.venv/bin/python3 -c 'import sys; sys.path.insert(0,"/opt/hermes"); from hermes_constants import get_hermes_dir; print(get_hermes_dir("platforms/whatsapp/session","whatsapp/session"))')"
umask 077
exec node /opt/hermes/scripts/whatsapp-bridge/bridge.js --pair-only --mode bot --session "$session_path"
