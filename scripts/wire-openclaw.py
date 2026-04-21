#!/usr/bin/env python3
"""
Idempotent merger that copies the JSON snippets in ../openclaw/ into a live
~/.openclaw/openclaw.json (and the per-agent auth-profiles.json), creating a
timestamped backup first.

Usage:
    scripts/wire-openclaw.py              # apply
    scripts/wire-openclaw.py --dry-run    # show what would change
    scripts/wire-openclaw.py --agent-id main   # default is 'main'
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNIPPETS = REPO / "openclaw"

CONFIG = Path.home() / ".openclaw" / "openclaw.json"


def _set_deep(root: dict, target: str, value) -> None:
    parts = target.split(".")
    cur = root
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _apply_snippet(root: dict, path: Path) -> str:
    raw = json.loads(path.read_text())
    target = raw.pop("_target", None)
    # Strip comment keys
    for k in list(raw.keys()):
        if k.startswith("_comment"):
            del raw[k]
    if target is None:
        raise SystemExit(f"{path.name} is missing _target")
    # The remaining object should have exactly one key whose value is what we want to set.
    if len(raw) == 1:
        value = next(iter(raw.values()))
    else:
        value = raw
    _set_deep(root, target, value)
    return target


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--agent-id", default="main")
    args = ap.parse_args()

    if not CONFIG.exists():
        sys.exit(f"{CONFIG} not found — install openclaw first (openclaw onboard)")

    cfg = json.loads(CONFIG.read_text())

    targets_applied = []
    for snippet in sorted(SNIPPETS.glob("*.json")):
        # Skip auth-profile snippet — that belongs in a different file.
        if snippet.name == "auth-profile-snippet.json":
            continue
        tgt = _apply_snippet(cfg, snippet)
        targets_applied.append((snippet.name, tgt))

    # Auth profile lives in a per-agent file.
    agent_auth = (
        Path.home()
        / ".openclaw"
        / "agents"
        / args.agent_id
        / "agent"
        / "auth-profiles.json"
    )
    if not agent_auth.exists():
        sys.exit(f"{agent_auth} not found — run `openclaw agents add {args.agent_id}` first")

    auth_data = json.loads(agent_auth.read_text())
    auth_snippet = json.loads((SNIPPETS / "auth-profile-snippet.json").read_text())
    for k in list(auth_snippet.keys()):
        if k.startswith("_comment") or k == "_target":
            auth_snippet.pop(k, None)
    for pname, pbody in auth_snippet.items():
        auth_data.setdefault("profiles", {})[pname] = pbody
    targets_applied.append(("auth-profile-snippet.json", f"agents.{args.agent_id}.auth-profiles.{list(auth_snippet)[0]}"))

    if args.dry_run:
        print("Would apply:")
        for name, tgt in targets_applied:
            print(f"  {name}  →  {tgt}")
        return

    ts = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(CONFIG, CONFIG.with_suffix(f".json.bak-{ts}"))
    shutil.copy2(agent_auth, agent_auth.with_suffix(f".json.bak-{ts}"))
    CONFIG.write_text(json.dumps(cfg, indent=2))
    agent_auth.write_text(json.dumps(auth_data, indent=2))

    print("✓ applied:")
    for name, tgt in targets_applied:
        print(f"  {name}  →  {tgt}")
    print(f"backups:  {CONFIG.with_suffix(f'.json.bak-{ts}')}")
    print(f"          {agent_auth.with_suffix(f'.json.bak-{ts}')}")
    print()
    print("Next:  openclaw gateway restart")


if __name__ == "__main__":
    main()
