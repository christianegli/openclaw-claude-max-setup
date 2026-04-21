# Why wrapping `claude --print` doesn't work, and what does

Most Claude-Max-subscription-to-API proxies are thin wrappers around the
Claude Code CLI:

```
your tool  ──OpenAI/Anthropic API──▶  proxy  ──spawn──▶  claude --print
```

This is appealing — it reuses the already-authenticated `claude` CLI,
no OAuth flow, no token extraction, no TOS gray area. But it breaks
in three ways when you try to use it as a backend for an agent framework
(OpenClaw, OpenCode, Hermes, Aider, Cline, …).

## 1. `claude --print` is itself an agent

Claude Code has its own system prompt (coder persona, file-operation
tooling), its own tool-use loop (Bash, Read, Edit, Glob, Grep, …), and
its own judgment about when to use them. It reads your messages as
**input to that agent**, not as a pure LLM prompt.

So when the user's framework sends a `{role: "system", content: "You are
Atlas, Chief of Staff …"}`, `claude --print` sees it as part of the
user's conversation. Claude's built-in system prompt wins. The user's
persona becomes decorative text Claude may or may not notice.

## 2. Multi-assistant-message streams

When `claude --print` decides to use a tool, the stream-json output
contains **multiple `message_start` / `message_stop` pairs** — one per
internal tool-use cycle:

```
message_start
  content: "Let me check…"  tool_use: Bash(uname -sr)
message_stop              ← "end of turn" from Claude's POV
<tool runs internally>
message_start             ← next turn starts
  content: "Darwin 25.4.0"
message_stop
```

Proxies that forward the stream verbatim emit a stream that **is not
valid Anthropic Messages API** (which specifies exactly one assistant
message per request). Frameworks parsing that stream see a second
`message_start` mid-response and abort with
`"Unexpected event order, got message_start before receiving message_stop"`.

You can bolt on `--disallowedTools "*"` to prevent tools, but then
Claude often emits *two* messages anyway (one "I'd like to use Bash",
one "… but I can't, so here's text"). Same bug.

## 3. HTTP-layer timeouts trigger retry storms

`claude-max-api-proxy` hardcodes a 300000ms (5-min) subprocess cap. Any
tool chain that runs over 5min gets killed at the HTTP layer. OpenClaw
(or any upstream) sees "LLM failed", retries the *same* prompt,
spawning another full claude subprocess (with the same 30K+ system
prompt).

We measured: one long question → four retries → five claude processes
running in parallel → five slightly different answers emitted to the
channel 1s apart → massive token burn on a "free" subscription.

Raising the timeout helps. Disabling retries helps. But the underlying
mismatch is still there.

---

## What works instead: talk to `api.anthropic.com` directly

A proper proxy:
- Reads the OAuth token from `~/.claude/.credentials.json` (or env).
- Makes direct `POST /v1/messages` HTTPS calls to `api.anthropic.com`.
- Injects the Claude Code billing identifier into headers so requests
  bill against the subscription instead of Extra Usage.
- Passes the user's `tools`, `system`, and `messages` through **as-is**.
- Returns Anthropic's native response — a single message, properly
  structured `tool_use` blocks, correct streaming.

[`zacdcook/openclaw-billing-proxy`](https://github.com/zacdcook/openclaw-billing-proxy)
is the one we use. It also rewrites tool names (`exec` → `Bash`,
`write` → `Write`, etc.) in the outbound request so Claude's safety
heuristics don't trigger on OpenClaw-specific names, then reverses the
rename on the way back so OpenClaw sees its own names.

**Trade-off:** you still depend on the OAuth token extracted from
Claude Code's credentials. Anthropic can revoke this at any time (they
did once in April 2026 and broke most community proxies). Keep the
OpenAI-format shim route in this repo as a fallback — it's slower and
less capable, but uses `claude --print` which is the officially
supported automation path.
