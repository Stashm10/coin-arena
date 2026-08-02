"""Nelder-Mead simplex minimizer. Pure stdlib: the app is packaged with
`flet pack` and must not carry scipy."""

import math
from collections.abc import Callable


def nelder_mead(f: Callable[[list[float]], float], x0: list[float],
                step: float = 0.5, max_iter: int = 300,
                tol: float = 1e-7) -> tuple[list[float], float]:
    """Minimize a scalar function using the Nelder-Mead simplex algorithm.

    Args:
        f: Objective function to minimize, taking a list of floats and returning a scalar.
        x0: Initial point (list of floats).
        step: Initial simplex step size (default 0.5).
        max_iter: Maximum iterations (default 300).
        tol: Convergence tolerance for both function-value spread and simplex diameter (default 1e-7).

    Returns:
        (best_point, best_score): Best point found and its function value.

    Terminates when both the function-value spread and simplex vertex spread drop below tol,
    or when max_iter iterations are reached. Non-finite function values are treated as infinity.
    """
    n = len(x0)

    def safe(p: list[float]) -> float:
        try:
            v = f(p)
        except (ValueError, OverflowError, ZeroDivisionError):
            return math.inf
        return v if math.isfinite(v) else math.inf

    simplex = [list(x0)]
    for i in range(n):
        p = list(x0)
        p[i] += step
        simplex.append(p)
    scores = [safe(p) for p in simplex]

    for _ in range(max_iter):
        order = sorted(range(n + 1), key=lambda i: scores[i])
        simplex = [simplex[i] for i in order]
        scores = [scores[i] for i in order]
        # Terminate when both function-value spread and simplex diameter are below tolerance
        if math.isfinite(scores[-1]) and abs(scores[-1] - scores[0]) < tol:
            diameter = max(
                max(p[j] for p in simplex) - min(p[j] for p in simplex)
                for j in range(n)
            )
            if diameter < tol:
                break
        centroid = [sum(p[i] for p in simplex[:-1]) / n for i in range(n)]
        worst = simplex[-1]
        refl = [centroid[i] + (centroid[i] - worst[i]) for i in range(n)]
        f_refl = safe(refl)
        if f_refl < scores[0]:
            expanded = [centroid[i] + 2.0 * (centroid[i] - worst[i]) for i in range(n)]
            f_exp = safe(expanded)
            simplex[-1], scores[-1] = ((expanded, f_exp) if f_exp < f_refl
                                       else (refl, f_refl))
        elif f_refl < scores[-2]:
            simplex[-1], scores[-1] = refl, f_refl
        else:
            # Contraction: distinguish inside vs. outside based on whether reflection beat worst
            if f_refl < scores[-1]:
                # Outside contraction (toward reflected point)
                contracted = [centroid[i] + 0.5 * (refl[i] - centroid[i]) for i in range(n)]
                f_con = safe(contracted)
                if f_con <= f_refl:
                    simplex[-1], scores[-1] = contracted, f_con
                else:
                    # Shrink toward best point
                    for i in range(1, n + 1):
                        simplex[i] = [simplex[0][j] + 0.5 * (simplex[i][j] - simplex[0][j])
                                      for j in range(n)]
                        scores[i] = safe(simplex[i])
            else:
                # Inside contraction (toward worst point)
                contracted = [centroid[i] + 0.5 * (worst[i] - centroid[i]) for i in range(n)]
                f_con = safe(contracted)
                if f_con < scores[-1]:
                    simplex[-1], scores[-1] = contracted, f_con
                else:
                    # Shrink toward best point
                    for i in range(1, n + 1):
                        simplex[i] = [simplex[0][j] + 0.5 * (simplex[i][j] - simplex[0][j])
                                      for j in range(n)]
                        scores[i] = safe(simplex[i])

    best = min(range(n + 1), key=lambda i: scores[i])
    return simplex[best], scores[best]
