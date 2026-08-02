"""Shannon entropy over the funding sources of a token's launch buyers.

H(F) = -sum p_i ln(p_i), where p_i is the share of launch buyers whose funds
trace back to root source i. Low entropy means one wallet funded many buyers —
a topological fact about the chain, not a probability. Resolving buyers to
roots is the network-bound half and lives in arena/funding_graph.py.
"""

import math
from collections import Counter
from dataclasses import dataclass


@dataclass
class EntropyResult:
    h: float
    h_norm: float
    n_buyers: int
    n_roots: int
    largest_share: float
    largest_root: str | None


def funding_entropy(roots: dict[str, str]) -> EntropyResult | None:
    n = len(roots)
    if n < 2:
        return None
    counts = Counter(roots.values())
    h = 0.0
    for c in counts.values():
        p = c / n
        h -= p * math.log(p)
    largest_root, largest_count = counts.most_common(1)[0]
    return EntropyResult(h=h, h_norm=h / math.log(n), n_buyers=n,
                         n_roots=len(counts),
                         largest_share=largest_count / n,
                         largest_root=largest_root)


def describe(result: EntropyResult) -> str:
    biggest = round(result.largest_share * result.n_buyers)
    if result.n_roots == result.n_buyers:
        return (f"{result.n_buyers} launch buyers funded from "
                f"{result.n_roots} distinct sources — H̃ = "
                f"{result.h_norm:.2f}")
    return (f"{biggest} of {result.n_buyers} launch buyers trace back to one "
            f"wallet — H̃ = {result.h_norm:.2f}")
