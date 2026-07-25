from arena.models import (AVOID, CAUTION, DISQUALIFIER, INFO, NO_RED_FLAGS,
                          PASS, WARNING, Finding)
from arena.scoring import verdict


def f(sev):
    return Finding(check="authorities", severity=sev, evidence="x", data={})


def test_any_disqualifier_is_avoid():
    assert verdict([f(PASS), f(WARNING), f(DISQUALIFIER)]) == AVOID


def test_two_warnings_is_caution():
    assert verdict([f(WARNING), f(WARNING), f(PASS)]) == CAUTION


def test_one_warning_is_clean():
    assert verdict([f(WARNING), f(PASS), f(INFO)]) == NO_RED_FLAGS


def test_all_pass_is_clean():
    assert verdict([f(PASS), f(PASS)]) == NO_RED_FLAGS


def test_info_never_counts_toward_verdict():
    assert verdict([f(INFO)] * 6) == NO_RED_FLAGS
