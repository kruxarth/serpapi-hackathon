"""The LLM gateway (spec 4.6): DeepSeek by default, any OpenAI-compatible endpoint.

The LLM informs, never decides (Rule 8):
- Job 1 writes a plain-language summary from a numbered fact list. It may only
  refer to facts by id; a deterministic validator rejects anything else, and
  fixed templates are used when there's no key or validation fails twice.
- Job 2 (optional, off by default) groups reworded template texts: signal A8,
  context only, which can never flag a reviewer on its own.

Only pseudonymized data is ever sent. Every call is cached by a hash of
(model, prompt version, input) and stored before it's parsed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from importlib import resources
from typing import Any

import requests

from . import config, db, redact
from .normalize.geo import known_area_names

log = logging.getLogger(__name__)

SUMMARY_PROMPT = "summary-v1"
PARAPHRASE_PROMPT = "paraphrase-v1"
BANNED = [
    "fake",
    "fakes",
    "fraud",
    "frauds",
    "fraudulent",
    "scam",
    "scams",
    "scammer",
    "scammers",
    "paid",
    "bought",
    "bot",
    "bots",
    "inauthentic",
    "manipulate",
    "manipulated",
    "manipulation",
    "manipulative",
]
NUMBER_WORDS = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "hundreds",
    "thousand",
    "thousands",
    "lakh",
    "lakhs",
    "crore",
    "crores",
    "percent",
    "per cent",
    "half",
    "dozen",
    "dozens",
    "million",
    "billion",
]
FACT_REF = re.compile(r"\[F(\d+)\]")
URLISH = re.compile(r"https?://|www\.|googleusercontent|maps\.app\.goo\.gl|@[A-Za-z0-9.\-]+\.[a-z]{2,}", re.I)

Transport = Callable[[list[dict[str, str]], bool], str]


class LLMRefused(RuntimeError):
    """The input wasn't safe to send (it contained a real identity)."""


def _prompt(name: str) -> str:
    return resources.files("reviewring.prompts").joinpath(f"{name.replace('-', '_')}.txt").read_text("utf-8")


def default_transport(api_key: str) -> Transport:
    cfg = config.load_tunables()["llm"]

    def call(messages: list[dict[str, str]], json_mode: bool) -> str:
        body: dict[str, Any] = {
            "model": cfg["model"],
            "messages": messages,
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            resp = requests.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=cfg["timeout_seconds"],
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"] or "")
        except (requests.RequestException, KeyError, ValueError) as exc:
            raise RuntimeError(f"LLM call failed: {redact.safe_error(exc)}") from None

    return call


class LLMGateway:
    def __init__(
        self,
        *,
        mode: str = "live",
        secrets: config.Secrets | None = None,
        transport: Transport | None = None,
        db_path=None,
    ) -> None:
        redact.install()
        self.secrets = secrets or config.load_secrets()
        if self.secrets.deepseek_key:
            redact.register_secret(self.secrets.deepseek_key)
        self.mode = mode
        self.db_path = db_path
        self._transport = transport

    @property
    def model(self) -> str:
        return str(config.tunable("llm", "model"))

    @property
    def can_call(self) -> bool:
        return self.mode == "live" and (self._transport is not None or bool(self.secrets.deepseek_key))

    def _key(self, prompt_version: str, payload: str) -> str:
        return hashlib.sha256(f"{self.model}\n{prompt_version}\n{payload}".encode()).hexdigest()

    def cached(self, prompt_version: str, payload: str) -> str | None:
        row = (
            db.connect(self.db_path)
            .execute("SELECT output FROM llm_responses WHERE request_key = ?", (self._key(prompt_version, payload),))
            .fetchone()
        )
        return row["output"] if row else None

    def complete(self, prompt_version: str, system: str, payload: str) -> str | None:
        """Cached completion. None when it isn't cached and a live call isn't allowed."""
        hit = self.cached(prompt_version, payload)
        if hit is not None:
            return hit
        if not self.can_call:
            return None
        transport = self._transport or default_transport(self.secrets.deepseek_key or "")
        output = transport([{"role": "system", "content": system}, {"role": "user", "content": payload}], True)
        db.connect(self.db_path).execute(  # persist before parse
            "INSERT OR REPLACE INTO llm_responses (request_key, model, prompt_version, input, output, validated, "
            "created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (self._key(prompt_version, payload), self.model, prompt_version, payload, output, db.iso(db.utcnow())),
        )
        return output

    def mark_valid(self, prompt_version: str, payload: str) -> None:
        db.connect(self.db_path).execute(
            "UPDATE llm_responses SET validated = 1 WHERE request_key = ?", (self._key(prompt_version, payload),)
        )


# ---------------------------------------------------------------------- privacy


def forbidden_values(report: dict[str, Any]) -> list[str]:
    """Real identities that must never be sent: names, contributor ids, review ids, business titles."""
    values = set((report.get("names") or {}).values()) | set((report.get("names") or {}).keys())
    values |= {r["contributor_id"] for r in report.get("reviewers", []) if r.get("contributor_id")}
    values |= {r["review_id"] for r in report.get("reviews", [])}
    values |= {r["contributor_id"] for r in report.get("reviews", []) if r.get("contributor_id")}
    title = report.get("place", {}).get("title")
    if title and not report.get("pseudonymized"):
        values.add(title)
    for rows in report.get("client_lists", {}).values():
        for row in rows:
            if row.get("title") and not report.get("pseudonymized"):
                values.add(row["title"])
    return sorted(v for v in values if v and len(v) >= 4)


def assert_safe(payload: str, forbidden: list[str]) -> None:
    if URLISH.search(payload):
        raise LLMRefused("The LLM input contains a link or an email address.")
    low = payload.casefold()
    for v in forbidden:
        if v.casefold() in low:
            raise LLMRefused("The LLM input contains a real name or identifier.")


# ---------------------------------------------------------------------- job 1: summary


def build_facts(report: dict[str, Any]) -> list[dict[str, str]]:
    """Numbered facts, each already formatted. Businesses are pseudonyms; no reviewer is named."""
    facts: list[str] = []

    def add(text: str) -> str:
        facts.append(text)
        return f"F{len(facts)}"

    r = report["ratings"]
    place = report["place"]
    add(f"this {(place.get('type') or 'business').lower()}")
    add(f"the latest {r['examined']} reviews")
    if r["sample_mean"] is not None:
        add(f"{r['sample_mean']:.2f} stars")
    if r["without_ring"] is not None and r["ring_reviews"]:
        add(f"{r['without_ring']:.2f} stars without the ring reviews")
        add(f"{r['ring_reviews']} reviews")
    add(f"suspicion level {report['level']['level']}")
    for g in report.get("groups", []):
        m = g["metrics"]
        if g["verdict"] in ("ring", "possible_ring", "possible_ring_trip"):
            add(f"a group of {m['size']} reviewer accounts")
            add(f"{m['core_places']} other businesses")
            if m["far_areas"]:
                add(", ".join(m["far_areas"][:-1]) + (" and " if len(m["far_areas"]) > 1 else "") + m["far_areas"][-1])
            if g["verdict"] == "possible_ring_trip":
                add("a pattern that could also be a group trip")
        elif g["verdict"] == "ruled_out_trip":
            add(f"a group of {m['size']} reviewers that looks like a group trip and was not counted")
    for b in report["signals"]["T1"]["bursts"]:
        add(f"{b['count']} reviews between {b['start']} and {b['end']}")
    dups = sum(len(v) for v in report["signals"]["T4"]["clusters"].values())
    if dups:
        add(f"{dups} near-identical review texts")
    add(f"{report['sample']['expanded']} reviewer histories checked")
    return [{"id": f"F{i + 1}", "text": t} for i, t in enumerate(facts)]


def validate_summary(paragraphs: Any, facts: list[dict[str, str]], extra_areas: set[str]) -> list[str]:
    """Problems with an LLM draft; empty when it may be shown."""
    if not isinstance(paragraphs, list) or not paragraphs or not all(isinstance(p, str) for p in paragraphs):
        return ["The reply must be a JSON object with a non-empty list of paragraph strings."]
    problems: list[str] = []
    ids = {f["id"] for f in facts}
    areas = {a for a in known_area_names() | extra_areas if a}
    for p in paragraphs:
        for m in FACT_REF.finditer(p):
            if f"F{m.group(1)}" not in ids:
                problems.append(f"Unknown fact id F{m.group(1)}.")
        bare = FACT_REF.sub(" ", p)
        bare_low = re.sub(r"\bno one\b", " ", bare.casefold())
        if re.search(r"\d", bare_low):
            problems.append("A digit appears outside a fact reference.")
        for w in NUMBER_WORDS:
            if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", bare_low):
                problems.append(f"The number word '{w}' appears outside a fact reference.")
        for a in areas:
            if re.search(rf"(?<!\w){re.escape(a.casefold())}(?!\w)", bare_low):
                problems.append(f"The place name '{a}' appears outside a fact reference.")
        for w in BANNED:
            if re.search(rf"(?<!\w){w}(?!\w)", bare_low):
                problems.append(f"The word '{w}' isn't allowed.")
    return sorted(set(problems))


def substitute(paragraphs: list[str], facts: list[dict[str, str]]) -> list[str]:
    by_id = {f["id"]: f["text"] for f in facts}
    return [FACT_REF.sub(lambda m: by_id[f"F{m.group(1)}"], p) for p in paragraphs]


def template_summary(report: dict[str, Any]) -> list[str]:
    paras = [" ".join(report["level"]["reasons"])]
    paras += [e["text"] for e in report.get("evidence", [])[:3]]
    paras.append(
        "This is a pattern, not proof. " + report["caveats"][1]
        if len(report.get("caveats", [])) > 1
        else "This is a pattern, not proof."
    )
    return [p for p in paras if p]


def summarize(report: dict[str, Any], gateway: LLMGateway | None) -> dict[str, Any]:
    """The AI summary block for a report: validated LLM text, or the fixed templates."""
    facts = build_facts(report)
    model = gateway.model if gateway else config.tunable("llm", "model")
    fallback = {
        "model": model,
        "prompt_version": SUMMARY_PROMPT,
        "paragraphs": template_summary(report),
        "source": "template",
    }
    if gateway is None:
        return fallback
    payload = json.dumps({"facts": facts}, ensure_ascii=False)
    assert_safe(payload, forbidden_values(report))
    extra_areas = {g for grp in report.get("groups", []) for g in grp["metrics"].get("far_areas", [])}
    extra_areas.add(report["place"].get("area") or "")
    system = _prompt(SUMMARY_PROMPT)
    for attempt in range(2):
        try:
            raw = gateway.complete(SUMMARY_PROMPT, system, payload)
        except RuntimeError as exc:
            log.warning("summary call failed: %s", exc)
            return fallback
        if raw is None:
            return fallback
        try:
            paragraphs = json.loads(raw).get("paragraphs")
        except (ValueError, AttributeError):
            paragraphs = None
        problems = validate_summary(paragraphs, facts, extra_areas)
        if not problems:
            gateway.mark_valid(SUMMARY_PROMPT, payload)
            return {
                "model": model,
                "prompt_version": SUMMARY_PROMPT,
                "paragraphs": substitute(paragraphs, facts),
                "source": "llm",
                "facts": facts,
            }
        if attempt == 0:
            payload = json.dumps(
                {"facts": facts, "previous_reply": raw, "problems_to_fix": problems}, ensure_ascii=False
            )
    return fallback


# ---------------------------------------------------------------------- job 2: paraphrase signal (A8)


def paraphrase_groups(texts: dict[str, str], gateway: LLMGateway, business_words: set[str]) -> dict[str, int]:
    """Map review_id -> group for reworded template texts. Texts are scrubbed and indexed opaquely."""
    from .privacy import scrub_text

    ids = sorted(texts)
    items = [{"index": i, "text": scrub_text(texts[rid], business_words)[:400]} for i, rid in enumerate(ids)]
    payload = json.dumps({"texts": items}, ensure_ascii=False)
    assert_safe(payload, [])
    raw = gateway.complete(PARAPHRASE_PROMPT, _prompt(PARAPHRASE_PROMPT), payload)
    if raw is None:
        return {}
    try:
        groups = json.loads(raw).get("groups", [])
    except (ValueError, AttributeError):
        return {}
    out: dict[str, int] = {}
    for g_index, g in enumerate(groups if isinstance(groups, list) else []):
        members = [i for i in (g.get("indices") or []) if isinstance(i, int) and 0 <= i < len(ids)]
        if len(members) >= 2:
            for i in members:
                out.setdefault(ids[i], g_index)
    gateway.mark_valid(PARAPHRASE_PROMPT, payload)
    return out
