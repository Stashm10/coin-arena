import math

from arena.flow.optimize import nelder_mead


def test_finds_minimum_of_quadratic_bowl():
    def f(p):
        return (p[0] - 3.0) ** 2 + (p[1] + 1.5) ** 2

    point, score = nelder_mead(f, [0.0, 0.0])
    assert abs(point[0] - 3.0) < 1e-3
    assert abs(point[1] + 1.5) < 1e-3
    assert score < 1e-6


def test_finds_minimum_of_rosenbrock():
    def f(p):
        return (1 - p[0]) ** 2 + 100 * (p[1] - p[0] ** 2) ** 2

    point, _ = nelder_mead(f, [-1.0, 1.0], max_iter=2000)
    assert abs(point[0] - 1.0) < 1e-2
    assert abs(point[1] - 1.0) < 1e-2


def test_handles_non_finite_scores_without_crashing():
    def f(p):
        if p[0] < 0:
            return math.inf
        return (p[0] - 2.0) ** 2

    point, score = nelder_mead(f, [1.0])
    assert abs(point[0] - 2.0) < 1e-3
    assert math.isfinite(score)


def test_finds_minimum_of_3d_chained_rosenbrock():
    """3D test covering the case Task 2 (Hawkes fit) will use: 3 parameters with step=0.6, max_iter=600."""
    def f(p):
        # Chained Rosenbrock: min at (1, 1, 1)
        return ((1 - p[0]) ** 2 + 100 * (p[1] - p[0] ** 2) ** 2 +
                (1 - p[1]) ** 2 + 100 * (p[2] - p[1] ** 2) ** 2)

    point, _ = nelder_mead(f, [-0.5, -0.5, -0.5], step=0.6, max_iter=600)
    assert len(point) == 3
    assert abs(point[0] - 1.0) < 1e-2
    assert abs(point[1] - 1.0) < 1e-2
    assert abs(point[2] - 1.0) < 1e-2


def test_avoids_premature_termination_on_shallow_ridge():
    """Regression test for shallow-ridge premature termination.

    The diameter-check fix prevents convergence being declared when function-value
    spread is small but simplex vertices cluster only in steep directions, leaving
    shallow (nearly-flat) directions far from optimum. Without diameter check, the old
    algorithm stops with ~0.339 error in p[1]; with the fix, it converges to ~1e-7.
    """
    def f(p):
        # Mismatched curvature: steep in p[0], nearly-flat in p[1]
        return 1e6 * (p[0] - 1.0) ** 2 + 1e-6 * (p[1] - 1.0) ** 2

    point, _ = nelder_mead(f, [0.0, 0.0])
    # Old value-only termination fails this assertion (p[1] ~0.661)
    # New diameter-check termination passes (p[1] ~1.0)
    assert abs(point[1] - 1.0) < 1e-3
