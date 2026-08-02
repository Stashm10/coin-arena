from arena.stream.tape import Tape, TapeEvent
from arena.thresholds import QME_FIT_WINDOW_EVENTS, QME_FIT_WINDOW_SECONDS


def _ev(ts, price=1.0, is_buy=True, sol=0.1):
    return TapeEvent(ts=ts, is_buy=is_buy, sol=sol, price=price)


def test_ring_buffer_drops_oldest_beyond_maxlen():
    tape = Tape(maxlen=10)
    for i in range(25):
        tape.append(_ev(float(i)))
    assert len(tape) == 10
    assert tape.window_times(now=24.0)[0] == 15.0


def test_window_excludes_events_older_than_the_time_window():
    tape = Tape()
    tape.append(_ev(0.0))
    tape.append(_ev(QME_FIT_WINDOW_SECONDS + 50.0))
    times = tape.window_times(now=QME_FIT_WINDOW_SECONDS + 50.0)
    assert times == [QME_FIT_WINDOW_SECONDS + 50.0]


def test_window_caps_at_event_limit():
    tape = Tape(maxlen=5000)
    for i in range(QME_FIT_WINDOW_EVENTS + 100):
        tape.append(_ev(i * 0.01))
    now = (QME_FIT_WINDOW_EVENTS + 99) * 0.01
    assert len(tape.window_times(now)) == QME_FIT_WINDOW_EVENTS


def test_window_prices_drops_none_prices():
    tape = Tape()
    tape.append(_ev(0.0, price=None))
    tape.append(_ev(1.0, price=2.0))
    assert tape.window_prices(now=1.0) == [(1.0, 2.0)]


def test_window_times_are_ascending():
    tape = Tape()
    for i in range(50):
        tape.append(_ev(float(i)))
    times = tape.window_times(now=49.0)
    assert times == sorted(times)


def test_buy_share_reports_fraction_of_buys():
    tape = Tape()
    for i in range(4):
        tape.append(_ev(float(i), is_buy=i < 3))
    assert abs(tape.buy_share(now=3.0) - 0.75) < 1e-9


def test_buy_share_none_when_empty():
    assert Tape().buy_share(now=0.0) is None


def test_clear_empties_the_tape():
    tape = Tape()
    tape.append(_ev(0.0))
    tape.clear()
    assert len(tape) == 0
