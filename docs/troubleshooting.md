# Troubleshooting

Every real error we hit, the cause, and the fix. Roughly ordered from "most
likely to bite you first" downward.

---

### `Error: gateway closed (1008): pairing required` from CLI tools

**What's happening:** The gateway enforces device pairing for scope-sensitive
operations (`openclaw cron list`, `openclaw system event`, `openclaw devices
list`, etc.) even on loopback even with `gateway.auth.mode: "none"`. Your
backend clients (e.g. the telegram native-approval handler) may be paired
with only `operator.read` scope and fail scope upgrades with pairing-required
on every reconnect — causing a spam loop in the err log.

**Fix:** Promote the backend device to full scope directly in
`~/.openclaw/devices/paired.json` and move any pending requests to paired:

```python
import json, pathlib, time
paired = json.loads(pathlib.Path("~/.openclaw/devices/paired.json").expanduser().read_text())
pending = json.loads(pathlib.Path("~/.openclaw/devices/pending.json").expanduser().read_text())
FULL = ["operator.admin","operator.approvals","operator.pairing","operator.read","operator.write"]
for d in paired.values():
    if d.get("clientMode") == "backend" and d.get("scopes") == ["operator.read"]:
        d["scopes"] = FULL; d["approvedScopes"] = FULL
        for t in d.get("tokens", {}).values(): t["scopes"] = FULL
for rid, req in list(pending.items()):
    if req.get("clientMode") == "backend":
        did = req["deviceId"]
        paired[did] = {**paired.get(did, {}), **req, "scopes": FULL, "approvedScopes": FULL,
                        "approvedAtMs": int(time.time()*1000)}
        del pending[rid]
pathlib.Path("~/.openclaw/devices/paired.json").expanduser().write_text(json.dumps(paired, indent=2))
pathlib.Path("~/.openclaw/devices/pending.json").expanduser().write_text(json.dumps(pending, indent=2))
```

Restart the gateway afterwards.

---

### "No API key found for provider 'anthropic'" during agent run

You added `models.providers.anthropic` but forgot the matching auth profile at
`~/.openclaw/agents/<agent-id>/agent/auth-profiles.json`. Add:

```json
"anthropic:default": {
  "type": "api_key",
  "provider": "anthropic",
  "key": "proxy-billing-dummy"
}
```

The key is a placeholder — the billing proxy injects your real OAuth token
server-side.

---

### Stale `*.jsonl.lock` files block the agent

If the gateway crashes mid-run it leaves lockfiles in
`~/.openclaw/agents/<id>/sessions/`. Next run sees "session file locked
(timeout 10000ms)". Clean them:

```bash
rm -f ~/.openclaw/agents/*/sessions/*.lock
```

Safe to do whenever the gateway isn't actively writing (i.e. during normal
idle state or right after a restart).

---

### Overnight `4x duplicate replies` / `token burn`

Symptom: you send one message, wake up to 4 slightly different answers plus a
lot of API use.

**Cause:** The upstream `claude-max-api-proxy` has a hardcoded 300000ms
(5-minute) HTTP timeout in `dist/subprocess/manager.js`. If Claude's internal
tool chain exceeds 5min, the proxy kills the HTTP connection, openclaw gets
"LLM timed out", *retries*, and the next claude subprocess eventually also
finishes late → multiple answers land.

**Fix options:**
1. Switch to the billing-proxy route (this repo's primary path) — no timeout,
   no retries, native streaming.
2. If you must stay on the OpenAI-format route, patch the proxy:
   ```bash
   sed -i '' \
     's#const DEFAULT_TIMEOUT = 300000;#const DEFAULT_TIMEOUT = parseInt(process.env.CLAUDE_PROXY_TIMEOUT_MS || "1200000", 10);#' \
     ~/.npm-global/lib/node_modules/claude-max-api-proxy/dist/subprocess/manager.js
   ```
   and set `CLAUDE_PROXY_TIMEOUT_MS` in the plist.

---

### Telegram splits one reply into 2–3 messages

`channels.telegram.streaming` defaults to `partial` or `block` mode — a long
reply is sent in chunks. Merge the `openclaw/telegram-no-split.snippet.json`
into your config:

```json
"channels": {
  "telegram": {
    "streaming": { "mode": "off" }
  }
}
```

Hot-reloadable — no gateway restart needed.

---

### `Claude returns "I would run uname -sr, run it yourself"`

You're on the OpenAI-format route with our `claude-shim.py` that tells Claude
"no tools available." That's correct behavior for that route — Claude can
refer to tools but not invoke them, because `claude --print`'s internal tool
loop produces multi-message streams that break openclaw's parser.

For an agent that *actually executes* actions, use the billing-proxy route.

---

### Agent replies as Claude, not as your persona ("I'm Claude, made by Anthropic")

`claude --print` uses its own default Claude-Code system prompt. The
OpenAI-format proxies flatten your system messages into `<system>...</system>`
prose which Claude reads but doesn't adopt.

- Billing-proxy route: native Anthropic API preserves `system` → persona is
  honored automatically.
- OpenAI-format route: install the shim, which extracts `<system>` tags and
  promotes them with `--system-prompt-file`.

---

### `ENOENT: claude not found` in proxy logs

The launchd agent can't resolve `claude` because launchd starts with an empty
PATH. Confirm your plist has a `PATH` env var that includes the directory
containing `claude` (likely `~/.npm-global/bin` or `/opt/homebrew/bin`).

---

### Mac goes to sleep → agent silently dies

Install the `com.example.stayawake.plist` which runs `caffeinate -dimsu` as a
long-running launchd job. For battery scenarios also run:

```bash
sudo pmset -b disablesleep 1 sleep 0 displaysleep 0 disksleep 0
```

---

### OAuth token expired

`sk-ant-oat01-…` tokens issued by `claude setup-token` can expire. The
billing-proxy health endpoint surfaces `tokenExpiresInHours` when reading
from `~/.claude/.credentials.json`; when set via `OAUTH_TOKEN` env var it
shows `n/a` (we don't track expiry).

Refresh with `claude setup-token`, update the `OAUTH_TOKEN` in the plist, and
`launchctl kickstart -k gui/$(id -u)/com.$(id -un).billing-proxy`.

---

### "Invalid streaming response. Unexpected event order, got message_start before receiving message_stop"

Specific to the Anthropic-native path when using intermediate proxies (e.g.
cc-max-proxy) that pass claude CLI's multi-message streams through verbatim.
The billing-proxy does NOT have this bug (it talks to api.anthropic.com
directly). If you see this, you're on the wrong proxy.
