"""Tests for the Claude Code hook → beacon bridge.

Pure logic (classify/apply/aggregate) is tested directly; the full
event → state files → sync → beaconctl flow is tested against a fake
beaconctl script that records its calls. No BLE involved."""

import pytest

import attention_hook as ah


def event(name, sid="s1", **extra):
    return {"hook_event_name": name, "session_id": sid, **extra}


class TestClassifyEvent:
    def test_stop_means_waiting(self):
        assert ah.classify_event(event("Stop")) == ah.WAITING

    @pytest.mark.parametrize("ntype", ["idle_prompt", "permission_prompt"])
    def test_waiting_notifications(self, ntype):
        e = event("Notification", notification_type=ntype)
        assert ah.classify_event(e) == ah.WAITING

    def test_other_notifications_are_ignored(self):
        e = event("Notification", notification_type="auth_success")
        assert ah.classify_event(e) is None
        assert ah.classify_event(event("Notification")) is None

    @pytest.mark.parametrize("name", ["UserPromptSubmit", "PreToolUse", "SessionStart"])
    def test_working_events(self, name):
        assert ah.classify_event(event(name)) == ah.WORKING

    def test_session_end(self):
        assert ah.classify_event(event("SessionEnd")) == ah.ENDED

    def test_unknown_events_are_ignored(self):
        assert ah.classify_event(event("PostToolUse")) is None
        assert ah.classify_event({}) is None


class TestAggregation:
    def test_apply_transition_adds_and_updates(self):
        s = ah.apply_transition({}, "a", ah.WAITING)
        assert s == {"a": ah.WAITING}
        s = ah.apply_transition(s, "a", ah.WORKING)
        assert s == {"a": ah.WORKING}

    def test_ended_removes_session(self):
        s = ah.apply_transition({"a": ah.WAITING}, "a", ah.ENDED)
        assert s == {}
        assert ah.apply_transition({}, "ghost", ah.ENDED) == {}

    def test_any_waiting_is_or_over_sessions(self):
        assert not ah.any_waiting({})
        assert not ah.any_waiting({"a": ah.WORKING})
        assert ah.any_waiting({"a": ah.WORKING, "b": ah.WAITING})

    def test_plan_action_only_on_change(self):
        assert ah.plan_action(None, "on") == "on"
        assert ah.plan_action("on", "on") is None
        assert ah.plan_action("on", "off") == "off"

    def test_safe_session_id(self):
        assert ah.safe_session_id("abc-123_X.y") == "abc-123_X.y"
        assert "/" not in ah.safe_session_id("../../etc/passwd")
        assert ah.safe_session_id("") == "unknown"


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("AGENT_BEACON_STATE_DIR", str(d))
    return d


@pytest.fixture
def ctl_calls(tmp_path, monkeypatch):
    """Fake beaconctl: records each invocation's first argument."""
    calls = tmp_path / "calls.txt"
    script = tmp_path / "fakectl"
    script.write_text(f'#!/bin/sh\necho "$1" >> "{calls}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("AGENT_BEACON_CTL", str(script))
    return calls


def drive(state_dir, payload):
    """One hook invocation followed by its (normally detached) sync."""
    ah.handle_event(state_dir, payload)
    ah.sync(state_dir)


def calls_of(ctl_calls):
    return ctl_calls.read_text().split() if ctl_calls.exists() else []


class TestEndToEndFlow:
    def test_stop_turns_beacon_on(self, state_dir, ctl_calls):
        drive(state_dir, event("Stop"))
        assert calls_of(ctl_calls) == ["on"]

    def test_prompt_turns_beacon_off_again(self, state_dir, ctl_calls):
        drive(state_dir, event("Stop"))
        drive(state_dir, event("UserPromptSubmit"))
        assert calls_of(ctl_calls) == ["on", "off"]

    def test_converged_state_writes_nothing(self, state_dir, ctl_calls):
        drive(state_dir, event("Stop", sid="a"))
        drive(state_dir, event("Stop", sid="b"))
        drive(state_dir, event("Notification", sid="a",
                               notification_type="idle_prompt"))
        assert calls_of(ctl_calls) == ["on"]

    def test_beacon_stays_on_until_every_session_is_answered(self, state_dir, ctl_calls):
        drive(state_dir, event("Stop", sid="a"))
        drive(state_dir, event("Stop", sid="b"))
        drive(state_dir, event("UserPromptSubmit", sid="a"))
        assert calls_of(ctl_calls) == ["on"], "b is still waiting"
        drive(state_dir, event("UserPromptSubmit", sid="b"))
        assert calls_of(ctl_calls) == ["on", "off"]

    def test_permission_prompt_then_tool_resume(self, state_dir, ctl_calls):
        # The very first event finds `applied` unknown (the beacon could be
        # stale-on after a crash), so the syncer first converges it to off.
        drive(state_dir, event("SessionStart"))
        assert calls_of(ctl_calls) == ["off"]
        drive(state_dir, event("Notification",
                               notification_type="permission_prompt"))
        assert calls_of(ctl_calls) == ["off", "on"]
        drive(state_dir, event("PreToolUse"))
        assert calls_of(ctl_calls) == ["off", "on", "off"]

    def test_session_end_releases_its_wait(self, state_dir, ctl_calls):
        drive(state_dir, event("Stop", sid="a"))
        drive(state_dir, event("SessionEnd", sid="a"))
        assert calls_of(ctl_calls) == ["on", "off"]

    def test_ignored_events_touch_nothing(self, state_dir, ctl_calls):
        drive(state_dir, event("PostToolUse"))
        drive(state_dir, event("Notification", notification_type="auth_success"))
        assert calls_of(ctl_calls) == []
        assert not (state_dir / "desired").exists()

    def test_failed_ble_write_is_retried_on_next_event(self, state_dir, ctl_calls,
                                                       tmp_path, monkeypatch):
        failing = tmp_path / "failctl"
        failing.write_text("#!/bin/sh\nexit 1\n")
        failing.chmod(0o755)
        monkeypatch.setenv("AGENT_BEACON_CTL", str(failing))
        drive(state_dir, event("Stop"))
        assert ah.read_value(state_dir / "applied") is None, \
            "applied must only record successful writes"
        monkeypatch.setenv("AGENT_BEACON_CTL",
                           str(ctl_calls.parent / "fakectl"))
        drive(state_dir, event("Notification",
                               notification_type="idle_prompt"))
        assert calls_of(ctl_calls) == ["on"]
