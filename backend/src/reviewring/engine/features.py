"""Text features for one analysis, computed from texts or taken from a fixture."""

from __future__ import annotations

from ..model import AnalysisInput
from ..normalize.text import TextFeatures, TextItem, near_duplicate_clusters


def target_text_id(review_id: str) -> str:
    return f"t:{review_id}"


def history_text_id(contributor_id: str, review_id: str) -> str:
    return f"h:{contributor_id}:{review_id}"


def compute_text_features(inp: AnalysisInput) -> dict[str, TextFeatures]:
    """Clusters over the target's reviews plus every fetched history (never across the whole cache).

    History reviews of the target itself are skipped: they're the same reviews again.
    """
    if inp.text_features is not None:
        return inp.text_features
    target_items = [
        TextItem(target_text_id(r.review_id), r.contributor_id, r.text or "", True) for r in inp.target_reviews
    ]
    items = list(target_items)
    for cid in sorted(inp.histories):
        for h in inp.histories[cid]:
            if h.place_key == inp.target.place_key:
                continue
            items.append(TextItem(history_text_id(cid, h.review_id), cid, h.text or "", False))
    features = near_duplicate_clusters(items)
    target_only = near_duplicate_clusters(target_items)
    for tid, f in target_only.items():
        features[tid].target_cluster = f.cluster
    return features
