"""Konzervativní párování: žádné odhady ani identifikátory v nálezech."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Optional

from app.core.models import Issue
from app.core.periods import Period


@dataclass(frozen=True)
class EmploymentIdentity:
    row: int
    period: Period
    internal_number: str = field(repr=False)
    oic: Optional[str] = field(default=None, repr=False)
    rc: Optional[str] = field(default=None, repr=False)
    invalid: bool = False


@dataclass(frozen=True)
class Assignment:
    row: int
    person_group: str
    primary_pp: bool


def canonical_identifier(value: str, kind: str) -> Optional[str]:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Identifikátor musí být textový.")
    value = value.strip()
    if not value:
        return None
    if kind == "oic" and re.fullmatch(r"[0-9]{10}", value):
        return value
    if kind == "rc" and re.fullmatch(r"[0-9]{6}/?[0-9]{3,4}", value):
        return value.replace("/", "")
    raise ValueError("Neplatný formát identifikačního klíče.")


def numeric_key(value: str):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,64}", value):
        raise ValueError("Interní číslo musí být text číslic.")
    canonical = value.lstrip("0") or "0"
    return len(canonical), canonical


def pair_employments(identities):
    """Find entire connected components BEFORE allowing any pairing/primary flag."""
    identities = tuple(identities)
    parents = list(range(len(identities)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parents[b] = a

    tokens = {}
    for i, identity in enumerate(identities):
        for kind, value in [("oic", identity.oic), ("rc", identity.rc)]:
            if value:
                key = (kind, value)
                if key in tokens:
                    union(i, tokens[key])
                else:
                    tokens[key] = i
    components = defaultdict(list)
    for i, identity in enumerate(identities):
        components[find(i)].append(identity)
    issues, assignments = [], {}
    number_occurrences = defaultdict(list)
    for identity in identities:
        number_occurrences[(identity.period.iso, identity.internal_number)].append(identity.row)
    duplicates = {row for rows in number_occurrences.values() if len(rows) > 1 for row in rows}
    group_number = 0
    for component in components.values():
        conflict = len({p.oic for p in component if p.oic}) > 1 or len({p.rc for p in component if p.rc}) > 1
        invalid = conflict or any(p.invalid or p.row in duplicates or not (p.oic or p.rc) for p in component)
        for p in component:
            if conflict:
                issues.append(Issue(p.row, "identity", "identity_conflict", "Identifikační údaje propojené skupiny si odporují; PP nebyly spárovány.", "Ověřte identifikátory ve zdroji; skupinu nelze spojit odhadem.", "user_workflow"))
            elif invalid:
                issues.append(Issue(p.row, "identity", "identity_group_blocked", "Párování a primární PP blokuje chybějící nebo nejednoznačný údaj skupiny.", "Opravte všechny dotčené zdrojové řádky.", "user_workflow"))
        if invalid:
            continue
        by_period = defaultdict(list)
        for p in component:
            by_period[p.period.iso].append(p)
        group_number += 1
        for period_rows in by_period.values():
            keys = [numeric_key(p.internal_number) for p in period_rows]
            minimum = min(keys)
            if keys.count(minimum) != 1:
                for p in period_rows:
                    issues.append(Issue(p.row, "internal_number", "ambiguous_primary", "Nejnižší interní číslo je po číselném porovnání nejednoznačné.", "Vyjasněte interní čísla; pořadí úvodních nul nerozhoduje.", "user_workflow"))
                continue
            for p, key in zip(period_rows, keys):
                assignments[p.row] = Assignment(p.row, "person-{0}".format(group_number), key == minimum)
    return assignments, issues
