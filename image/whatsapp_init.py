"""Prepare the official bridge's private home; never pair or change other state."""
import os
import pwd
import re
import sys
from pathlib import Path

sys.path.insert(0, "/opt/hermes")


def validate(env):
    allowed = env.get("WHATSAPP_ALLOWED_USERS", "").strip()
    if allowed and not re.fullmatch(r"[1-9][0-9]{7,14}", allowed):
        raise ValueError("POC WhatsApp allowlist must contain one phone number, digits only")
    if env.get("WHATSAPP_ALLOW_ALL_USERS", "false").lower() != "false":
        raise ValueError("POC WhatsApp cannot allow all users")
    if env.get("WHATSAPP_DM_POLICY", "allowlist") != "allowlist" or env.get("WHATSAPP_GROUP_POLICY", "disabled") != "disabled":
        raise ValueError("POC WhatsApp requires allowlist DMs and disabled groups")
    enabled = env.get("WHATSAPP_ENABLED", "false").lower() in {"true", "1", "yes", "on"}
    if enabled and not allowed:
        raise ValueError("Set WHATSAPP_ALLOWED_USERS before enabling WhatsApp")
    home = env.get("WHATSAPP_HOME_CHANNEL", "").strip()
    if home and home != allowed + "@s.whatsapp.net":
        raise ValueError("WhatsApp home must be the allowlisted sender DM JID")


def main():
    from hermes_constants import get_hermes_dir
    try:
        validate(os.environ)
    except ValueError as error:
        # Fail closed for this channel without parking Plow or the gateway.
        Path("/run/s6/container_environment/WHATSAPP_ENABLED").write_text("false")
        print(f"WhatsApp disabled: {error}", flush=True)
    path = get_hermes_dir("platforms/whatsapp/session", "whatsapp/session")
    user = pwd.getpwnam("hermes")
    path.mkdir(parents=True, exist_ok=True)
    for directory in (path.parent, path):
        os.chown(directory, user.pw_uid, user.pw_gid)
        os.chmod(directory, 0o700)
    print("WhatsApp session directory ready; pairing remains manual", flush=True)


if __name__ == "__main__":
    main()
