# Setup walkthrough

Every file touched, every command, in order. Assumes macOS + Node 18+.

## 0. Prereqs

```bash
# Claude Code CLI
npm install -g @anthropic-ai/claude-code
claude setup-token   # prints sk-ant-oat01-… — save it

# OpenClaw
npm install -g openclaw
openclaw onboard     # walks you through initial config

# This repo
git clone https://github.com/<fork>/openclaw-claude-max-setup.git
cd openclaw-claude-max-setup
```

## 1. One-shot install

```bash
export OAUTH_TOKEN='sk-ant-oat01-paste-yours-here'
./scripts/install.sh
```

That does everything below. If you want to understand each step, read on.

---

## 2. Manual install

### 2a. Billing proxy

```bash
git clone https://github.com/zacdcook/openclaw-billing-proxy.git ~/openclaw-billing-proxy
```

No `node setup.js` needed — we pass the OAuth token via env in the plist.

### 2b. launchd agent for the proxy

```bash
cp launchd-templates/com.example.billing-proxy.plist \
   ~/Library/LaunchAgents/com.$(id -un).billing-proxy.plist
# Edit the copy and replace {{USER}}, {{NODE_PATH}}, {{OAUTH_TOKEN}}.
chmod 600 ~/Library/LaunchAgents/com.$(id -un).billing-proxy.plist
launchctl load -w ~/Library/LaunchAgents/com.$(id -un).billing-proxy.plist
curl -s http://127.0.0.1:18801/health   # should return JSON ok
```

### 2c. Wire OpenClaw

Either run `scripts/wire-openclaw.py` (idempotent, auto-backup) or manually
merge the snippets in `openclaw/` into:

- `~/.openclaw/openclaw.json`
  - `models.providers.anthropic`  ← `openclaw/provider-snippet.json`
  - `agents.defaults`              ← `openclaw/agents-defaults-snippet.json`
  - `channels.telegram.streaming`  ← `openclaw/telegram-no-split.snippet.json`
- `~/.openclaw/agents/main/agent/auth-profiles.json`
  - `profiles.anthropic:default`   ← `openclaw/auth-profile-snippet.json`

Then:

```bash
openclaw config validate
openclaw gateway restart
```

### 2d. Verify end-to-end

```bash
# Agent answers as itself, no 'I am Claude, a large language model'
openclaw agent --local --agent main -m "Who are you?" --json | jq -r '.payloads[].text'
```

Bonus: confirm you're **not** burning API credit — the proxy health endpoint
reports `subscriptionType: "env-var"` and runs against your Max subscription.

### 2e. Optional: OpenAI-format side-route (for Hermes, Continue.dev, Cline, …)

```bash
npm install -g claude-max-api-proxy

# (Optional) Raise the hardcoded 5-min timeout that causes retry storms:
sed -i '' \
  's#const DEFAULT_TIMEOUT = 300000;#const DEFAULT_TIMEOUT = parseInt(process.env.CLAUDE_PROXY_TIMEOUT_MS || "1200000", 10);#' \
  ~/.npm-global/lib/node_modules/claude-max-api-proxy/dist/subprocess/manager.js

# Install the shim on PATH so `claude` resolves to our wrapper first
mkdir -p ~/.claude-shim
ln -sf "$(pwd)/scripts/claude-shim.py" ~/.claude-shim/claude
chmod +x scripts/claude-shim.py

# Launchd agent for the OpenAI proxy
cp launchd-templates/com.example.hermes-proxy.plist \
   ~/Library/LaunchAgents/com.$(id -un).hermes-proxy.plist
# Edit placeholders ({{USER}}, {{NODE_PATH}}, {{OAUTH_TOKEN}}, {{REPO_PATH}}).
launchctl load -w ~/Library/LaunchAgents/com.$(id -un).hermes-proxy.plist
```

Now any OpenAI client pointed at `http://127.0.0.1:3456/v1` will route through
the shim → claude CLI → your Max subscription.

---

## 3. Known-good verification checklist

- [ ] `curl http://127.0.0.1:18801/health` returns `{ "status": "ok", "subscriptionType": "env-var" }`
- [ ] `openclaw gateway health` returns `OK`
- [ ] `openclaw cron list` returns without `pairing required`
- [ ] Webchat reply matches your IDENTITY.md / SOUL.md voice
- [ ] A tool-using prompt ("run uname -sr") returns the actual output, not "I would run..."
- [ ] A long reply (5-10 sentences) arrives as **one** message, not split
- [ ] Token count in proxy health grows by ~1 per prompt (not 4)
