"""
Operation Bundling: merge same-day, tank-mixable FERTILIZER/SPRAY activities
into a single recommended operation instead of showing/recommending several
separate continuous farmer operations for the same day.

This used to live as page-local helpers inside pages/2_Cultivation_Schedule.py;
it's a shared service now so the Recommendation Engine (which needs to
bundle when building the single "Recommended Next Operation") and the
Cultivation Schedule page (which needs to bundle when rendering the weekly
card grid) both bundle exactly the same way, from one place.

Operates on plain dicts, not ORM rows, so it has no DB dependency and is
trivial to unit test:
    {"id", "activity_date", "das", "name", "category", "status", "remarks", "is_custom"}
A merged row gets an additional "ids" (list of every id folded in) and
"members" (list of original names) key; single (unmerged) rows keep just
"id" and never get a "members" key, so callers can check `row.get("members")`
to know whether a row represents a bundle.
"""
from __future__ import annotations

from datetime import date

# Only FERTILIZER/SPRAY are ever bundle candidates -- irrigation, weeding,
# harvest etc. are physically separate field operations that can't be
# folded into a tank-mix regardless of same-day timing.
COMBINABLE_CATS = {"FERTILIZER", "SPRAY"}


def parse_remarks(remarks: str) -> dict[str, str]:
    """
    Parse the "Label: value. Label: value." remarks convention used
    throughout this codebase's seed data (see _card() in
    seed/bhendi_physiology_v3.py) into a dict. Duplicated here (rather than
    imported from the page) so this module has zero dependency on
    Streamlit or any page module.
    """
    fields: dict[str, str] = {}
    for chunk in remarks.split(". "):
        chunk = chunk.strip().rstrip(".")
        if ":" not in chunk:
            continue
        label, _, value = chunk.partition(":")
        fields[label.strip()] = value.strip()
    return fields


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def is_foliar(row: dict, hint_lookup=None) -> bool:
    """Only foliar (tank-mixable) applications can realistically be combined
    into one spray-tank field trip -- soil-applied/basal fertilizer (e.g.
    basal DAP+MOP, basal iron correction) has to stay a separate operation."""
    if row["category"] == "SPRAY":
        return True
    parsed = parse_remarks(row["remarks"])
    method = (parsed.get("Method") or "").lower()
    text = (row["name"] + " " + row["remarks"]).lower()
    return "foliar" in method or "foliar" in text or "spray" in method


def merge_group(group: list[dict], get_hint) -> dict:
    """
    Combine several same-day foliar ops into one synthetic row. Rebuilds a
    `remarks` string in the same 'Label: value.' shape parse_remarks()
    already understands, so downstream rendering/parsing needs no
    special-casing for combined vs single rows.

    `get_hint(name, remarks, category) -> dict | None` is injected (rather
    than imported) so this module doesn't depend on the page's
    PRODUCT_HINTS table.
    """
    names = [g["name"] for g in group]
    combined_name = " + ".join(names) if len(names) <= 2 else f"Combined Application ({len(names)} items)"

    products, methods, timings, waters, precautions = [], [], [], [], []
    for g in group:
        parsed  = parse_remarks(g["remarks"])
        hint    = get_hint(g["name"], g["remarks"], g["category"])
        product = clean_value(parsed.get("Product") or (hint["combo"] if hint else "")) or g["name"]
        dose    = clean_value(parsed.get("Dose") or (hint["dose"] if hint else ""))
        products.append(f"{product} — {dose}" if dose else product)
        m = clean_value(parsed.get("Method", ""))
        t = clean_value(parsed.get("Timing", ""))
        w = clean_value(parsed.get("Water", ""))
        p = clean_value(parsed.get("Precautions") or (hint["note"] if hint else ""))
        if m:
            methods.append(m)
        if t:
            timings.append(t)
        if w:
            waters.append(w)
        if p:
            precautions.append(p)

    statuses = {g["status"] for g in group}
    if statuses <= {"COMPLETED", "SKIPPED"}:
        status = "COMPLETED" if "COMPLETED" in statuses else "SKIPPED"
    else:
        status = "PENDING"

    remarks_parts = [
        "Priority: Essential.",
        "Product: " + "; ".join(products) + ".",
        "Dose: see combined product list above.",
    ]
    if waters:
        remarks_parts.append(f"Water: {waters[0]}.")
    remarks_parts.append("Method: " + ("; ".join(sorted(set(methods))) if methods else "Foliar spray") + ".")
    if timings:
        remarks_parts.append("Timing: " + "; ".join(sorted(set(timings))) + ".")
    remarks_parts.append(f"Objective: One combined field operation instead of {len(group)} separate trips.")
    remarks_parts.append("Why: These fall on the same day and are compatible to combine (tank-mix/apply together).")
    if precautions:
        remarks_parts.append("Precautions: " + " ".join(precautions))

    cats = {g["category"] for g in group}
    return {
        "id":            group[0]["id"],
        "ids":           [g["id"] for g in group],
        "activity_date": group[0]["activity_date"],
        "das":           group[0]["das"],
        "name":          combined_name,
        "category":      group[0]["category"] if len(cats) == 1 else "FERTILIZER",
        "status":        status,
        "remarks":       " ".join(remarks_parts),
        "is_custom":     any(g["is_custom"] for g in group),
        "members":       names,
    }


def combine_items(items: list[dict], get_hint) -> list[dict]:
    """Merge same-day, tank-mixable FERTILIZER/SPRAY rows so the schedule
    recommends one combined operation (with combined dose) rather than
    several separate continuous farmer operations on the same day."""
    buckets: dict[date, list[dict]] = {}
    order: list[date] = []
    passthrough: list[dict] = []
    for r in items:
        if r["category"] in COMBINABLE_CATS and is_foliar(r):
            key = r["activity_date"]
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            buckets[key].append(r)
        else:
            passthrough.append(r)

    combined: list[dict] = []
    for key in order:
        group = buckets[key]
        combined.append(group[0] if len(group) == 1 else merge_group(group, get_hint))

    return sorted(combined + passthrough, key=lambda r: r["activity_date"])
