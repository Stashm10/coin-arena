import math

from arena.checks.entropy import describe, funding_entropy


def test_none_below_two_buyers():
    assert funding_entropy({"a": "r1"}) is None
    assert funding_entropy({}) is None


def test_fully_independent_buyers_give_maximum_entropy():
    roots = {f"b{i}": f"r{i}" for i in range(10)}
    r = funding_entropy(roots)
    assert abs(r.h - math.log(10)) < 1e-9
    assert abs(r.h_norm - 1.0) < 1e-9
    assert r.n_roots == 10


def test_single_source_gives_zero_entropy():
    roots = {f"b{i}": "whale" for i in range(20)}
    r = funding_entropy(roots)
    assert abs(r.h) < 1e-9
    assert abs(r.h_norm) < 1e-9
    assert r.largest_root == "whale"
    assert abs(r.largest_share - 1.0) < 1e-9


def test_mixed_case_lands_between():
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(15)}
    r = funding_entropy(roots)
    assert 0.0 < r.h_norm < 1.0
    assert r.largest_root == "whale"
    assert abs(r.largest_share - 12 / 15) < 1e-9
    assert r.n_buyers == 15


def test_describe_states_the_dominant_cluster():
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(15)}
    text = describe(funding_entropy(roots))
    assert "12 of 15" in text
    assert "0.2" in text or "0.3" in text  # normalised entropy is shown


def test_describe_for_independent_buyers():
    text = describe(funding_entropy({f"b{i}": f"r{i}" for i in range(6)}))
    assert "6 distinct" in text


def test_describe_is_honest_about_truncated_sampling_dominant_cluster():
    # Only 20 of the coin's 45 launch buyers were traced (FUNDING_GRAPH_MAX_
    # BUYERS truncation) -- the sentence must not imply the full 45 were seen.
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(20)}
    text = describe(funding_entropy(roots), total_launch_buyers=45)
    assert "20" in text and "45" in text
    assert "12" in text


def test_describe_is_honest_about_truncated_sampling_independent_buyers():
    roots = {f"b{i}": f"r{i}" for i in range(20)}
    text = describe(funding_entropy(roots), total_launch_buyers=45)
    assert "20" in text and "45" in text


def test_describe_unchanged_when_total_equals_traced():
    # No truncation happened (total == traced): wording matches the
    # no-argument call exactly.
    roots = {f"b{i}": ("whale" if i < 12 else f"r{i}") for i in range(15)}
    result = funding_entropy(roots)
    assert describe(result, total_launch_buyers=15) == describe(result)
