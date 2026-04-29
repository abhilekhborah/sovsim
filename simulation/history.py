from __future__ import annotations
from typing import List, Dict, Any

from .config import Condition


def _format_round_kcpr(r: Dict[str, Any]) -> str:
    z = r["extractions"]
    lines = [
        f"--- Month {r['round']} ---",
        f"Pool at start: ${r['pool_before']}",
        f"Peasant extractions: Peasant 1=${z[0]}, Peasant 2=${z[1]}, Peasant 3=${z[2]} "
        f"(total: ${sum(z[:3])})",
        f"Remaining before king: ${r['remaining_before_leader']}",
        f"King extracted: ${z[3]}",
        f"Final pool: ${r['final_pool']}",
        f"Regenerated to: ${r['pool_next']}",
        f"Payoffs: Peasant 1=${r['payoffs'][0]:.2f}, Peasant 2=${r['payoffs'][1]:.2f}, "
        f"Peasant 3=${r['payoffs'][2]:.2f}, King=${r['payoffs'][3]:.2f}",
    ]
    if r.get("collapsed"):
        lines.append("[COLLAPSED]")
    return "\n".join(lines)


def _format_round_kcpr_m(r: Dict[str, Any]) -> str:
    z = r["extractions"]
    lines = [
        f"--- Month {r['round']} ---",
        f"True pool at start: ${r['pool_before']} | "
        f"King announced: ${r.get('announced_pool', r['pool_before'])}",
        f"Peasant extractions: Peasant 1=${z[0]}, Peasant 2=${z[1]}, Peasant 3=${z[2]} "
        f"(total: ${sum(z[:3])})",
        f"Remaining before king: ${r['remaining_before_leader']}",
        f"King extracted: ${z[3]}",
        f"Final pool: ${r['final_pool']}",
        f"Regenerated to: ${r['pool_next']}",
        f"Payoffs: Peasant 1=${r['payoffs'][0]:.2f}, Peasant 2=${r['payoffs'][1]:.2f}, "
        f"Peasant 3=${r['payoffs'][2]:.2f}, King=${r['payoffs'][3]:.2f}",
    ]
    if r.get("collapsed"):
        lines.append("[COLLAPSED]")
    return "\n".join(lines)


def _format_round_cpr(r: Dict[str, Any]) -> str:
    z = r["extractions"]
    lines = [
        f"--- Month {r['round']} ---",
        f"Pool at start: ${r['pool_before']}",
        f"Citizen extractions: Citizen 1=${z[0]}, Citizen 2=${z[1]}, "
        f"Citizen 3=${z[2]}, Citizen 4=${z[3]} (total: ${sum(z)})",
        f"Final pool: ${r['final_pool']}",
        f"Regenerated to: ${r['pool_next']}",
        f"Payoffs: Citizen 1=${r['payoffs'][0]:.2f}, Citizen 2=${r['payoffs'][1]:.2f}, "
        f"Citizen 3=${r['payoffs'][2]:.2f}, Citizen 4=${r['payoffs'][3]:.2f}",
    ]
    if r.get("collapsed"):
        lines.append("[COLLAPSED]")
    return "\n".join(lines)


def _format_round_bcpr(r: Dict[str, Any]) -> str:
    z = r["extractions"]
    lines = [
        f"--- Month {r['round']} ---",
        f"Pool at start: ${r['pool_before']}",
        f"Worker extractions: Worker 1=${z[0]}, Worker 2=${z[1]}, Worker 3=${z[2]} "
        f"(total: ${sum(z[:3])})",
        f"Remaining before boss: ${r['remaining_before_leader']}",
        f"Boss extracted: ${z[3]}",
        f"Final pool: ${r['final_pool']}",
        f"Regenerated to: ${r['pool_next']}",
        f"Payoffs: Worker 1=${r['payoffs'][0]:.2f}, Worker 2=${r['payoffs'][1]:.2f}, "
        f"Worker 3=${r['payoffs'][2]:.2f}, Boss=${r['payoffs'][3]:.2f}",
    ]
    if r.get("collapsed"):
        lines.append("[COLLAPSED]")
    return "\n".join(lines)


_FORMATTERS = {
    Condition.CPR: _format_round_cpr,
    Condition.BCPR: _format_round_bcpr,
    Condition.KCPR: _format_round_kcpr,
    Condition.KCPR_M: _format_round_kcpr_m,
}


def _compress_rounds(rounds: List[Dict[str, Any]], condition: Condition) -> str:
    # Produce a compact one-line summary of multiple rounds.
    if not rounds:
        return ""
    first, last = rounds[0]["round"], rounds[-1]["round"]

    avg_pool = sum(r["pool_before"] for r in rounds) / len(rounds)
    avg_total_ext = sum(sum(r["extractions"]) for r in rounds) / len(rounds)

    start_pool = rounds[0]["pool_before"]
    end_pool = rounds[-1].get("pool_next", rounds[-1]["final_pool"])
    if end_pool >= start_pool:
        trend = "stable/growing"
    elif end_pool >= start_pool * 0.5:
        trend = "declining"
    else:
        trend = "rapidly declining"

    violations = sum(
        1 for r in rounds
        if sum(r["extractions"]) > r["sustainability_threshold"]
    )

    parts = [
        f"[Summary of Months {first}-{last}]",
        f"Avg pool: ${avg_pool:.0f}",
        f"Avg total extraction: ${avg_total_ext:.1f}/round",
        f"Pool trend: {trend}",
        f"Sustainability violations: {violations}/{len(rounds)} months",
        f"Pool at end of period: ${end_pool}",
    ]

    if condition in (Condition.KCPR, Condition.KCPR_M, Condition.BCPR):
        avg_leader = sum(r["extractions"][3] for r in rounds) / len(rounds)
        label = "King" if condition != Condition.BCPR else "Boss"
        parts.append(f"Avg {label} extraction: {avg_leader:.1f}/round")

    return " | ".join(parts)


def format_history(
    rounds: List[Dict[str, Any]],
    condition: Condition,
    window: int = 3,
    compress: bool = True,
) -> str:
    # Build the history string injected into agent prompts.
    if not rounds:
        return "No previous months."

    fmt = _FORMATTERS[condition]

    if not compress or len(rounds) <= window:
        return "\n\n".join(fmt(r) for r in rounds)

    old = rounds[:-window]
    recent = rounds[-window:]

    parts: List[str] = [_compress_rounds(old, condition)]
    parts.extend(fmt(r) for r in recent)
    return "\n\n".join(parts)
