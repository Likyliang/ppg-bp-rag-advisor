"""Near-duplicate detection for catalogued literature.

The catalog already blocks *byte-identical* identity (``source_identity_hash``
over raw title/url/doi/pmid). That misses the common real-world duplicates:
case/punctuation differences in titles, a DOI living in the ``url`` field on one
entry and the ``doi`` field on another, and DOI case differences. This module
adds a normalized "is this the same paper?" matcher used by both the add/import
warning path and the library-wide duplicate scan.

Matching rule (tuned to minimise false positives in a medical KB):

* **DOI is authoritative.** If both entries carry a normalized DOI, they are a
  duplicate iff the DOIs intersect — and if they *differ*, that is a hard veto
  (different DOIs ⇒ different papers, even when titles coincide).
* **PMID** is the same story when neither DOI is available on both sides.
* **Title + year fallback** only when at least one side lacks a DOI/PMID: the
  normalized titles must be equal *and* both years present and equal.

Nothing here deletes anything; callers surface matches for manual review.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")
_PMID_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.IGNORECASE)
_TITLE_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_DOI_CUT_RE = re.compile(r"[?#&\s]")  # url query / fragment / param / whitespace boundary
# URL trailing segments that are appended after a DOI (not part of it).
_DOI_TRAILING = (
    "/full", "/fulltext", "/full-text", "/pdf", "/epdf", "/abstract",
    "/meta", "/html", "/references", "/citation", "/summary", "/figures",
)


def normalize_doi(raw: Any) -> str:
    """Extract a bare, lower-cased DOI from a DOI/url/``doi:`` string, or "".

    Over-capturing a URL tail (``&type=printable``, ``/fulltext``) is worse than
    under-capturing: it makes two entries of the *same* paper look like *different*
    DOIs, which then hard-vetoes the title+year fallback. So we cut aggressively at
    the first url delimiter and repeatedly strip known trailing path segments.
    """

    match = _DOI_RE.search(str(raw or ""))
    if not match:
        return ""
    doi = _DOI_CUT_RE.split(match.group(0), 1)[0]  # stop at ? # & or whitespace
    lower = doi.lower().rstrip("/.,;)")
    changed = True
    while changed:
        changed = False
        for suffix in _DOI_TRAILING:
            if lower.endswith(suffix):
                lower = lower[: -len(suffix)].rstrip("/.,;)")
                changed = True
                break
    return lower


def normalize_pmid(raw: Any) -> str:
    """Digits-only PMID from a field or a PubMed url, or ""."""

    text = str(raw or "").strip()
    url_match = _PMID_URL_RE.search(text)
    if url_match:
        return url_match.group(1)
    digits = re.sub(r"\D", "", text)
    return digits


# Generic section/type titles that are NOT specific enough to stand as sole
# evidence — distinct papers routinely share these, so a bare title+year match
# on them is almost always a false positive.
_GENERIC_TITLES = frozenset({
    "editorial", "erratum", "corrigendum", "correction", "reply", "response",
    "letter", "letter to the editor", "introduction", "comment", "commentary",
    "preface", "foreword", "obituary", "in this issue", "highlights", "abstracts",
    "contents", "table of contents", "acknowledgments", "acknowledgements", "news",
})


def normalize_title(raw: Any) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""

    if not raw:
        return ""
    text = str(raw).lower().strip()
    text = _TITLE_PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _year(source: Dict[str, Any]) -> str:
    raw = source.get("year")
    if raw in (None, ""):
        return ""
    digits = re.sub(r"\D", "", str(raw))
    return digits


def source_dois(source: Dict[str, Any]) -> Set[str]:
    """Normalized DOI(s): the ``doi`` field, or the ``url`` as a fallback."""

    doi = normalize_doi(source.get("doi"))
    if doi:
        return {doi}
    from_url = normalize_doi(source.get("url"))
    return {from_url} if from_url else set()


def source_pmids(source: Dict[str, Any]) -> Set[str]:
    out: Set[str] = set()
    field = normalize_pmid(source.get("pmid"))
    if field:
        out.add(field)
    url_match = _PMID_URL_RE.search(str(source.get("url") or ""))
    if url_match:
        out.add(url_match.group(1))
    return out


# --------------------------------------------------------------------------- #
# Identity + matching
# --------------------------------------------------------------------------- #
class _Identity:
    """Pre-computed match keys for one source (built once, compared many times)."""

    __slots__ = ("source_id", "dois", "pmids", "title", "year")

    def __init__(self, source: Dict[str, Any]) -> None:
        self.source_id = source.get("source_id")
        self.dois = source_dois(source)
        self.pmids = source_pmids(source)
        self.title = normalize_title(source.get("title"))
        self.year = _year(source)

    @property
    def has_strong_id(self) -> bool:
        return bool(self.dois or self.pmids)


def _match(a: "_Identity", b: "_Identity") -> Optional[str]:
    """Return the match reason ('doi' | 'pmid' | 'title+year') or None."""

    if a.dois and b.dois:
        return "doi" if (a.dois & b.dois) else None  # differing DOIs veto
    if a.pmids and b.pmids:
        return "pmid" if (a.pmids & b.pmids) else None
    if (
        a.title
        and a.title == b.title
        and a.year
        and a.year == b.year
        and a.title not in _GENERIC_TITLES  # generic titles are never sole evidence
    ):
        return "title+year"
    return None


def find_duplicates(
    candidate: Dict[str, Any],
    existing: List[Dict[str, Any]],
    *,
    ignore_id: Optional[str] = None,
    existing_ids: Optional[List["_Identity"]] = None,
) -> List[Dict[str, Any]]:
    """Existing sources that look like the same paper as ``candidate``.

    Returns ``[{source_id, title, reason}]`` (possibly empty). Used for the
    non-blocking add/import warning. Pass ``existing_ids`` (pre-built once via
    :func:`build_identities`) to avoid re-normalising the whole catalogue per
    candidate when checking a batch.
    """

    cand = _Identity(candidate)
    ids = existing_ids if existing_ids is not None else [_Identity(s) for s in existing]
    matches: List[Dict[str, Any]] = []
    for source, ident in zip(existing, ids):
        sid = source.get("source_id")
        if ignore_id is not None and sid == ignore_id:
            continue
        reason = _match(cand, ident)
        if reason:
            matches.append({"source_id": sid, "title": source.get("title"), "reason": reason})
    return matches


def build_identities(sources: List[Dict[str, Any]]) -> List["_Identity"]:
    """Pre-compute identities once for batch duplicate checks."""

    return [_Identity(s) for s in sources]


def find_duplicate_clusters(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group ``sources`` into near-duplicate clusters (size >= 2).

    Union-find over pairwise matches. Returns clusters sorted largest-first,
    each ``{reasons: [...], size: n, members: [source dict, ...]}``.
    """

    ids = [_Identity(s) for s in sources]
    n = len(ids)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges: List[tuple] = []  # (i, j, reason)
    for i in range(n):
        for j in range(i + 1, n):
            reason = _match(ids[i], ids[j])
            if not reason:
                continue
            # A weak title+year edge must not bridge an identifier-bearing source
            # into a cluster: otherwise transitivity (A-doi ~ B-noid ~ C-doi) could
            # merge DOI-conflicting papers and let the whole cluster inherit a
            # "strong" label. Weak edges only connect two identifier-less sources.
            if reason == "title+year" and (ids[i].has_strong_id or ids[j].has_strong_id):
                continue
            edges.append((i, j, reason))
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    # Aggregate reasons per final component (roots may have shifted during union).
    component_reasons: Dict[int, Set[str]] = defaultdict(set)
    for i, _j, reason in edges:
        component_reasons[find(i)].add(reason)

    groups: Dict[int, List[int]] = defaultdict(list)
    for idx in range(n):
        groups[find(idx)].append(idx)

    clusters: List[Dict[str, Any]] = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        clusters.append(
            {
                "reasons": sorted(component_reasons.get(root, set())) or ["match"],
                "size": len(members),
                "members": [sources[idx] for idx in members],
            }
        )
    clusters.sort(key=lambda c: (-c["size"], c["members"][0].get("source_id", "")))
    return clusters
