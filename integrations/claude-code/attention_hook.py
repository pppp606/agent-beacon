#!/usr/bin/env python3
"""Claude Code hooks → Agent Beacon bridge.

Claude Code invokes this script with a hook event JSON on stdin (see
settings.example.json). It tracks each session's state as a file under the
state dir, derives "is any session waiting for a human?", and converges the
beacon LED to that (on/off).

The hook itself only touches local files and exits immediately; the BLE write
happens in a detached `--sync` process, so hooks never slow Claude Code down.
The desired/applied pair guarantees the beacon converges to the latest
aggregate even when events race.

State dir (default ~/.local/state/agent-beacon):
  sessions/<session_id>   "waiting" | "working"
  desired                 "on" | "off" — aggregate we want on the beacon
  applied                 last state successfully written to the beacon
  state.lock, sync.lock   advisory locks
  hook.log                one line per handled event / sync action

Pure logic (classify/apply/aggregate/plan) is side-effect free for TDD
(docs/adr/0003-test-strategy.md).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

WAITING = "waiting"
WORKING = "working"
ENDED = "ended"

WAITING_NOTIFICATIONS = {"idle_prompt", "permission_prompt"}

REPO_ROOT = Path(__file__).resolve().parents[2]
BEACONCTL = REPO_ROOT / "cli" / "beaconctl.py"


# ---------- pure logic ----------

def classify_event(payload: dict) -> str | None:
    """Map a hook event to a session transition, or None to ignore.

    State model (ADR 0001): an agent is either working autonomously (LED off)
    or stopped, waiting for its human (LED on). Stop and the waiting
    notifications mean waiting; prompt submission, tool execution and session
    start mean the agent is working again; SessionEnd drops the session.
    """
    event = payload.get("hook_event_name")
    if event == "Stop":
        return WAITING
    if event == "Notification":
        if payload.get("notification_type") in WAITING_NOTIFICATIONS:
            return WAITING
        return None
    if event in ("UserPromptSubmit", "PreToolUse", "SessionStart"):
        return WORKING
    if event == "SessionEnd":
        return ENDED
    return None


def apply_transition(sessions: dict, session_id: str, transition: str) -> dict:
    result = dict(sessions)
    if transition == ENDED:
        result.pop(session_id, None)
    else:
        result[session_id] = transition
    return result


def any_waiting(sessions: dict) -> bool:
    return WAITING in sessions.values()


def desired_state(sessions: dict) -> str:
    return "on" if any_waiting(sessions) else "off"


def plan_action(applied: str | None, desired: str) -> str | None:
    """The beaconctl subcommand to run, or None if already converged."""
    return None if applied == desired else desired


def safe_session_id(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", session_id)[:128] or "unknown"


# ---------- state dir I/O ----------

def state_dir() -> Path:
    return Path(os.environ.get(
        "AGENT_BEACON_STATE_DIR",
        str(Path.home() / ".local" / "state" / "agent-beacon")))


@contextmanager
def locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_value(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return None


def read_sessions(d: Path) -> dict:
    sessions_dir = d / "sessions"
    if not sessions_dir.is_dir():
        return {}
    return {p.name: p.read_text().strip() for p in sessions_dir.iterdir() if p.is_file()}


def log(d: Path, message: str) -> None:
    try:
        d.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(d / "hook.log", "a") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


def handle_event(d: Path, payload: dict) -> str | None:
    """Update session state from one hook event; returns the new desired
    aggregate ("on"/"off"), or None if the event was ignored."""
    transition = classify_event(payload)
    if transition is None:
        return None
    session_id = safe_session_id(str(payload.get("session_id") or "unknown"))
    with locked(d / "state.lock"):
        session_file = d / "sessions" / session_id
        if transition == ENDED:
            try:
                session_file.unlink()
            except FileNotFoundError:
                pass
        else:
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(transition)
        if transition == WAITING:
            # Force a rewrite even when the beacon is already "on": the BLE
            # write refreshes the beacon's display-timeout clocks, so a
            # display dismissed by tap or timeout re-lights for every new
            # wait (docs/protocol.md). Also heals drift after a beacon
            # power-cycle or a manual `beaconctl off`.
            try:
                (d / "applied").unlink()
            except FileNotFoundError:
                pass
        desired = desired_state(read_sessions(d))
        (d / "desired").write_text(desired)
    log(d, f"{payload.get('hook_event_name')} session={session_id} "
           f"-> {transition}, desired={desired}")
    return desired


# ---------- beacon sync (detached) ----------

def run_beaconctl(d: Path, action: str) -> bool:
    override = os.environ.get("AGENT_BEACON_CTL")
    if override:
        cmd = [override, action]
    else:
        cmd = ["uv", "run", str(BEACONCTL), action]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(d, f"beaconctl {action} failed to run: {e}")
        return False
    if result.returncode != 0:
        log(d, f"beaconctl {action} failed: {result.stderr.strip()}")
        return False
    return True


def _sync_holding_lock(d: Path) -> None:
    while True:
        desired = read_value(d / "desired")
        applied = read_value(d / "applied")
        action = plan_action(applied, desired) if desired else None
        if action is None:
            return
        if not run_beaconctl(d, action):
            return  # keep `applied` stale; the next event retries
        (d / "applied").write_text(action)
        log(d, f"beacon -> {action}")


def sync(d: Path) -> None:
    """Converge the beacon to the desired state. Only one syncer runs at a
    time; late writers re-check after the lock is released so a desired
    change during release is not lost."""
    d.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        with open(d / "sync.lock", "w") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return  # the running syncer will pick up our change
            try:
                _sync_holding_lock(d)
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        desired = read_value(d / "desired")
        if desired is None or desired == read_value(d / "applied"):
            return


def spawn_syncer() -> None:
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--sync"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ---------- entry point ----------

def main(argv: list) -> int:
    d = state_dir()
    if "--sync" in argv:
        sync(d)
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0  # never break Claude Code on malformed input
    desired = handle_event(d, payload)
    if desired is not None and desired != read_value(d / "applied"):
        spawn_syncer()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
