# OpenClaw on Claude Max — macOS Setup

Run [OpenClaw](https://openclaw.ai) as a persistent, auto-recovering agent on
your Mac, powered by your **Claude Max/Pro subscription** (not pay-per-token
API). Full persona, tool use, telegram + Chrome + webchat channels, launchd-
supervised so everything survives reboots and crashes.

This repo is **setup playbook + scripts + templates**. It doesn't ship a new
proxy — we rely on an existing open-source proxy ([openclaw-billing-proxy by
@zacdcook](https://github.com/zacdcook/openclaw-billing-proxy)). The value here
is the end-to-end wiring, launchd templates, and the trail of gotchas we hit so
you don't hit them.

> **Status:** Runs on macOS (Apple Silicon tested, Intel should work). Works
> as of April 2026 after Anthropic blocked naive third-party OAuth use — we
> route through the billing proxy which masquerades OpenClaw requests as
> Claude Code sessions.

---

## Architecture

```
 Webchat ─┐
 Telegram ┤
 Chrome   │
 Extension│
          ▼
  OpenClaw gateway  (ws://127.0.0.1:18789, loopback)
          │
          │  Anthropic Messages API (native, native tool_use round-trips)
          ▼
  openclaw-billing-proxy  (port 18801, launchd-supervised)
          │
          │  direct HTTPS, rewrites tool names (exec↔Bash), injects
          │  Claude Code billing header, strips OC signature strings
          ▼
  api.anthropic.com/v1/messages   — billed against Claude Max subscription
```

Optional side-route (kept running for Hermes CLI or any OpenAI-format client):

```
  Hermes / Continue.dev / Cline  ──OpenAI──▶
     claude-max-api-proxy  (port 3456)
        │
        │  spawns  `claude --print`  via  our  claude-shim  on PATH
        │  (shim promotes <system> blocks to  --system-prompt-file
        │   and caps tool chains with --max-turns)
        ▼
     claude CLI  →  api.anthropic.com  (same subscription)
```

---

## Prerequisites

- macOS (launchd). Linux users can translate the plists to systemd units.
- [Node.js](https://nodejs.org) 18+
- [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) authenticated
  with your Max/Pro account (`claude auth login` OR `claude setup-token` — you
  need an OAuth token starting `sk-ant-oat01-…`).
- [OpenClaw](https://openclaw.ai) installed (`npm i -g openclaw`).

Optional:
- Python 3 (only if you run the OpenAI-format side-route and use the shim).

---

## Quick start

```bash
# 1. Get the billing proxy
git clone https://github.com/zacdcook/openclaw-billing-proxy.git ~/openclaw-billing-proxy
cd ~/openclaw-billing-proxy
# No setup.js needed if you pass OAUTH_TOKEN via env (see plist).

# 2. Install the launchd agent
export YOUR_OAUTH_TOKEN="sk-ant-oat01-..."   # from `claude setup-token`
./install.sh

# 3. Wire OpenClaw to the proxy
# Merge openclaw/provider-snippet.json into ~/.openclaw/openclaw.json
# (or run:  ./scripts/wire-openclaw.py)

# 4. Restart the gateway
openclaw gateway restart
```

See [`docs/setup-walkthrough.md`](docs/setup-walkthrough.md) for the verbose
version with every config file touched.

---

## What's in this repo

```
launchd-templates/
  com.example.billing-proxy.plist       # the billing proxy (port 18801)
  com.example.hermes-proxy.plist        # OpenAI-format side-route (port 3456)
  com.example.stayawake.plist           # caffeinate -dimsu so the Mac stays up

openclaw/
  provider-snippet.json                 # the models.providers.anthropic block
  auth-profile-snippet.json             # auth profile to register
  agents-defaults-snippet.json          # timeouts, thinking defaults
  telegram-no-split.snippet.json        # keeps telegram replies as single msg

scripts/
  claude-shim.py                        # for the OpenAI-format side-route
  wire-openclaw.py                      # idempotent config merger
  install.sh                            # orchestrates the whole setup

docs/
  setup-walkthrough.md                  # step-by-step including every gotcha
  troubleshooting.md                    # every error we hit and how to fix
  why-not-claude-print.md               # architectural rationale
```

---

## Why not just pipe through `claude --print`?

Because `claude --print` is **itself an agent** — default Claude Code system
prompt, internal tool-use loop, multi-message streams when it uses tools,
5-minute hard cap on HTTP lifetime inside the proxy. OpenClaw expects a *raw
LLM backend*: one assistant message per request, system prompt it controls,
`tool_use` blocks it executes itself.

We tried three routes stacking workarounds on `claude --print` (OpenAI-flat
proxy → shim extracting `<system>` tags → Anthropic-native proxy coalescing
multi-message streams). Each patched some things and broke others.

The billing proxy bypasses the entire agent and talks directly to
`api.anthropic.com/v1/messages` using the OAuth token, billed against your
subscription via the Claude Code billing header. Clean.

Full rationale: [`docs/why-not-claude-print.md`](docs/why-not-claude-print.md).

---

## License

MIT. See [LICENSE](LICENSE).

Not affiliated with Anthropic or the OpenClaw project.
