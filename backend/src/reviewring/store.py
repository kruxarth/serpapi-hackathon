"""Write the normalized tables of spec section 7 from a collected AnalysisInput.

The engine always works from AnalysisInput (rebuilt from raw responses), so these
tables are a queryable record of what was parsed, e.g. for checking parsers.
"""

from __future__ import annotations

import json

from . import db
from .engine.features import compute_text_features, target_text_id
from .engine.groups import type_group
from .model import AnalysisInput


def save_parsed(inp: AnalysisInput, conn=None) -> None:
    conn = conn or db.connect()
    features = compute_text_features(inp)
    with conn:
        for p in inp.places.values():
            conn.execute(
                "INSERT OR REPLACE INTO places (place_key, data_id, place_id, title, address, area, lat, lng, type, "
                "type_group, rating, total_reviews) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    p.place_key,
                    p.data_id,
                    p.title,
                    p.address,
                    p.area,
                    p.lat,
                    p.lng,
                    p.type,
                    type_group(p.type)[0],
                    p.rating,
                    p.total_reviews,
                ),
            )
        for r in inp.target_reviews:
            f = features.get(target_text_id(r.review_id))
            conn.execute(
                "INSERT OR REPLACE INTO target_reviews (review_id, place_key, contributor_id, rating, iso_date, "
                "edited_at, text_original, text_length, text_script, has_images, reviewer_total_reviews, "
                "reviewer_total_photos, local_guide) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r.review_id,
                    inp.target.place_key,
                    r.contributor_id,
                    r.rating,
                    r.posted_at.isoformat() if r.posted_at else None,
                    r.text,
                    f.length if f else None,
                    f.script if f else None,
                    int(r.has_images),
                    r.reviewer_reviews,
                    r.reviewer_photos,
                    None if r.local_guide is None else int(r.local_guide),
                ),
            )
        for cid, c in inp.contributors.items():
            conn.execute(
                "INSERT OR REPLACE INTO contributors (contributor_id, name, level, points, local_guide, contributions, "
                "reviews_returned, history_truncated, fetch_status, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cid,
                    c.name,
                    c.level,
                    c.points,
                    None if c.local_guide is None else int(c.local_guide),
                    json.dumps(c.contributions),
                    c.reviews_returned,
                    int(c.truncated),
                    c.status,
                    db.iso(c.fetched_at) if c.fetched_at else None,
                ),
            )
            for h in inp.histories.get(cid, []):
                conn.execute(
                    "INSERT OR REPLACE INTO contributor_reviews (contributor_id, review_id, place_key, rating, "
                    "relative_date, date_min, date_max, date_precision_days, edited, image_dates, text_original, "
                    "text_length, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        cid,
                        h.review_id,
                        h.place_key,
                        h.rating,
                        h.relative_date,
                        h.date_min.isoformat() if h.date_min else None,
                        h.date_max.isoformat() if h.date_max else None,
                        h.precision_days,
                        int(h.edited),
                        json.dumps(h.image_dates),
                        h.text,
                        len(h.text or ""),
                        db.iso(c.fetched_at) if c.fetched_at else None,
                    ),
                )
