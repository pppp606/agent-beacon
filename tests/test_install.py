"""Tests for the hook installer's pure merge logic (integrations/claude-code/
install.py): every event gets exactly one agent-beacon entry, foreign hooks
survive, stale checkout paths are replaced, and the merge is idempotent."""

import install


CMD = "python3 /repo/integrations/claude-code/attention_hook.py"


def our_entries(settings, event):
    return [h for g in settings["hooks"][event] for h in g["hooks"]
            if "attention_hook.py" in h["command"]]


class TestMergeHooks:
    def test_installs_every_event_into_empty_settings(self):
        merged = install.merge_hooks({}, CMD)
        for event in install.EVENTS:
            assert [h["command"] for h in our_entries(merged, event)] == [CMD]

    def test_notification_keeps_waiting_matcher(self):
        merged = install.merge_hooks({}, CMD)
        (group,) = merged["hooks"]["Notification"]
        assert group["matcher"] == "idle_prompt|permission_prompt"

    def test_preserves_foreign_hooks(self):
        settings = {"hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "say done"}]}
        ]}, "model": "opus"}
        merged = install.merge_hooks(settings, CMD)
        commands = [h["command"] for g in merged["hooks"]["Stop"]
                    for h in g["hooks"]]
        assert "say done" in commands and CMD in commands
        assert merged["model"] == "opus"

    def test_replaces_stale_checkout_path(self):
        old = "python3 /old/place/agent-beacon/integrations/claude-code/attention_hook.py"
        settings = install.merge_hooks({}, old)
        merged = install.merge_hooks(settings, CMD)
        for event in install.EVENTS:
            assert [h["command"] for h in our_entries(merged, event)] == [CMD]

    def test_idempotent(self):
        once = install.merge_hooks({}, CMD)
        twice = install.merge_hooks(once, CMD)
        assert once == twice

    def test_does_not_mutate_input(self):
        settings = {"hooks": {"Stop": [
            {"hooks": [{"type": "command", "command": "say done"}]}
        ]}}
        install.merge_hooks(settings, CMD)
        assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == "say done"
        assert len(settings["hooks"]) == 1
