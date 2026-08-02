"""Sound + notification via macOS built-ins. No dependency, and it reaches the
user when Coin Arena is behind the trading terminal — which is the normal case.

Neither channel may ever raise: an alert failure must not kill a watch."""

import logging
import subprocess

log = logging.getLogger(__name__)

SOUND_PATH = "/System/Library/Sounds/Glass.aiff"


def fire_alert(title: str, body: str, runner=subprocess.run) -> None:
    try:
        runner(["afplay", SOUND_PATH], check=False, timeout=5)
    except Exception as exc:
        log.warning("alert sound failed: %s", exc)
    safe_title = title.replace('"', '\\"')
    safe_body = body.replace('"', '\\"')
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    try:
        runner(["osascript", "-e", script], check=False, timeout=5)
    except Exception as exc:
        log.warning("alert notification failed: %s", exc)
