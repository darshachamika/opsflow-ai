"""Provision/rotate one local MVP actor. Store only a token hash in root .env."""
import argparse
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--subject", required=True)
parser.add_argument("--role", required=True, choices=["PROCUREMENT_MANAGER", "OPERATOR", "ADMIN"])
parser.add_argument("--hours", type=int, default=8)
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", args.subject) or not 1 <= args.hours <= 24:
    parser.error("Use a simple subject ID and lifetime between 1 and 24 hours.")
path = Path(__file__).resolve().parents[2] / ".env"
source = path.read_text(encoding="utf-8-sig")
lines = source.splitlines()
prefix = "APPROVAL_PRINCIPALS_JSON="
indices = [i for i, line in enumerate(lines) if line.startswith(prefix)]
if len(indices) > 1:
    raise SystemExit("Duplicate APPROVAL_PRINCIPALS_JSON settings. Keep one before provisioning.")
actors = []
if indices:
    raw = lines[indices[0]][len(prefix):].strip()
    if raw.startswith("'") and raw.endswith("'"):
        raw = raw[1:-1]
    actors = json.loads(raw)
    if not isinstance(actors, list):
        raise SystemExit("Existing approval credentials must be a JSON list.")
# Reprovisioning a subject revokes their old local token on server restart.
actors = [actor for actor in actors if actor["subject"] != args.subject]
token = secrets.token_urlsafe(48)
expires = datetime.now(timezone.utc) + timedelta(hours=args.hours)
actors.append({"subject": args.subject, "role": args.role,
    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    "expires_at": expires.isoformat(), "enabled": True})
line = prefix + "'" + json.dumps(actors, separators=(",", ":")) + "'"
if indices:
    lines[indices[0]] = line
else:
    lines.append(line)
path.write_text('\n'.join(lines) + '\n', encoding="utf-8")
print(f"Provisioned {args.subject} as {args.role}; expires {expires.isoformat()}.")
print("Restart the API. Paste this token into Swagger Authorize; do not share it:")
print(token)
