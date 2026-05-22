"""Phase 11C.1C-A - Peer-cluster context builder.

Phase 11C.1C-A pins the *contract* only. The cheap classifier in
this module groups candidates by quote asset suffix (e.g. every
``*USDT`` symbol lands in cluster ``"USDT"``) so the WS-radar
event-chain driver always has a valid value to attach. Smarter
cluster classification (sector / narrative / leader detection /
priority_score) is reserved for a later PR; the field set is pinned
here so the daily-report and export contracts do not need
re-shaping when that work lands.

Phase 11C.1C-A boundary
-----------------------

  - Pure functions; no I/O, no global state.
  - Uses ONLY information already on the candidate / radar snapshot
    (no cross-symbol REST calls).
  - Cluster membership is descriptive; selecting a leader does NOT
    aggregate position size and does NOT trigger any cross-symbol
    co-execution.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from app.adaptive.models import ClusterContext


_KNOWN_QUOTE_SUFFIXES: tuple[str, ...] = (
    "USDT",
    "USDC",
    "BUSD",
    "BTC",
    "ETH",
    "FDUSD",
    "TUSD",
)


def _quote_asset_for(symbol: str) -> str:
    """Return the canonical quote-asset suffix or ``"unknown"``.

    The lookup is case-sensitive against Binance's canonical
    contract spelling. Non-ASCII contracts work unchanged: the
    suffix check is plain string ``.endswith``.
    """
    text = str(symbol or "").strip()
    if not text:
        return "unknown"
    upper = text.upper()
    for suffix in _KNOWN_QUOTE_SUFFIXES:
        if upper.endswith(suffix):
            return suffix
    return "unknown"


def build_cluster_context(
    *,
    symbol: str,
    radar_score: float = 0.0,
    cluster_id: str | None = None,
    peer_scores: Mapping[str, float] | Iterable[tuple[str, float]] | None = None,
    cluster_reason: tuple[str, ...] = (),
) -> ClusterContext:
    """Build a :class:`ClusterContext` for one candidate.

    Default behaviour:

      - If ``cluster_id`` is supplied, it is used verbatim.
      - Otherwise, the cluster is the candidate's quote-asset
        suffix (``"USDT"`` / ``"USDC"`` / ...).
      - When ``peer_scores`` is supplied, the highest-scoring symbol
        in the cluster is picked as the cluster leader and the
        candidate's rank within the cluster is computed.
      - When ``peer_scores`` is empty, the candidate is its own
        cluster leader (rank=1, size=1).
    """
    cid = (cluster_id or _quote_asset_for(symbol)).strip() or "unknown"
    peers: dict[str, float] = {}
    if peer_scores is not None:
        if isinstance(peer_scores, Mapping):
            for sym, score in peer_scores.items():
                peers[str(sym)] = float(score)
        else:
            for sym, score in peer_scores:
                peers[str(sym)] = float(score)
    # Always include this candidate so the cluster has at least one
    # member.
    peers[str(symbol)] = max(peers.get(str(symbol), 0.0), float(radar_score))

    # Rank by score desc; ties broken by symbol for determinism.
    ordered = sorted(peers.items(), key=lambda r: (-r[1], r[0]))
    leader = ordered[0][0]
    cluster_size = len(ordered)
    rank = 0
    for index, (sym, _score) in enumerate(ordered, start=1):
        if sym == str(symbol):
            rank = index
            break

    reasons: list[str] = list(cluster_reason)
    if not reasons:
        reasons.append("quote_asset_grouping")
    if leader == str(symbol):
        reasons.append("self_leader")
    return ClusterContext(
        cluster_id=cid,
        cluster_leader=leader,
        cluster_rank=int(rank),
        cluster_size=int(cluster_size),
        cluster_reason=tuple(reasons),
    )


__all__ = [
    "build_cluster_context",
]
