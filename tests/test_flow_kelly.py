from arena.flow.kelly import KellyInputs, solve_kelly


def _inputs(**kw):
    base = dict(hit_rate=0.10, winner_multiple=5.0, tail_index=1.8,
                max_drawdown=0.50, ruin_tolerance=0.05, trials=300,
                trades_per_path=150, seed=99)
    base.update(kw)
    return KellyInputs(**base)


def test_is_deterministic_for_a_seed():
    a, b = solve_kelly(_inputs()), solve_kelly(_inputs())
    assert a.f_star == b.f_star
    assert a.f_constrained == b.f_constrained


def test_fractions_are_within_unit_interval():
    r = solve_kelly(_inputs())
    assert 0.0 <= r.f_constrained <= r.f_star <= 1.0


def test_higher_hit_rate_allows_larger_bets():
    low = solve_kelly(_inputs(hit_rate=0.05))
    high = solve_kelly(_inputs(hit_rate=0.25))
    assert high.f_star >= low.f_star


def test_hopeless_edge_sizes_to_zero():
    r = solve_kelly(_inputs(hit_rate=0.01, winner_multiple=1.2))
    assert r.f_star == 0.0


def test_drawdown_constraint_binds():
    loose = solve_kelly(_inputs(max_drawdown=0.95, ruin_tolerance=0.50))
    tight = solve_kelly(_inputs(max_drawdown=0.10, ruin_tolerance=0.01))
    assert tight.f_constrained <= loose.f_constrained


def test_sensitivity_reports_half_and_double_hit_rate():
    r = solve_kelly(_inputs())
    labels = [row[0] for row in r.sensitivity]
    assert labels == ["half hit rate", "stated hit rate", "double hit rate"]
    assert r.sensitivity[1][1] == r.f_constrained
    assert r.sensitivity[0][1] <= r.sensitivity[2][1]


def test_fatter_tail_is_not_penalised_versus_thinner():
    # smaller tail_index = fatter tail = bigger winners
    fat = solve_kelly(_inputs(tail_index=1.2))
    thin = solve_kelly(_inputs(tail_index=3.0))
    assert fat.f_star >= thin.f_star
