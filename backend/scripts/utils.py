"""
utils.py — shared helpers for the BankMap AI loader scripts.

Provides:
  * sys.path wiring so scripts can `import database` / `import models`
  * the canonical list of Nigerian states (36 + FCT) with codes
  * name normalization
  * fuzzy matching (rapidfuzz if installed, else stdlib difflib)
  * a WardIndex for resolving (state, lga, ward) names to ward rows
  * require_files(): graceful handling when raw data is not yet present
  * a small CSV column resolver

These exist so every loader behaves consistently when Nigerian dataset names
are spelled differently across sources.
"""

import os
import sys
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Make the backend root importable (scripts live in backend/scripts/).
# ---------------------------------------------------------------------------
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

DATA_RAW = os.path.join(BACKEND_ROOT, "data", "raw")
DATA_PROCESSED = os.path.join(BACKEND_ROOT, "data", "processed")

# ---------------------------------------------------------------------------
# Optional fast fuzzy matcher.
# ---------------------------------------------------------------------------
try:
    from rapidfuzz import fuzz as _rf_fuzz

    _HAVE_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - rapidfuzz is optional
    _HAVE_RAPIDFUZZ = False


# ---------------------------------------------------------------------------
# Canonical Nigerian states: name -> ISO-ish state code. 36 states + FCT.
# ---------------------------------------------------------------------------
NIGERIAN_STATES = {
    "Abia": "AB", "Adamawa": "AD", "Akwa Ibom": "AK", "Anambra": "AN",
    "Bauchi": "BA", "Bayelsa": "BY", "Benue": "BE", "Borno": "BO",
    "Cross River": "CR", "Delta": "DE", "Ebonyi": "EB", "Edo": "ED",
    "Ekiti": "EK", "Enugu": "EN", "Gombe": "GO", "Imo": "IM",
    "Jigawa": "JI", "Kaduna": "KD", "Kano": "KN", "Katsina": "KT",
    "Kebbi": "KE", "Kogi": "KO", "Kwara": "KW", "Lagos": "LA",
    "Nasarawa": "NA", "Niger": "NI", "Ogun": "OG", "Ondo": "ON",
    "Osun": "OS", "Oyo": "OY", "Plateau": "PL", "Rivers": "RI",
    "Sokoto": "SO", "Taraba": "TA", "Yobe": "YO", "Zamfara": "ZA",
    "Federal Capital Territory": "FC",
}

# Common alternate spellings seen across GRID3 / NBS / EFInA / CBN / NCC files.
_STATE_ALIASES = {
    "Abuja": "Federal Capital Territory",
    "Fct": "Federal Capital Territory",
    "F.C.T": "Federal Capital Territory",
    "Fct Abuja": "Federal Capital Territory",
    "Nassarawa": "Nasarawa",
    "Akwa-Ibom": "Akwa Ibom",
    "Cross-River": "Cross River",
}


def normalize_name(value) -> str | None:
    """
    Normalize a place name: trim, collapse internal whitespace, Title Case.
    Returns None for empty/null input.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    text = " ".join(text.split())  # collapse repeated whitespace
    return text.title()


def canonical_state(value) -> str | None:
    """Normalize a state name and resolve known aliases to the canonical name."""
    name = normalize_name(value)
    if name is None:
        return None
    if name in _STATE_ALIASES:
        return _STATE_ALIASES[name]
    return name


def similarity(a: str, b: str) -> float:
    """Similarity ratio in [0, 1]. Uses rapidfuzz when available."""
    if not a or not b:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        return _rf_fuzz.ratio(a, b) / 100.0
    return SequenceMatcher(None, a, b).ratio()


def best_match(target: str, choices, threshold: float = 0.85):
    """
    Return (best_choice, score) from `choices` for `target`, or (None, score)
    if nothing clears `threshold`. `choices` is any iterable of strings.
    """
    best, best_score = None, 0.0
    for choice in choices:
        score = similarity(target, choice)
        if score > best_score:
            best, best_score = choice, score
    if best_score >= threshold:
        return best, best_score
    return None, best_score


def require_files(candidates, description: str):
    """
    Return the first existing path among `candidates` (filenames are resolved
    relative to data/raw). If none exist, print a clear message telling the
    user exactly what to place where, and return None so the script can exit
    cleanly even when the raw data is not present yet.
    """
    resolved = []
    for c in candidates:
        path = c if os.path.isabs(c) else os.path.join(DATA_RAW, c)
        resolved.append(path)
        if os.path.exists(path):
            return path

    print("\n" + "=" * 72)
    print(f"[!] Required data not found: {description}")
    print("    Place one of these files in backend/data/raw/ and re-run:")
    for c in candidates:
        print(f"      - {c}")
    print(f"    (looked in: {DATA_RAW})")
    print("=" * 72 + "\n")
    return None


def find_column(df, candidates, required: bool = True):
    """
    Resolve a column name in a pandas DataFrame case-insensitively, trying each
    name in `candidates`. Returns the actual column name or None.
    """
    lookup = {col.lower().strip(): col for col in df.columns}
    for cand in candidates:
        key = cand.lower().strip()
        if key in lookup:
            return lookup[key]
    if required:
        raise KeyError(
            f"None of the expected columns {candidates} found. "
            f"Available columns: {list(df.columns)}"
        )
    return None


class WardIndex:
    """
    In-memory index of wards for fast (and fuzzy) name resolution.

    Build once per script from the DB, then call .match(state, lga, ward).
    Matching is scoped: we first narrow to the right state, then the right LGA,
    then fuzzy-match the ward name within that LGA. This dramatically reduces
    false positives versus matching ward names globally.
    """

    def __init__(self, session, models):
        self.session = session
        self.models = models
        # exact lookups
        self._wards_by_key = {}            # (state_norm, lga_norm, ward_norm) -> Ward
        self._wards_by_lga = {}            # (state_norm, lga_norm) -> {ward_norm: Ward}
        self._states = {}                  # state_norm -> State
        self._lgas_by_state = {}           # state_norm -> {lga_norm: LGA}

        for state in session.query(models.State).all():
            self._states[normalize_name(state.name)] = state
            self._lgas_by_state.setdefault(normalize_name(state.name), {})

        for lga in session.query(models.LGA).all():
            s = session.get(models.State, lga.state_id)
            if not s:
                continue
            sn = normalize_name(s.name)
            self._lgas_by_state.setdefault(sn, {})[normalize_name(lga.name)] = lga

        for ward in session.query(models.Ward).all():
            s = session.get(models.State, ward.state_id)
            lga = session.get(models.LGA, ward.lga_id)
            if not (s and lga):
                continue
            sn, ln, wn = (
                normalize_name(s.name),
                normalize_name(lga.name),
                normalize_name(ward.name),
            )
            self._wards_by_key[(sn, ln, wn)] = ward
            self._wards_by_lga.setdefault((sn, ln), {})[wn] = ward

    def match(self, state, lga, ward, threshold: float = 0.85):
        """
        Resolve (state, lga, ward) names to a Ward row using exact-then-fuzzy
        logic. Returns the Ward or None.
        """
        sn = canonical_state(state)
        ln = normalize_name(lga)
        wn = normalize_name(ward)
        if not (sn and ln and wn):
            return None

        # 1) exact triple
        hit = self._wards_by_key.get((sn, ln, wn))
        if hit:
            return hit

        # 2) fuzzy state -> fuzzy lga -> fuzzy ward (scoped)
        if sn not in self._lgas_by_state:
            match_state, _ = best_match(sn, self._lgas_by_state.keys(), threshold)
            sn = match_state or sn

        lgas = self._lgas_by_state.get(sn, {})
        if ln not in lgas and lgas:
            match_lga, _ = best_match(ln, lgas.keys(), threshold)
            ln = match_lga or ln

        wards = self._wards_by_lga.get((sn, ln), {})
        if wn in wards:
            return wards[wn]
        if wards:
            match_ward, _ = best_match(wn, wards.keys(), threshold)
            if match_ward:
                return wards[match_ward]
        return None
