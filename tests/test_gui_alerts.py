from arena.gui.alerts import fire_alert


class FakeRunner:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self.fail_on and self.fail_on in args[0]:
            raise OSError("not found")
        return None


def test_plays_sound_and_posts_notification():
    runner = FakeRunner()
    fire_alert("EXIT", "cascade decay", runner=runner)
    commands = [c[0] for c in runner.calls]
    assert "afplay" in commands
    assert "osascript" in commands


def test_notification_carries_title_and_body():
    runner = FakeRunner()
    fire_alert("EXIT SIGNAL", "cascade decay", runner=runner)
    script = [c for c in runner.calls if c[0] == "osascript"][0][-1]
    assert "EXIT SIGNAL" in script
    assert "cascade decay" in script


def test_quotes_in_body_are_escaped():
    runner = FakeRunner()
    fire_alert("EXIT", 'he said "sell"', runner=runner)
    script = [c for c in runner.calls if c[0] == "osascript"][0][-1]
    assert '\\"sell\\"' in script


def test_sound_failure_does_not_block_notification():
    runner = FakeRunner(fail_on="afplay")
    fire_alert("EXIT", "reason", runner=runner)
    assert any(c[0] == "osascript" for c in runner.calls)


def test_notification_failure_is_swallowed():
    runner = FakeRunner(fail_on="osascript")
    fire_alert("EXIT", "reason", runner=runner)  # must not raise
