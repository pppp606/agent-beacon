#!/usr/bin/env python3
"""Install the Agent Beacon hooks into a Claude Code settings file.

Replaces the manual "edit settings.example.json and merge it yourself" step:
resolves this repository's absolute path, then merges the hook entries into
the target settings file (default: ~/.claude/settings.json), preserving every
unrelated hook already present.

Idempotent: any previously installed agent-beacon hook entries (including
ones pointing at an old checkout path) are replaced, so re-running after
moving the repository just fixes the paths. A .bak copy of the settings file
is written before the first change.

Usage:
  python3 integrations/claude-code/install.py            # ~/.claude/settings.json
  python3 integrations/claude-code/install.py --settings PATH
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "integrations" / "claude-code" / "attention_hook.py"

# Marker identifying entries owned by this installer (any checkout path)
HOOK_MARKER = "attention_hook.py"

# Hook events and their matchers (must mirror settings.example.json / ADR 0001)
EVENTS: dict = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": None,
    "Stop": None,
    "SessionEnd": None,
    "Notification": "idle_prompt|permission_prompt",
}


def merge_hooks(settings: dict, hook_command: str) -> dict:
    """Pure merge: returns settings with exactly one agent-beacon entry per
    event, all other hooks untouched. Running it twice is a no-op."""
    result = copy.deepcopy(settings)
    hooks = result.setdefault("hooks", {})
    for event, matcher in EVENTS.items():
        groups = hooks.setdefault(event, [])
        for group in groups:
            group["hooks"] = [h for h in group.get("hooks", [])
                              if HOOK_MARKER not in h.get("command", "")]
        groups[:] = [g for g in groups if g.get("hooks")]
        group = {"hooks": [{"type": "command", "command": hook_command,
                            "timeout": 10}]}
        if matcher is not None:
            group["matcher"] = matcher
        groups.append(group)
    return result


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings",
                        default=str(Path.home() / ".claude" / "settings.json"),
                        help="Claude Code settings file to merge into "
                             "(default: ~/.claude/settings.json)")
    args = parser.parse_args(argv)

    target = Path(args.settings).expanduser()
    if target.exists():
        try:
            settings = json.loads(target.read_text())
        except json.JSONDecodeError as e:
            print(f"{target} is not valid JSON ({e}); fix it first — "
                  "refusing to overwrite.", file=sys.stderr)
            return 1
    else:
        settings = {}

    merged = merge_hooks(settings, f"python3 {HOOK_SCRIPT}")
    if merged == settings:
        print(f"Already installed in {target}; nothing to do.")
        return 0

    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(target, backup)
        print(f"Backed up existing settings to {backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"Installed agent-beacon hooks into {target}")
    print("Hooks load at session start: restart running Claude Code "
          "sessions to activate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
