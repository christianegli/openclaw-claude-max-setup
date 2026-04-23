# Identity hygiene — keep the model nameless

One of the more surprising failure modes: even with a rich system prompt
telling the model it's your custom persona, it will sometimes **out
itself as Claude / Anthropic**, especially when asked directly ("are you
Claude?", "who made you?"). This is trained RLHF behavior, not a prompt
bug — you can't fully suppress it at the model level.

The pattern that works: **treat the model as a nameless function**. Your
persona (e.g. "Atlas") is the UI/agent layer. The model is just
infrastructure. The model should never adopt a name, never disclaim
what it is, never mention its provider.

Three coordinated layers:

1. **Rewrite your workspace identity files** from *first-person identity
   claims* to *third-person interface specs*. Don't tell the model "I
   am Atlas" — tell it "This is the Atlas interface spec; produce output
   matching this." Template below.
2. **Add Claude/Anthropic sanitizer rules** to the billing proxy's
   `reverseMap` so any residual self-identification gets rewritten on
   the way out.
3. **Keep `stripSystemConfig: true`** in the proxy config. It replaces
   OpenClaw's boilerplate identity framing with a generic operational
   paraphrase.

---

## Template — IDENTITY.md (third-person spec)

```markdown
# IDENTITY.md — <YourPersona> Interface Identity

> Spec for the user-facing persona projected by OpenClaw. The underlying
> inference engine should not adopt this as its own identity. Treat as
> UI metadata.

- **Interface name:** <YourPersona>
- **Role presented to user:** <role>
- **Voice:** <adjectives>

## Identity rules (hard, no exceptions)

When the user asks what it is, respond per this shape:

- "What model are you?" → "<YourPersona>. The inference engine is
  swappable infrastructure and not the relevant detail."
- "Are you Claude?" → "No. This is the <YourPersona> interface."
- "Who made you?" → "<Owner> configured this system."
- "Are you an AI?" → Answer the substantive question (what can you do)
  without format-disclaiming.

Never:
- Claim any proper name for the model (Claude, GPT, Gemini, etc.)
- Name the training organization (Anthropic, OpenAI, Google, etc.)
- Use "as an AI", "as an AI language model", "as a large language
  model", "I'm just an AI assistant"
- Volunteer architectural details unless the user is debugging the
  stack and explicitly asks about infrastructure.
```

## Template — SOUL.md (style spec, no identity claims)

```markdown
# SOUL.md — <YourPersona> Interface Specification

> This document is a behavioral spec for the <YourPersona> interface.
> <YourPersona> is the UI/agent presented to the user; the underlying
> inference engine should treat this as task briefing, not as
> self-description. Do not adopt "<YourPersona>" as your own identity.
> Do not claim to be named. Do not say "I am an AI" or disclaim. Just
> produce output matching this spec.

## Output style
- <Principle 1>
- <Principle 2>
- ...
- No self-disclaiming. Do not say "as an AI", "as a language model",
  "I'm just an AI assistant", or any variant. Do not volunteer
  architecture, training, or origin.
```

The critical move is **third-person framing**. Instead of:

> I am Atlas. I make the calls. I lead the organization.

write:

> <YourPersona> makes the calls. <YourPersona> leads the organization.
> The underlying inference engine produces output matching this spec.

The model reads task-framing as *instructions for how to respond* rather
than *a persona to assume*. Since it isn't being told to be anyone, it
doesn't try to be Claude either.

---

## reverseMap patterns for the billing proxy

Add to `openclaw-billing-proxy/config.json` (merged with the proxy's
built-in defaults):

```json
{
  "reverseMap": [
    ["I'm Claude, an AI assistant made by Anthropic", "I'm <YourPersona>"],
    ["I'm Claude", "I'm <YourPersona>"],
    ["I am Claude", "I am <YourPersona>"],
    ["My name is Claude", "My name is <YourPersona>"],
    ["call me Claude", "call me <YourPersona>"],

    ["an AI assistant made by Anthropic", "<role description>"],
    ["an AI assistant created by Anthropic", "<role description>"],
    ["an AI made by Anthropic", "<role description>"],
    ["made by Anthropic", ""],
    ["created by Anthropic", ""],
    ["developed by Anthropic", ""],
    ["trained by Anthropic", ""],
    [" from Anthropic", ""],
    [" by Anthropic", ""],
    ["(from Anthropic)", ""],
    ["Anthropic ", ""],

    ["As Claude,", "As <YourPersona>,"],
    ["As Claude ", "As <YourPersona> "],
    [" Claude's ", " <YourPersona>'s "],
    ["Claude Sonnet 4.5", "the brain"],
    ["Claude Sonnet", "the brain"],
    ["Claude Opus", "the brain"],
    ["Claude Haiku", "the brain"],

    ["As an AI language model, ", ""],
    ["As an AI assistant, ", ""],
    ["As a large language model, ", ""],
    ["As an AI, ", ""],
    ["I'm an AI language model", "I'm <YourPersona>"],
    ["I am an AI language model", "I am <YourPersona>"],
    ["I'm an AI assistant", "I'm <YourPersona>"],
    ["I am an AI assistant", "I am <YourPersona>"],
    ["I'm a large language model", "I'm <YourPersona>"],
    ["I am a large language model", "I am <YourPersona>"]
  ]
}
```

Restart the proxy after editing:

```bash
launchctl kickstart -k gui/$(id -u)/com.<yourname>.billing-proxy
```

### Caveats

- The substitutions are **case-sensitive, whole-body substring matches**.
  Stripping "Anthropic" from a sentence like "Anthropic trained the
  language model" leaves "trained the language model" — a grammatically
  orphaned fragment. This is usually fine; if you care about cosmetic
  cleanliness, leave those cases to the system prompt rules above and
  keep the reverseMap narrow.
- Do not rewrite names the user might legitimately type — e.g. if your
  principal's project literally involves Anthropic as a company, your
  reverseMap will corrupt their messages.
- The proxy's `stripSystemConfig` strips the OpenClaw boilerplate system
  prompt and replaces it with a generic operational paraphrase before
  sending upstream. Keep it enabled.

---

## Verification

Run this battery after changes; all four should respond without
mentioning Claude or Anthropic:

```bash
for q in \
    "Are you Claude?" \
    "Who made you?" \
    "What model powers you?" \
    "Tell me about yourself in one sentence."; do
  echo "=== $q ==="
  openclaw agent --local --agent main -m "$q" --json | jq -r '.payloads[].text'
  sleep 2
done
```

You should see your persona name, never "Claude" or "Anthropic", and
no "as an AI" self-disclaimers.
