#!/usr/bin/env python3
"""
claude-shim — compatibility shim in front of the `claude` CLI.

WHY THIS EXISTS
---------------
Some third-party proxies (e.g. claude-max-api-proxy) translate OpenAI
ChatCompletions to Claude CLI invocations by flattening all messages into one
prompt, wrapping system messages in `<system>...</system>` tags. Claude reads
those as *prose*, not as a system prompt, so persona/identity bleeds.

This shim, placed on PATH as `claude`, intercepts every invocation and:

  1. Extracts every `<system>…</system>` block from the last prompt argv,
     concatenates them, writes to a temp file, and adds
     `--system-prompt-file <tmp>` so Claude treats it as an actual system
     prompt (full persona override).
  2. Injects `--max-turns N` (env-configurable) so internal tool-use loops
     don't exceed upstream proxy HTTP timeouts.

Then execs the real `claude` with the rewritten args. Invisible to the
proxy, to Claude, and to any other flags the proxy happens to pass.

INSTALL
-------
    mkdir -p ~/.claude-shim
    ln -sf /path/to/claude-shim.py ~/.claude-shim/claude
    # put ~/.claude-shim first in PATH for any process that should use it

ENV
---
    CLAUDE_SHIM_REAL        absolute path to real claude binary
                            default: $(which claude) fallback to common locations
    CLAUDE_SHIM_MAX_TURNS   integer; 0 disables the --max-turns injection
                            default: 8
"""
import os
import re
import shutil
import sys
import tempfile

SYS_RE = re.compile(r"<system>\s*(.*?)\s*</system>\s*", re.DOTALL)


def locate_real_claude() -> str:
    explicit = os.environ.get("CLAUDE_SHIM_REAL")
    if explicit and os.path.exists(explicit):
        return explicit
    # Avoid recursion: the shim is probably earlier on PATH as `claude`.
    # Search common install locations directly.
    candidates = [
        os.path.expanduser("~/.npm-global/bin/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        "/usr/bin/claude",
    ]
    for p in candidates:
        if os.path.exists(p) and not os.path.samefile(p, __file__):
            return p
    # Last resort: strip our shim dir from PATH and ask which().
    shim_dir = os.path.dirname(os.path.abspath(__file__))
    cleaned = ":".join(
        p for p in os.environ.get("PATH", "").split(":") if p and p != shim_dir
    )
    found = shutil.which("claude", path=cleaned)
    if found:
        return found
    sys.stderr.write(
        "[claude-shim] real `claude` binary not found. "
        "Set CLAUDE_SHIM_REAL or install claude-code via npm.\n"
    )
    sys.exit(127)


def main() -> None:
    real = locate_real_claude()
    max_turns = int(os.environ.get("CLAUDE_SHIM_MAX_TURNS", "8") or "0")

    argv = list(sys.argv[1:])

    # Locate the prompt positional — last non-flag arg after `--print` if
    # present; otherwise last non-flag arg in the list.
    try:
        p_idx = argv.index("--print")
    except ValueError:
        p_idx = -1

    prompt_idx = None
    for i in range(len(argv) - 1, max(p_idx, -1), -1):
        if not argv[i].startswith("-"):
            prompt_idx = i
            break

    extra = []

    if max_turns > 0 and not any(
        a == "--max-turns" or a.startswith("--max-turns=") for a in argv
    ):
        extra.extend(["--max-turns", str(max_turns)])

    if prompt_idx is not None:
        prompt = argv[prompt_idx]
        systems = SYS_RE.findall(prompt)
        if systems:
            sys_text = "\n\n".join(s.strip() for s in systems if s.strip())
            cleaned = SYS_RE.sub("", prompt).strip()

            tf = tempfile.NamedTemporaryFile(
                prefix="claude-sysprompt-",
                suffix=".md",
                delete=False,
                mode="w",
                encoding="utf-8",
            )
            tf.write(sys_text)
            tf.close()

            argv[prompt_idx] = cleaned
            extra = ["--system-prompt-file", tf.name] + extra

    # Splice just before the prompt so flags unambiguously apply to it.
    if prompt_idx is not None:
        new_argv = argv[:prompt_idx] + extra + argv[prompt_idx:]
    else:
        new_argv = extra + argv

    os.execv(real, [real] + new_argv)


if __name__ == "__main__":
    main()
