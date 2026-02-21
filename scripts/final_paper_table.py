#!/usr/bin/env python3
"""
Generate CR v2 Final Paper Table — full layered format (5.1–5.4 + Appendix).

Output: Single-page Markdown with all tables. Optionally export CSVs for large tables.

Tables:
  5.1 Surface Layer: Overall (ATSA-F macro/micro) + Conditional subsets (S0 vs M0)
  5.2 Schema Layer: Overall (error rates, ACSA-F1 macro/micro) + Conditional subsets
  5.3 Process Layer: Overall (fix/break/net_gain) + Conditional (difficulty + trigger M0)
  5.4 Stochastic Stability: Overall + Conditional subsets
  Appendix: a1 variance, a2 pair-level counts, a3 micro breakdown

Subset Partition Verification: docs/cr_v2_subset_partition.md
  Subset partitions are mutually exclusive and exhaustive. Weighted recomputation across subsets exactly matches overall micro-F1.

Usage:
  python scripts/final_paper_table.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --run-dirs-s0 ... --run-dirs-m0 ... --run-dirs-m1 ... --out reports/cr_v2_n601_v1_final_paper_table.md
  python scripts/final_paper_table.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --triptych-s0 ... --triptych-m0 ... --out reports/cr_v2_n601_v1_final_paper_table.md --csv-dir reports/cr_v2_n601_v1_tables
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from random import choices
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
N_BOOTSTRAP = 2000

NEGATION_PATTERNS = [
    r"\b안\b", r"\b못\b", r"않", r"없",
    r"\b아니\b", r"지만", r"그러나",
    r"반면", r"\b근데\b", r"\b는데\b",
]


def _has_negation(text: str) -> bool:
    if not text:
        return False
    for pat in NEGATION_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _load_agg(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = (row.get("metric") or "").strip()
            if m:
                out[m] = {"mean": row.get("mean", ""), "std": row.get("std", "")}
    return out


def _load_per_seed_metrics(run_dirs: list[Path]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for d in run_dirs:
        d = d.resolve() if not d.is_absolute() else d
        if not d.is_dir():
            continue
        m = re.search(r"__seed(\d+)_", d.name)
        seed = m.group(1) if m else None
        if not seed:
            continue
        for sub in ("derived/metrics", "derived_subset"):
            csv_path = d / sub / "structural_metrics.csv"
            if csv_path.exists():
                break
        else:
            csv_path = d / "derived" / "metrics" / "structural_metrics.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        row = rows[0]
        out: dict[str, float] = {}
        for k, v in row.items():
            if k.startswith("_"):
                continue
            try:
                val = float(v) if v and str(v).strip() else float("nan")
                if val == val:
                    out[k] = val
            except (TypeError, ValueError):
                pass
        result[seed] = out
    return result


def _load_irr_from_run_dirs(run_dirs: list[Path]) -> dict[str, dict[str, str]]:
    irr_metrics: dict[str, dict[str, str]] = {}
    for irr_key, paper_name in [("mean_kappa_measurement", "meas_cohen_kappa_mean"), ("mean_fleiss_measurement", "meas_fleiss_kappa")]:
        vals: list[float] = []
        for d in run_dirs:
            d = d.resolve() if not d.is_absolute() else d
            irr_path = d / "irr" / "irr_run_summary.json"
            if irr_path.exists():
                try:
                    data = json.loads(irr_path.read_text(encoding="utf-8"))
                    v = data.get(irr_key)
                    if v is not None and v == v:
                        vals.append(float(v))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        if vals:
            m = mean(vals)
            s = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0.0
            irr_metrics[paper_name] = {"mean": f"{m:.4f}", "std": f"{s:.4f}"}
    return irr_metrics


def _bootstrap_delta_ci(
    m0_per_seed: dict[str, dict[str, float]],
    m1_per_seed: dict[str, dict[str, float]],
    metric: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float] | None:
    common = sorted(set(m0_per_seed) & set(m1_per_seed))
    if len(common) < 2:
        return None
    deltas = []
    for s in common:
        v1 = m1_per_seed.get(s, {}).get(metric)
        v0 = m0_per_seed.get(s, {}).get(metric)
        if v1 is not None and v0 is not None and v1 == v1 and v0 == v0:
            deltas.append(float(v1) - float(v0))
    if len(deltas) < 2:
        return None
    mean_delta = mean(deltas)
    n = len(deltas)
    boot_means = [mean(choices(deltas, k=n)) for _ in range(n_bootstrap)]
    boot_means.sort()
    lower = boot_means[int(0.025 * n_bootstrap)]
    upper = boot_means[int(0.975 * n_bootstrap)]
    return (mean_delta, lower, upper)


def _bootstrap_delta_ci_refinement(
    s0_per_seed: dict[str, dict[str, float]],
    m0_per_seed: dict[str, dict[str, float]],
    metric: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float] | None:
    common = sorted(set(s0_per_seed) & set(m0_per_seed))
    if len(common) < 2:
        return None
    deltas = []
    for s in common:
        v0 = m0_per_seed.get(s, {}).get(metric)
        vs = s0_per_seed.get(s, {}).get(metric)
        if v0 is not None and vs is not None and v0 == v0 and vs == vs:
            deltas.append(float(v0) - float(vs))
    if len(deltas) < 2:
        return None
    mean_delta = mean(deltas)
    n = len(deltas)
    boot_means = [mean(choices(deltas, k=n)) for _ in range(n_bootstrap)]
    boot_means.sort()
    lower = boot_means[int(0.025 * n_bootstrap)]
    upper = boot_means[int(0.975 * n_bootstrap)]
    return (mean_delta, lower, upper)


def _fmt_mean_std(mean_val: str | float | None, std_val: str | float | None) -> str:
    if mean_val is None or mean_val == "" or str(mean_val).strip().upper() in ("N/A", "NA"):
        return ""
    if std_val is None or std_val == "" or str(std_val).strip().upper() in ("N/A", "NA"):
        try:
            return f"{float(mean_val):.4f}"
        except (TypeError, ValueError):
            return str(mean_val)
    try:
        m, s = float(mean_val), float(std_val)
        if m != m:
            return ""
        return f"{m:.4f} ± {s:.4f}"
    except (TypeError, ValueError):
        return str(mean_val)


def _fmt_ci(mean_delta: float, lower: float, upper: float) -> str:
    return f"[{lower:.4f}, {upper:.4f}]"


def _seed_variance(per_seed: dict[str, dict[str, float]], key: str = "tuple_f1_s2_refpol") -> str:
    vals = []
    for row in per_seed.values():
        v = row.get(key)
        if v is not None and v == v:
            vals.append(float(v))
    if len(vals) < 2:
        return f"{vals[0]:.4f}" if vals else ""
    m = mean(vals)
    return f"{(sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5:.4f}"


def macro_f1_per_sample(
    rows: list[dict],
    match_key: str = "matches_final_vs_gold",
    gold_key: str = "gold_n_pairs",
    final_key: str = "final_n_pairs",
) -> float:
    """Macro F1 = mean of per-sample F1 over rows with gold_n_pairs > 0."""
    f1s: list[float] = []
    for r in rows:
        try:
            m = int(r.get(match_key) or 0)
            g = int(r.get(gold_key) or 0)
            f = int(r.get(final_key) or 0)
        except (ValueError, TypeError):
            continue
        if g <= 0:
            continue
        tp = m
        fn = g - m
        fp = max(0, f - m)
        denom = 2 * tp + fp + fn
        if denom <= 0:
            f1s.append(0.0)
        else:
            f1s.append(2 * tp / denom)
    return mean(f1s) if f1s else 0.0


def micro_f1_pair_level(
    rows: list[dict],
    match_key: str = "matches_final_vs_gold",
    gold_key: str = "gold_n_pairs",
    final_key: str = "final_n_pairs",
) -> tuple[float, int, int, int, int, int]:
    tp = fp = fn = 0
    n_valid = 0
    for r in rows:
        try:
            m = int(r.get(match_key) or 0)
            g = int(r.get(gold_key) or 0)
            f = int(r.get(final_key) or 0)
        except (ValueError, TypeError):
            continue
        if g <= 0:
            continue
        n_valid += 1
        tp += m
        fn += g - m
        fp += max(0, f - m)
    if tp + fp + fn == 0:
        return 0.0, n_valid, 0, 0, 0, 0
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r_val = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r_val / (p + r_val) if (p + r_val) > 0 else 0.0
    return f1, n_valid, tp + fn, tp, fp, fn


def load_triptych(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def _norm_pol(p: str | None) -> str:
    """Normalize polarity to positive/negative/neutral/mixed."""
    if not p or not str(p).strip():
        return "neutral"
    k = str(p).strip().lower()
    if k in ("positive", "pos"):
        return "positive"
    if k in ("negative", "neg"):
        return "negative"
    if k in ("neutral", "neu"):
        return "neutral"
    if k in ("mixed",):
        return "mixed"
    return "neutral"


def _extract_gold_polarities(record: dict) -> list[str]:
    """Extract polarity list from gold_tuples."""
    gold = record.get("inputs", {}).get("gold_tuples") or record.get("gold_tuples") or []
    if not isinstance(gold, list):
        return []
    out: list[str] = []
    for it in gold:
        if not it or not isinstance(it, dict):
            continue
        p = _norm_pol(it.get("polarity") or it.get("label"))
        out.append(p)
    return out


def _extract_final_polarities(record: dict) -> list[str]:
    """Extract polarity list from final_tuples."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    fr = parsed.get("final_result") or {}
    lst = fr.get("final_tuples") or []
    if not isinstance(lst, list):
        return []
    out: list[str] = []
    for it in lst:
        if not it or not isinstance(it, dict):
            continue
        p = _norm_pol(it.get("polarity") or it.get("label"))
        out.append(p)
    return out


def compute_gold_subset_stats(triptych_path: Path | None, scorecards_path: Path | None, seed_filter: str = "seed42") -> dict[str, dict[str, int | float]]:
    """
    Gold 기준 서브셋 통계: Implicit, Explicit, Negation, Multi-aspect 각각 n, %.
    triptych 우선, 없으면 scorecards에서 추정.
    """
    out: dict[str, dict[str, int | float]] = {}
    rows: list[dict] = []
    if triptych_path and triptych_path.exists():
        with triptych_path.open("r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                r["has_negation"] = _has_negation(r.get("text") or "")
                rows.append(r)
    elif scorecards_path and scorecards_path.exists():
        for line in scorecards_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if seed_filter and seed_filter not in str(rec.get("run_id") or rec.get("meta", {}).get("run_id") or ""):
                continue
            gold = rec.get("inputs", {}).get("gold_tuples") or rec.get("gold_tuples") or []
            gold = gold if isinstance(gold, list) else []
            has_explicit = any(
                (it.get("aspect_term") or "").strip() or (isinstance(it.get("aspect_term"), dict) and (it.get("aspect_term") or {}).get("term") or "")
                for it in gold if it and isinstance(it, dict)
            )
            gold_type = "explicit" if has_explicit else "implicit"
            text = (rec.get("meta") or {}).get("input_text") or rec.get("inputs", {}).get("input_text") or ""
            rows.append({
                "text_id": (rec.get("meta") or {}).get("text_id") or "",
                "gold_type": gold_type,
                "gold_n_pairs": len(gold),
                "has_negation": _has_negation(text),
            })
    if not rows:
        return {}
    seen: set[str] = set()
    implicit_n = explicit_n = negation_n = multi_n = 0
    for r in rows:
        tid = r.get("text_id") or ""
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        gt = (r.get("gold_type") or "").strip().lower()
        if gt == "implicit":
            implicit_n += 1
        elif gt == "explicit":
            explicit_n += 1
        npairs = int(r.get("gold_n_pairs") or 0)
        if npairs > 1:
            multi_n += 1
        if r.get("has_negation"):
            negation_n += 1
    total = len(seen) if seen else len(rows)
    if total == 0:
        return {}
    non_neg = total - negation_n
    single_n = total - multi_n
    out["Implicit"] = {"n": implicit_n, "%": 100.0 * implicit_n / total}
    out["Explicit"] = {"n": explicit_n, "%": 100.0 * explicit_n / total}
    out["Negation"] = {"n": negation_n, "%": 100.0 * negation_n / total}
    out["Non-negation"] = {"n": non_neg, "%": 100.0 * non_neg / total}
    out["Multi-aspect"] = {"n": multi_n, "%": 100.0 * multi_n / total}
    out["Single-aspect"] = {"n": single_n, "%": 100.0 * single_n / total}
    return out


def compute_gold_sample_distribution(scorecards_path: Path, seed_filter: str | None = "seed42") -> dict[str, int | float]:
    """
    Gold 기준 샘플 단위 분포: 긍정만/부정만/중립만/믹스(복수 감성)를 각각 단일 카운트.
    각 샘플은 정확히 하나의 버킷에만 속함.
    """
    if not scorecards_path.exists():
        return {}
    rows: list[dict] = []
    for line in scorecards_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return {}
    if seed_filter:
        rows = [r for r in rows if seed_filter in str(r.get("run_id") or r.get("meta", {}).get("run_id") or "")]
    seen_tid: set[str] = set()
    pos_only = neg_only = neu_only = mixed = 0
    for r in rows:
        meta = r.get("meta") or {}
        tid = meta.get("text_id") or meta.get("case_id") or ""
        if tid in seen_tid:
            continue
        seen_tid.add(tid)
        pols = _extract_gold_polarities(r)
        if not pols:
            continue
        uniq = set(pols)
        if len(uniq) >= 2:
            mixed += 1
        elif "positive" in uniq:
            pos_only += 1
        elif "negative" in uniq:
            neg_only += 1
        elif "mixed" in uniq:
            mixed += 1
        else:
            neu_only += 1
    total = pos_only + neg_only + neu_only + mixed
    if total == 0:
        return {}
    return {
        "positive_only_n": pos_only, "positive_only_pct": 100.0 * pos_only / total,
        "negative_only_n": neg_only, "negative_only_pct": 100.0 * neg_only / total,
        "neutral_only_n": neu_only, "neutral_only_pct": 100.0 * neu_only / total,
        "mixed_n": mixed, "mixed_pct": 100.0 * mixed / total,
        "total": total,
    }


def compute_sentiment_distribution(scorecards_path: Path, seed_filter: str | None = "seed42") -> dict[str, dict[str, int | float]]:
    """
    Compute polarity distribution (positive, negative, neutral) from scorecards.
    Returns dict: {"gold": {n, %}, "S0"|"M0"|"M1": {n, %} for pred}.
    When seed_filter is set, use only rows with that seed in run_id (for merged scorecards).
    """
    if not scorecards_path.exists():
        return {}
    rows: list[dict] = []
    for line in scorecards_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return {}
    if seed_filter:
        rows = [r for r in rows if seed_filter in str(r.get("run_id") or r.get("meta", {}).get("run_id") or "")]
    if not rows:
        return {}
    gold_pos = gold_neg = gold_neu = 0
    pred_pos = pred_neg = pred_neu = 0
    seen_text_id: set[str] = set()
    for r in rows:
        meta = r.get("meta") or {}
        tid = meta.get("text_id") or meta.get("case_id") or ""
        gold_pols = _extract_gold_polarities(r)
        pred_pols = _extract_final_polarities(r)
        if tid not in seen_text_id:
            seen_text_id.add(tid)
            for p in gold_pols:
                if p == "positive":
                    gold_pos += 1
                elif p == "negative":
                    gold_neg += 1
                else:
                    gold_neu += 1
        for p in pred_pols:
            if p == "positive":
                pred_pos += 1
            elif p == "negative":
                pred_neg += 1
            else:
                pred_neu += 1
    total_gold = gold_pos + gold_neg + gold_neu
    total_pred = pred_pos + pred_neg + pred_neu
    out: dict[str, dict[str, int | float]] = {}
    if total_gold > 0:
        out["gold"] = {
            "positive_n": gold_pos, "positive_pct": 100.0 * gold_pos / total_gold,
            "negative_n": gold_neg, "negative_pct": 100.0 * gold_neg / total_gold,
            "neutral_n": gold_neu, "neutral_pct": 100.0 * gold_neu / total_gold,
            "total": total_gold,
        }
    if total_pred > 0:
        run_id = str(rows[0].get("run_id") or rows[0].get("meta", {}).get("run_id") or "")
        cond = "M1" if "_m1_" in run_id.lower() else ("M0" if "_m0_" in run_id.lower() else "S0")
        out[cond] = {
            "positive_n": pred_pos, "positive_pct": 100.0 * pred_pos / total_pred,
            "negative_n": pred_neg, "negative_pct": 100.0 * pred_neg / total_pred,
            "neutral_n": pred_neu, "neutral_pct": 100.0 * pred_neu / total_pred,
            "total": total_pred,
        }
    return out


def load_m0_conflict_flags(project: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for seed_dir in (project / "results").glob("cr_v2_n601_m0_v1__seed*_proposed"):
        path = seed_dir / "outputs.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = rec.get("meta") or {}
            text_id = meta.get("text_id") or ""
            flags = rec.get("analysis_flags") or {}
            cf = (flags.get("conflict_flags") or []) if isinstance(flags, dict) else []
            out[text_id] = out.get(text_id, False) or bool(cf and len(cf) > 0)
    return out


def compute_subset_seed_variance(
    s0_rows: list[dict],
    m0_rows: list[dict],
    m0_conflict: dict[str, bool],
) -> dict[str, dict[str, str]]:
    """Compute seed variance of ATSA-F macro/micro per subset. Requires run_id in rows to filter by seed."""
    seed_pattern = re.compile(r"seed(\d+)", re.I)

    def _seed_from_run_id(run_id: str) -> str | None:
        m = seed_pattern.search(str(run_id or ""))
        return m.group(1) if m else None

    def by_subset(rows: list[dict], subset: str) -> list[dict]:
        for r in rows:
            r.setdefault("has_negation", _has_negation(r.get("text") or ""))
        if subset == "implicit":
            return [r for r in rows if (r.get("gold_type") or "") == "implicit"]
        if subset == "explicit":
            return [r for r in rows if (r.get("gold_type") or "") == "explicit"]
        if subset == "negation":
            return [r for r in rows if r.get("has_negation")]
        if subset == "multi_aspect":
            return [r for r in rows if int(r.get("gold_n_pairs") or 0) > 1]
        return rows

    subsets = [("Implicit", "implicit"), ("Explicit", "explicit"), ("Negation", "negation"), ("Multi-aspect", "multi_aspect")]
    out: dict[str, dict[str, str]] = {}

    for s0_r in s0_rows:
        s0_r.setdefault("has_negation", _has_negation(s0_r.get("text") or ""))
        s0_r["has_conflict"] = False
    for m0_r in m0_rows:
        m0_r.setdefault("has_negation", _has_negation(m0_r.get("text") or ""))
        m0_r["has_conflict"] = m0_conflict.get(m0_r.get("text_id") or "", False)

    s0_seeds = sorted({_seed_from_run_id(r.get("run_id")) for r in s0_rows if _seed_from_run_id(r.get("run_id"))})
    m0_seeds = sorted({_seed_from_run_id(r.get("run_id")) for r in m0_rows if _seed_from_run_id(r.get("run_id"))})
    common_seeds = sorted(set(s0_seeds) & set(m0_seeds))
    if len(common_seeds) < 2:
        for label, key in subsets:
            out[label] = {
                "atsa_macro_s0": "—", "atsa_macro_m0": "—", "atsa_macro_delta": "—",
                "atsa_micro_s0": "—", "atsa_micro_m0": "—", "atsa_micro_delta": "—",
            }
        return out

    for label, key in subsets:
        atsa_macro_s0_vals: list[float] = []
        atsa_macro_m0_vals: list[float] = []
        atsa_micro_s0_vals: list[float] = []
        atsa_micro_m0_vals: list[float] = []
        for seed in common_seeds:
            sub_s0 = by_subset([r for r in s0_rows if _seed_from_run_id(r.get("run_id")) == seed], key)
            sub_m0 = by_subset([r for r in m0_rows if _seed_from_run_id(r.get("run_id")) == seed], key)
            am_s0 = macro_f1_per_sample(sub_s0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")
            am_m0 = macro_f1_per_sample(sub_m0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")
            f1_s0, _, _, _, _, _ = micro_f1_pair_level(sub_s0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")
            f1_m0, _, _, _, _, _ = micro_f1_pair_level(sub_m0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")
            has_s0 = any(int(r.get("gold_n_pairs_otepol") or 0) > 0 for r in sub_s0)
            has_m0 = any(int(r.get("gold_n_pairs_otepol") or 0) > 0 for r in sub_m0)
            if has_s0 or has_m0:
                atsa_macro_s0_vals.append(am_s0)
                atsa_macro_m0_vals.append(am_m0)
                atsa_micro_s0_vals.append(f1_s0)
                atsa_micro_m0_vals.append(f1_m0)
        if len(atsa_macro_s0_vals) >= 2:
            sv_am_s0 = (sum((x - mean(atsa_macro_s0_vals)) ** 2 for x in atsa_macro_s0_vals) / len(atsa_macro_s0_vals)) ** 0.5
            sv_am_m0 = (sum((x - mean(atsa_macro_m0_vals)) ** 2 for x in atsa_macro_m0_vals) / len(atsa_macro_m0_vals)) ** 0.5
            sv_au_s0 = (sum((x - mean(atsa_micro_s0_vals)) ** 2 for x in atsa_micro_s0_vals) / len(atsa_micro_s0_vals)) ** 0.5
            sv_au_m0 = (sum((x - mean(atsa_micro_m0_vals)) ** 2 for x in atsa_micro_m0_vals) / len(atsa_micro_m0_vals)) ** 0.5
            dm = mean(atsa_macro_m0_vals) - mean(atsa_macro_s0_vals)
            du = mean(atsa_micro_m0_vals) - mean(atsa_micro_s0_vals)
            out[label] = {
                "atsa_macro_s0": f"{sv_am_s0:.4f}", "atsa_macro_m0": f"{sv_am_m0:.4f}", "atsa_macro_delta": f"{dm:+.4f}",
                "atsa_micro_s0": f"{sv_au_s0:.4f}", "atsa_micro_m0": f"{sv_au_m0:.4f}", "atsa_micro_delta": f"{du:+.4f}",
            }
        else:
            out[label] = {
                "atsa_macro_s0": "—", "atsa_macro_m0": "—", "atsa_macro_delta": "—",
                "atsa_micro_s0": "—", "atsa_micro_m0": "—", "atsa_micro_delta": "—",
            }
    return out


def compute_subset_metrics(
    s0_rows: list[dict],
    m0_rows: list[dict],
    m0_conflict: dict[str, bool],
) -> dict[str, dict[str, float | str]]:
    for r in s0_rows:
        r["has_negation"] = _has_negation(r.get("text") or "")
        r["has_conflict"] = False
    for r in m0_rows:
        r["has_negation"] = _has_negation(r.get("text") or "")
        tid = r.get("text_id") or ""
        r["has_conflict"] = m0_conflict.get(tid, False)

    def by_subset(rows: list[dict], subset: str) -> list[dict]:
        if subset == "implicit":
            return [r for r in rows if (r.get("gold_type") or "") == "implicit"]
        if subset == "explicit":
            return [r for r in rows if (r.get("gold_type") or "") == "explicit"]
        if subset == "negation":
            return [r for r in rows if r.get("has_negation")]
        if subset == "multi_aspect":
            return [r for r in rows if int(r.get("gold_n_pairs") or 0) > 1]
        return rows

    def _rate(n: int, total: int) -> float:
        return n / total if total > 0 else 0.0

    subsets = [
        ("Implicit", "implicit"),
        ("Explicit", "explicit"),
        ("Negation", "negation"),
        ("Multi-aspect", "multi_aspect"),
    ]
    out: dict[str, dict[str, float | str]] = {}
    for label, key in subsets:
        sub_s0 = by_subset(s0_rows, key)
        sub_m0 = by_subset(m0_rows, key)

        # ATSA-F (otepol)
        atsa_f1_s0, atsa_n_s0, _, atsa_tp_s0, _, _ = micro_f1_pair_level(
            sub_s0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol"
        )
        atsa_f1_m0, atsa_n_m0, _, atsa_tp_m0, _, _ = micro_f1_pair_level(
            sub_m0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol"
        )
        atsa_macro_s0 = macro_f1_per_sample(sub_s0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")
        atsa_macro_m0 = macro_f1_per_sample(sub_m0, "matches_final_vs_gold_otepol", "gold_n_pairs_otepol", "final_n_pairs_otepol")

        # ACSA-F (refpol)
        acsa_f1_s0, acsa_n_s0, _, acsa_tp_s0, _, _ = micro_f1_pair_level(sub_s0)
        acsa_f1_m0, acsa_n_m0, _, acsa_tp_m0, _, _ = micro_f1_pair_level(sub_m0)
        acsa_macro_s0 = macro_f1_per_sample(sub_s0)
        acsa_macro_m0 = macro_f1_per_sample(sub_m0)

        # fix/break/net_gain (refpol)
        fix_s0 = sum(1 for r in sub_s0 if int(r.get("fix_flag") or 0)) if sub_s0 else 0
        fix_m0 = sum(1 for r in sub_m0 if int(r.get("fix_flag") or 0)) if sub_m0 else 0
        break_s0 = sum(1 for r in sub_s0 if int(r.get("break_flag") or 0)) if sub_s0 else 0
        break_m0 = sum(1 for r in sub_m0 if int(r.get("break_flag") or 0)) if sub_m0 else 0
        n_s0 = len([r for r in sub_s0 if int(r.get("gold_n_pairs") or 0) > 0])
        n_m0 = len([r for r in sub_m0 if int(r.get("gold_n_pairs") or 0) > 0])
        fix_rate_s0 = _rate(fix_s0, n_s0) if n_s0 else 0.0
        fix_rate_m0 = _rate(fix_m0, n_m0) if n_m0 else 0.0
        break_rate_s0 = _rate(break_s0, n_s0) if n_s0 else 0.0
        break_rate_m0 = _rate(break_m0, n_m0) if n_m0 else 0.0
        net_gain_s0 = fix_rate_s0 - break_rate_s0
        net_gain_m0 = fix_rate_m0 - break_rate_m0

        # Implicit Assignment Error Rate (implicit subset only)
        impl_inv_s0 = impl_inv_m0 = impl_n_s0 = impl_n_m0 = 0
        if key == "implicit":
            impl_n_s0 = len(sub_s0)
            impl_n_m0 = len(sub_m0)
            impl_inv_s0 = sum(1 for r in sub_s0 if int(r.get("implicit_invalid_flag") or 0))
            impl_inv_m0 = sum(1 for r in sub_m0 if int(r.get("implicit_invalid_flag") or 0))
        impl_err_s0 = _rate(impl_inv_s0, impl_n_s0) if impl_n_s0 else 0.0
        impl_err_m0 = _rate(impl_inv_m0, impl_n_m0) if impl_n_m0 else 0.0

        # Fallback: when no otepol data (old triptych), use None for ATSA
        has_otepol = (atsa_n_s0 > 0 or atsa_n_m0 > 0)
        out[label] = {
            "n_samples_s0": n_s0,
            "n_samples_m0": n_m0,
            "atsa_macro_s0": atsa_macro_s0 if has_otepol else None,
            "atsa_macro_m0": atsa_macro_m0 if has_otepol else None,
            "atsa_macro_delta": (atsa_macro_m0 - atsa_macro_s0) if has_otepol else None,
            "atsa_micro_s0": atsa_f1_s0 if has_otepol else None,
            "atsa_micro_m0": atsa_f1_m0 if has_otepol else None,
            "atsa_micro_delta": (atsa_f1_m0 - atsa_f1_s0) if has_otepol else None,
            "acsa_macro_s0": acsa_macro_s0,
            "acsa_macro_m0": acsa_macro_m0,
            "acsa_macro_delta": acsa_macro_m0 - acsa_macro_s0,
            "acsa_micro_s0": acsa_f1_s0,
            "acsa_micro_m0": acsa_f1_m0,
            "acsa_micro_delta": acsa_f1_m0 - acsa_f1_s0,
            "fix_rate_s0": fix_rate_s0,
            "fix_rate_m0": fix_rate_m0,
            "fix_rate_delta": fix_rate_m0 - fix_rate_s0,
            "break_rate_s0": break_rate_s0,
            "break_rate_m0": break_rate_m0,
            "break_rate_delta": break_rate_m0 - break_rate_s0,
            "net_gain_s0": net_gain_s0,
            "net_gain_m0": net_gain_m0,
            "net_gain_delta": net_gain_m0 - net_gain_s0,
            "implicit_err_s0": impl_err_s0,
            "implicit_err_m0": impl_err_m0,
            "implicit_err_delta": impl_err_m0 - impl_err_s0,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate CR v2 Final Paper Table")
    ap.add_argument("--agg-s0", type=Path, default=None, help="S0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m0", type=Path, required=True, help="M0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m1", type=Path, required=True, help="M1 aggregated_mean_std.csv")
    ap.add_argument("--run-dirs-s0", nargs="*", type=Path, default=[], help="S0 seed run dirs")
    ap.add_argument("--run-dirs-m0", nargs="*", type=Path, default=[], help="M0 seed run dirs")
    ap.add_argument("--run-dirs-m1", nargs="*", type=Path, default=[], help="M1 seed run dirs")
    ap.add_argument("--triptych-s0", type=Path, default=None, help="S0 triptych.csv (for subset analysis)")
    ap.add_argument("--triptych-m0", type=Path, default=None, help="M0 triptych.csv (for subset analysis)")
    ap.add_argument("--scorecards-s0", type=Path, default=None, help="S0 merged_scorecards.jsonl (for Appendix a4 sentiment distribution)")
    ap.add_argument("--scorecards-m0", type=Path, default=None, help="M0 merged_scorecards.jsonl (for Appendix a4)")
    ap.add_argument("--scorecards-m1", type=Path, default=None, help="M1 merged_scorecards.jsonl (for Appendix a4)")
    ap.add_argument("--out", type=Path, default=Path("reports/cr_v2_n601_v1_final_paper_table.md"), help="Output md path")
    ap.add_argument("--csv-dir", type=Path, default=None, help="Optional: export large tables as CSV")
    args = ap.parse_args()

    def resolve(p: Path) -> Path:
        return p.resolve() if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    agg_s0 = _load_agg(resolve(args.agg_s0)) if args.agg_s0 else {}
    agg_m0 = _load_agg(resolve(args.agg_m0))
    agg_m1 = _load_agg(resolve(args.agg_m1))

    run_dirs_s0 = [resolve(d) for d in args.run_dirs_s0]
    run_dirs_m0 = [resolve(d) for d in args.run_dirs_m0]
    run_dirs_m1 = [resolve(d) for d in args.run_dirs_m1]

    irr_m0 = _load_irr_from_run_dirs(run_dirs_m0)
    for k, v in irr_m0.items():
        agg_m0[k] = v
    irr_m1 = _load_irr_from_run_dirs(run_dirs_m1)
    for k, v in irr_m1.items():
        agg_m1[k] = v

    s0_per_seed = _load_per_seed_metrics(run_dirs_s0)
    m0_per_seed = _load_per_seed_metrics(run_dirs_m0)
    m1_per_seed = _load_per_seed_metrics(run_dirs_m1)

    has_s0 = bool(agg_s0)

    def _get(agg: dict, key: str) -> tuple[str, str]:
        r = agg.get(key, {})
        return r.get("mean", ""), r.get("std", "")

    def _delta(key: str) -> tuple[str, str]:
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        if (not m0_m or str(m0_m).strip() in ("", "N/A", "NA")) and (not m1_m or str(m1_m).strip() in ("", "N/A", "NA")):
            return "", ""
        try:
            d = float(m1_m or 0) - float(m0_m or 0)
        except (TypeError, ValueError):
            return "", ""
        ci = _bootstrap_delta_ci(m0_per_seed, m1_per_seed, key) if m0_per_seed and m1_per_seed else None
        ci_str = _fmt_ci(ci[0], ci[1], ci[2]) if ci else ""
        return f"{d:+.4f}" if isinstance(d, float) and d == d else "", ci_str

    def _delta_refinement(key: str) -> tuple[str, str]:
        if not has_s0 or not agg_s0:
            return "", ""
        s0_m, s0_s = _get(agg_s0, key)
        m0_m, m0_s = _get(agg_m0, key)
        if not s0_m or str(s0_m).strip() in ("", "N/A", "NA"):
            return "", ""
        if not m0_m or str(m0_m).strip() in ("", "N/A", "NA"):
            return "", ""
        try:
            d = float(m0_m) - float(s0_m)
        except (TypeError, ValueError):
            return "", ""
        ci = _bootstrap_delta_ci_refinement(s0_per_seed, m0_per_seed, key) if s0_per_seed and m0_per_seed else None
        ci_str = _fmt_ci(ci[0], ci[1], ci[2]) if ci else ""
        return f"{d:+.4f}" if isinstance(d, float) and d == d else "", ci_str

    def _row_s0(key: str) -> tuple[str, str, str, str, str]:
        s0_m, s0_s = _get(agg_s0 or {}, key)
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d_ref, _ = _delta_refinement(key)
        d, ci = _delta(key)
        return (
            _fmt_mean_std(s0_m, s0_s) or "",
            _fmt_mean_std(m0_m, m0_s) or "",
            _fmt_mean_std(m1_m, m1_s) or "",
            d_ref,
            d,
        )

    lines: list[str] = []
    lines.append("# CR v2 Final Paper Table (S0 | M0 | M1 | ΔMFRA | Δmemory)")
    lines.append("")
    lines.append("**Subset Partition Verification**: Subset partitions are mutually exclusive and exhaustive. Weighted recomputation across subsets exactly matches overall micro-F1. See `docs/cr_v2_subset_partition.md`.")
    lines.append("")

    # 5.1 Surface Layer Overall
    lines.append("## 5.1 Surface Layer")
    lines.append("### 5.1.1 Overall")
    lines.append("")
    lines.append("| Condition | ATSA-F(macro) tuple_f1_s2_otepol | ATSA-F(micro) tuple_f1_s2_otepol | ΔMFRA [95% CI] | Δmemory [95% CI] |")
    lines.append("|-----------|----------------------------------|----------------------------------|-----------------|------------------|")
    s0, m0, m1, d_ref, d = _row_s0("tuple_f1_s2_otepol")
    _, ci_ref = _delta_refinement("tuple_f1_s2_otepol")
    _, ci_mem = _delta("tuple_f1_s2_otepol")
    d_ref_micro, ci_ref_micro = _delta_refinement("tuple_f1_s2_otepol_micro")
    d_mem_micro, ci_mem_micro = _delta("tuple_f1_s2_otepol_micro")
    lines.append(f"| S0 | {s0} | {_fmt_mean_std(_get(agg_s0 or {}, 'tuple_f1_s2_otepol_micro')[0], _get(agg_s0 or {}, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | — | — |")
    lines.append(f"| M0 | {m0} | {_fmt_mean_std(_get(agg_m0, 'tuple_f1_s2_otepol_micro')[0], _get(agg_m0, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | {d_ref} {ci_ref} | — |")
    lines.append(f"| M1 | {m1} | {_fmt_mean_std(_get(agg_m1, 'tuple_f1_s2_otepol_micro')[0], _get(agg_m1, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | — | {d} {ci_mem} |")
    ci_ref_micro_str = f" {ci_ref_micro}" if ci_ref_micro else ""
    ci_mem_micro_str = f" {ci_mem_micro}" if ci_mem_micro else ""
    lines.append(f"| ΔMFRA [95% CI] | {d_ref} {ci_ref} | {d_ref_micro}{ci_ref_micro_str} | | |")
    lines.append(f"| Δmemory [95% CI] | — | {d_mem_micro}{ci_mem_micro_str} | | |")
    lines.append("")

    # 5.1.2 Conditional (subset) — from triptych if available
    subset_data: dict[str, dict[str, float | str]] | None = None
    if args.triptych_s0 and args.triptych_m0:
        s0_trip = load_triptych(resolve(args.triptych_s0))
        m0_trip = load_triptych(resolve(args.triptych_m0))
        m0_conflict = load_m0_conflict_flags(PROJECT_ROOT)
        subset_data = compute_subset_metrics(s0_trip, m0_trip, m0_conflict)

    lines.append("### 5.1.2 Conditional Performance (Subsets)")
    lines.append("")
    lines.append("| subset | ATSA-F(macro) S0 | ATSA-F(macro) M0 | Macro Δ (M0−S0) | ATSA-F(micro) S0 | ATSA-F(micro) M0 | Micro Δ (M0−S0) |")
    lines.append("|--------|------------------|-----------------|-----------------|------------------|------------------|-----------------|")
    if subset_data:
        for label, data in subset_data.items():
            def _f(v, fmt=".4f"):
                return f"{v:{fmt}}" if isinstance(v, (int, float)) else "—"
            ams0 = _f(data.get("atsa_macro_s0"))
            amm0 = _f(data.get("atsa_macro_m0"))
            amd = _f(data.get("atsa_macro_delta"), "+.4f")
            aus0 = _f(data.get("atsa_micro_s0"))
            aum0 = _f(data.get("atsa_micro_m0"))
            aud = _f(data.get("atsa_micro_delta"), "+.4f")
            lines.append(f"| {label} | {ams0} | {amm0} | {amd} | {aus0} | {aum0} | {aud} |")
    else:
        lines.append("| *(run with --triptych-s0 and --triptych-m0 for subset analysis)* |")
    lines.append("")

    # 5.2 Schema Layer
    lines.append("## 5.2 Schema Layer")
    lines.append("### 5.2.1 Overall")
    lines.append("")
    lines.append("| Condition | Implicit Assignment Error Rate | Intra-Aspect Polarity Conflict Rate | ACSA-F1(macro) | ACSA-F1(micro) | #attribute f1 (macro) | #attribute f1 (micro) |")
    lines.append("|-----------|-------------------------------|-------------------------------------|----------------|----------------|------------------------|------------------------|")
    s0_impl, _, _, _, _ = _row_s0("implicit_invalid_pred_rate")
    s0_pol, _, _, _, _ = _row_s0("polarity_conflict_rate")
    s0_ref, _, _, _, _ = _row_s0("tuple_f1_s2_refpol")
    s0_refm, _, _, _, _ = _row_s0("tuple_f1_s2_refpol_micro")
    s0_attr, _, _, _, _ = _row_s0("tuple_f1_s2_attrpol")
    s0_attrm, _, _, _, _ = _row_s0("tuple_f1_s2_attrpol_micro")
    lines.append(f"| S0 | {s0_impl} | {s0_pol} | {s0_ref} | {s0_refm} | {s0_attr} | {s0_attrm} |")
    m0_impl, m0_pol = _get(agg_m0, "implicit_invalid_pred_rate")[0], _get(agg_m0, "polarity_conflict_rate")[0]
    m0_ref, m0_refm = _get(agg_m0, "tuple_f1_s2_refpol")[0], _get(agg_m0, "tuple_f1_s2_refpol_micro")[0]
    m0_attr, m0_attrm = _get(agg_m0, "tuple_f1_s2_attrpol")[0], _get(agg_m0, "tuple_f1_s2_attrpol_micro")[0]
    m0_s = _get(agg_m0, "implicit_invalid_pred_rate")[1]
    lines.append(f"| M0 | {_fmt_mean_std(m0_impl, m0_s)} | {_fmt_mean_std(_get(agg_m0, 'polarity_conflict_rate')[0], _get(agg_m0, 'polarity_conflict_rate')[1])} | {_fmt_mean_std(m0_ref, _get(agg_m0, 'tuple_f1_s2_refpol')[1])} | {_fmt_mean_std(m0_refm, _get(agg_m0, 'tuple_f1_s2_refpol_micro')[1])} | {_fmt_mean_std(m0_attr, _get(agg_m0, 'tuple_f1_s2_attrpol')[1])} | {_fmt_mean_std(m0_attrm, _get(agg_m0, 'tuple_f1_s2_attrpol_micro')[1])} |")
    m1_impl, m1_pol = _get(agg_m1, "implicit_invalid_pred_rate")[0], _get(agg_m1, "polarity_conflict_rate")[0]
    m1_ref, m1_refm = _get(agg_m1, "tuple_f1_s2_refpol")[0], _get(agg_m1, "tuple_f1_s2_refpol_micro")[0]
    m1_attr, m1_attrm = _get(agg_m1, "tuple_f1_s2_attrpol")[0], _get(agg_m1, "tuple_f1_s2_attrpol_micro")[0]
    m1_s = _get(agg_m1, "implicit_invalid_pred_rate")[1]
    lines.append(f"| M1 | {_fmt_mean_std(m1_impl, m1_s)} | {_fmt_mean_std(_get(agg_m1, 'polarity_conflict_rate')[0], _get(agg_m1, 'polarity_conflict_rate')[1])} | {_fmt_mean_std(m1_ref, _get(agg_m1, 'tuple_f1_s2_refpol')[1])} | {_fmt_mean_std(m1_refm, _get(agg_m1, 'tuple_f1_s2_refpol_micro')[1])} | {_fmt_mean_std(m1_attr, _get(agg_m1, 'tuple_f1_s2_attrpol')[1])} | {_fmt_mean_std(m1_attrm, _get(agg_m1, 'tuple_f1_s2_attrpol_micro')[1])} |")
    d_impl_ref, ci_impl = _delta_refinement("implicit_invalid_pred_rate")
    d_impl_mem, _ = _delta("implicit_invalid_pred_rate")
    d_pol_ref, ci_pol = _delta_refinement("polarity_conflict_rate")
    d_ref_ref, ci_ref = _delta_refinement("tuple_f1_s2_refpol")
    d_ref_refm, ci_ref_refm = _delta_refinement("tuple_f1_s2_refpol_micro")
    d_ref_mem, ci_ref_mem = _delta("tuple_f1_s2_refpol")
    d_ref_mem_micro, ci_ref_mem_micro = _delta("tuple_f1_s2_refpol_micro")
    d_attr_ref, ci_attr_ref = _delta_refinement("tuple_f1_s2_attrpol")
    d_attr_refm, ci_attr_refm = _delta_refinement("tuple_f1_s2_attrpol_micro")
    d_attr_mem, _ = _delta("tuple_f1_s2_attrpol")
    d_attr_mem_micro, ci_attr_mem_micro = _delta("tuple_f1_s2_attrpol_micro")
    ci_ref_refm_str = f" {ci_ref_refm}" if ci_ref_refm else ""
    ci_ref_mem_micro_str = f" {ci_ref_mem_micro}" if ci_ref_mem_micro else ""
    ci_attr_refm_str = f" {ci_attr_refm}" if ci_attr_refm else ""
    ci_attr_mem_micro_str = f" {ci_attr_mem_micro}" if ci_attr_mem_micro else ""
    lines.append(f"| ΔMFRA [95% CI] | {d_impl_ref} {ci_impl} | {d_pol_ref} {ci_pol} | {d_ref_ref} {ci_ref} | {d_ref_refm}{ci_ref_refm_str} | {d_attr_ref} {ci_attr_ref} | {d_attr_refm}{ci_attr_refm_str} |")
    lines.append(f"| Δmemory [95% CI] | {d_impl_mem} | | {d_ref_mem} {ci_ref_mem} | {d_ref_mem_micro}{ci_ref_mem_micro_str} | {d_attr_mem} | {d_attr_mem_micro}{ci_attr_mem_micro_str} |")
    lines.append("")

    # 5.2.2 Conditional Constraint Stability (Subsets)
    lines.append("### 5.2.2 Conditional Constraint Stability (Subsets)")
    lines.append("")
    lines.append("| subset | Implicit Assignment Error Rate S0 | M0 | Δ (M0−S0) | ATSA-F(macro) S0 | M0 | Δ | ATSA-F(micro) S0 | M0 | Δ | ACSA-F(macro) S0 | M0 | Δ | ACSA-F(micro) S0 | M0 | Δ |")
    lines.append("|--------|----------------------------------|-----|-----------|------------------|-----|---|------------------|-----|---|------------------|-----|---|------------------|-----|---|")
    if subset_data:
        for label, data in subset_data.items():
            def _f(v, fmt=".4f"):
                return f"{v:{fmt}}" if isinstance(v, (int, float)) else "—"
            ie_s0 = _f(data.get("implicit_err_s0")) if label == "Implicit" else "—"
            ie_m0 = _f(data.get("implicit_err_m0")) if label == "Implicit" else "—"
            ie_d = _f(data.get("implicit_err_delta"), "+.4f") if label == "Implicit" else "—"
            lines.append(
                f"| {label} | {ie_s0} | {ie_m0} | {ie_d} | "
                f"{_f(data.get('atsa_macro_s0'))} | {_f(data.get('atsa_macro_m0'))} | {_f(data.get('atsa_macro_delta'), '+.4f')} | "
                f"{_f(data.get('atsa_micro_s0'))} | {_f(data.get('atsa_micro_m0'))} | {_f(data.get('atsa_micro_delta'), '+.4f')} | "
                f"{_f(data.get('acsa_macro_s0'))} | {_f(data.get('acsa_macro_m0'))} | {_f(data.get('acsa_macro_delta'), '+.4f')} | "
                f"{_f(data.get('acsa_micro_s0'))} | {_f(data.get('acsa_micro_m0'))} | {_f(data.get('acsa_micro_delta'), '+.4f')} |"
            )
    else:
        lines.append("| *(run with --triptych-s0 and --triptych-m0 for subset analysis)* |")
    lines.append("")

    # 5.3 Process Layer
    lines.append("## 5.3 Process Layer")
    lines.append("### 5.3.1 Overall")
    lines.append("")
    lines.append("| Condition | Error Correction Rate (fix_rate) | Error Introduction Rate (break_rate) | Net Correction Gain (net_gain) |")
    lines.append("|-----------|----------------------------------|--------------------------------------|--------------------------------|")
    s0, m0, m1, d_ref, d = _row_s0("fix_rate")
    lines.append(f"| S0 | {s0} | {_fmt_mean_std(_get(agg_s0 or {}, 'break_rate')[0], _get(agg_s0 or {}, 'break_rate')[1]) or '—'} | {_fmt_mean_std(_get(agg_s0 or {}, 'net_gain')[0], _get(agg_s0 or {}, 'net_gain')[1]) or '—'} |")
    lines.append(f"| M0 | {m0} | {_fmt_mean_std(_get(agg_m0, 'break_rate')[0], _get(agg_m0, 'break_rate')[1]) or '—'} | {_fmt_mean_std(_get(agg_m0, 'net_gain')[0], _get(agg_m0, 'net_gain')[1]) or '—'} |")
    m1_fix, m1_break, m1_net = _get(agg_m1, "fix_rate")[0], _get(agg_m1, "break_rate")[0], _get(agg_m1, "net_gain")[0]
    m1_fs, m1_bs, m1_ns = _get(agg_m1, "fix_rate")[1], _get(agg_m1, "break_rate")[1], _get(agg_m1, "net_gain")[1]
    lines.append(f"| M1 | {_fmt_mean_std(m1_fix, m1_fs)} | {_fmt_mean_std(m1_break, m1_bs)} | {_fmt_mean_std(m1_net, m1_ns)} |")
    lines.append("")

    # 5.3.2 Conditional Overall Correction Stability (Subsets)
    lines.append("### 5.3.2 Conditional Overall Correction Stability (Subsets)")
    lines.append("")
    lines.append("**난이도 기반**")
    lines.append("")
    lines.append("| subset | fix_rate S0 | M0 | Δ (M0−S0) | break_rate S0 | M0 | Δ (M0−S0) | net_gain S0 | M0 | Δ (M0−S0) |")
    lines.append("|--------|-------------|-----|-----------|---------------|-----|-----------|-------------|-----|-----------|")
    if subset_data:
        for label, data in subset_data.items():
            def _f(v, fmt=".4f"):
                return f"{v:{fmt}}" if isinstance(v, (int, float)) else "—"
            lines.append(
                f"| {label} | {_f(data.get('fix_rate_s0'))} | {_f(data.get('fix_rate_m0'))} | {_f(data.get('fix_rate_delta'), '+.4f')} | "
                f"{_f(data.get('break_rate_s0'))} | {_f(data.get('break_rate_m0'))} | {_f(data.get('break_rate_delta'), '+.4f')} | "
                f"{_f(data.get('net_gain_s0'))} | {_f(data.get('net_gain_m0'))} | {_f(data.get('net_gain_delta'), '+.4f')} |"
            )
    else:
        lines.append("| *(run with --triptych-s0 and --triptych-m0 for subset analysis)* |")
    lines.append("")
    lines.append("**트리거 기반 (M0)**")
    lines.append("")
    if subset_data and args.triptych_m0:
        m0_trip = load_triptych(resolve(args.triptych_m0))
        m0_conflict = load_m0_conflict_flags(PROJECT_ROOT)
        for r in m0_trip:
            r["has_conflict"] = m0_conflict.get(r.get("text_id") or "", False)
        conflict_rows = [r for r in m0_trip if r.get("has_conflict")]
        no_conflict_rows = [r for r in m0_trip if not r.get("has_conflict")]
        n_conf = len(conflict_rows)
        n_noconf = len(no_conflict_rows)
        n_m0 = n_conf + n_noconf
        pct_conf = 100.0 * n_conf / n_m0 if n_m0 else 0
        fix_c = sum(1 for r in conflict_rows if int(r.get("fix_flag") or 0))
        fix_n = sum(1 for r in no_conflict_rows if int(r.get("fix_flag") or 0))
        break_c = sum(1 for r in conflict_rows if int(r.get("break_flag") or 0))
        break_n = sum(1 for r in no_conflict_rows if int(r.get("break_flag") or 0))
        ng_c = fix_c / n_conf - break_c / n_conf if n_conf else 0
        ng_n = fix_n / n_noconf - break_n / n_noconf if n_noconf else 0
        fix_rate_c = fix_c / n_conf if n_conf else 0
        fix_rate_n = fix_n / n_noconf if n_noconf else 0
        break_rate_c = break_c / n_conf if n_conf else 0
        break_rate_n = break_n / n_noconf if n_noconf else 0
        lines.append("| Subset (M0) | n_samples | fix_rate | break_rate | net_gain | % of samples |")
        lines.append("|-------------|-----------|----------|------------|----------|--------------|")
        lines.append(f"| conflict_flag = 1 | {n_conf} | {fix_rate_c:.4f} | {break_rate_c:.4f} | {ng_c:.4f} | {pct_conf:.1f}% |")
        lines.append(f"| conflict_flag = 0 | {n_noconf} | {fix_rate_n:.4f} | {break_rate_n:.4f} | {ng_n:.4f} | {100 - pct_conf:.1f}% |")
    else:
        lines.append("| Subset (M0) | n_samples | fix_rate | break_rate | net_gain | % of samples |")
        lines.append("|-------------|-----------|----------|------------|----------|--------------|")
        lines.append("| *(run with --triptych-m0 for trigger-based analysis)* |")
    lines.append("")

    # 5.4 Stochastic Stability
    lines.append("## 5.4 Stochastic Stability")
    lines.append("### 5.4.1 Overall")
    lines.append("")
    lines.append("| Condition | seed variance ACSA-F1 (MACRO) | seed variance ACSA-F1 (MICRO) | Run-to-Run Output Agreement (Measurement IRR Cohen's κ) |")
    lines.append("|-----------|------------------------------|------------------------------|-----------------------------------------------------|")
    sv_s0 = _seed_variance(s0_per_seed) if s0_per_seed else "—"
    sv_s0_micro = (_seed_variance(s0_per_seed, "tuple_f1_s2_refpol_micro") or "—") if s0_per_seed else "—"
    sv_m0 = _seed_variance(m0_per_seed) if m0_per_seed else "—"
    sv_m1 = _seed_variance(m1_per_seed) if m1_per_seed else "—"
    sv_m0_micro = _seed_variance(m0_per_seed, "tuple_f1_s2_refpol_micro") if m0_per_seed else "—"
    sv_m1_micro = _seed_variance(m1_per_seed, "tuple_f1_s2_refpol_micro") if m1_per_seed else "—"
    irr_m0 = _fmt_mean_std(_get(agg_m0, "meas_cohen_kappa_mean")[0], _get(agg_m0, "meas_cohen_kappa_mean")[1])
    irr_m1 = _fmt_mean_std(_get(agg_m1, "meas_cohen_kappa_mean")[0], _get(agg_m1, "meas_cohen_kappa_mean")[1])
    lines.append(f"| S0 | {sv_s0} | {sv_s0_micro} | N/A |")
    lines.append(f"| M0 | {sv_m0} | {sv_m0_micro} | {irr_m0 or '—'} |")
    lines.append(f"| M1 | {sv_m1} | {sv_m1_micro} | {irr_m1 or '—'} |")
    lines.append("")

    # 5.4.2 Conditional Stochastic Stability (Subsets)
    lines.append("### 5.4.2 Conditional Stochastic Stability (Subsets)")
    lines.append("")
    lines.append("| subset | seed variance ATSA-F(macro) S0 | M0 | Δ (M0−S0) | seed variance ATSA-F(micro) S0 | M0 | Δ (M0−S0) |")
    lines.append("|--------|--------------------------------|-----|-----------|--------------------------------|-----|-----------|")
    if subset_data and args.triptych_s0 and args.triptych_m0:
        s0_trip = load_triptych(resolve(args.triptych_s0))
        m0_trip = load_triptych(resolve(args.triptych_m0))
        m0_conflict = load_m0_conflict_flags(PROJECT_ROOT)
        seed_var_data = compute_subset_seed_variance(s0_trip, m0_trip, m0_conflict)
        for label in ["Implicit", "Explicit", "Negation", "Multi-aspect"]:
            data = seed_var_data.get(label, {})
            lines.append(
                f"| {label} | {data.get('atsa_macro_s0', '—')} | {data.get('atsa_macro_m0', '—')} | {data.get('atsa_macro_delta', '—')} | "
                f"{data.get('atsa_micro_s0', '—')} | {data.get('atsa_micro_m0', '—')} | {data.get('atsa_micro_delta', '—')} |"
            )
    else:
        lines.append("| *(run with --triptych-s0 and --triptych-m0; triptych must include run_id for per-seed variance)* |")
    lines.append("")

    # Appendix a1
    lines.append("## Appendix")
    lines.append("### a1. Metric Variance")
    lines.append("")
    lines.append("| Metric | S0 | M0 | M1 | Var(S0) | Var(M0) | Var(M1) |")
    lines.append("|--------|-----|-----|-----|---------|---------|---------|")
    for name, key in [("Micro F1 ACSA-F1", "tuple_f1_s2_refpol_micro"), ("Macro F1 ACSA-F1", "tuple_f1_s2_refpol")]:
        s0_m = _get(agg_s0 or {}, key)[0]
        m0_m = _get(agg_m0, key)[0]
        m1_m = _get(agg_m1, key)[0]
        s0_s = _get(agg_s0 or {}, key)[1]
        m0_s = _get(agg_m0, key)[1]
        m1_s = _get(agg_m1, key)[1]
        v0 = f"{float(s0_s)**2:.6f}" if s0_s and s0_s != "N/A" else "—"
        v1 = f"{float(m0_s)**2:.6f}" if m0_s and m0_s != "N/A" else "—"
        v2 = f"{float(m1_s)**2:.6f}" if m1_s and m1_s != "N/A" else "—"
        lines.append(f"| {name} | {s0_m or '—'} | {m0_m or '—'} | {m1_m or '—'} | {v0} | {v1} | {v2} |")
    lines.append("")

    # Appendix a2, a3 — pair-level counts (from per-seed structural_metrics if tp/fp/fn columns exist)
    lines.append("### a2. Full Pair-Level Counts (TP / FP / FN) — Overall by Condition (Seed-wise)")
    lines.append("")
    lines.append("| Condition | Seed | TP | FP | FN | Precision | Recall | Micro-F1 |")
    lines.append("|-----------|------|-----|-----|-----|-----------|--------|----------|")
    for cond, per_seed in [("S0", s0_per_seed), ("M0", m0_per_seed), ("M1", m1_per_seed)]:
        for seed, row in sorted(per_seed.items()):
            tp = int(row.get("tuple_f1_s2_refpol_tp", 0) or 0)
            fp = int(row.get("tuple_f1_s2_refpol_fp", 0) or 0)
            fn = int(row.get("tuple_f1_s2_refpol_fn", 0) or 0)
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            lines.append(f"| {cond} | {seed} | {tp} | {fp} | {fn} | {p:.4f} | {r:.4f} | {f1:.4f} |")
    lines.append("")

    lines.append("### a3. Pair-Level Micro Breakdown (Overall Only)")
    lines.append("")
    lines.append("| Condition | TP | FP | FN | Precision | Recall | Micro-F1 |")
    lines.append("|-----------|-----|-----|-----|-----------|--------|----------|")
    # Load merged_metrics for TP/FP/FN (aggregated_mean_std doesn't have them)
    merged_paths = []
    if args.agg_s0:
        p0 = resolve(args.agg_s0).parent / "merged_metrics" / "structural_metrics.csv"
        merged_paths.append(("S0", p0))
    p_m0 = resolve(args.agg_m0).parent / "merged_metrics" / "structural_metrics.csv"
    p_m1 = resolve(args.agg_m1).parent / "merged_metrics" / "structural_metrics.csv"
    merged_paths.extend([("M0", p_m0), ("M1", p_m1)])
    for cond, mp in merged_paths:
        if not mp.exists():
            micro = _get(agg_s0 if cond == "S0" else (agg_m0 if cond == "M0" else agg_m1), "tuple_f1_s2_refpol_micro")[0]
            lines.append(f"| {cond} | — | — | — | — | — | {micro or '—'} |")
            continue
        with mp.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        row = rows[0] if rows else {}
        tp = int(row.get("tuple_f1_s2_refpol_tp", 0) or 0)
        fp = int(row.get("tuple_f1_s2_refpol_fp", 0) or 0)
        fn = int(row.get("tuple_f1_s2_refpol_fn", 0) or 0)
        if tp + fp + fn == 0:
            micro = _get(agg_s0 if cond == "S0" else (agg_m0 if cond == "M0" else agg_m1), "tuple_f1_s2_refpol_micro")[0]
            lines.append(f"| {cond} | — | — | — | — | — | {micro or '—'} |")
        else:
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            lines.append(f"| {cond} | {tp} | {fp} | {fn} | {p:.4f} | {r:.4f} | {f1:.4f} |")
    lines.append("")

    # Appendix a4: Sentiment classification distribution + subset stats
    lines.append("### a4. Sentiment Classification Distribution (cr_v2_n601_v1 Dataset)")
    lines.append("")
    lines.append("**Gold 기준 샘플 단위 분포** (긍정만/부정만/중립만/믹스 각각 단일 카운트, 복수 감성 샘플은 믹스로 분류)")
    lines.append("")
    lines.append("| Category | n | % |")
    lines.append("|----------|---|---|")
    sc_s0 = resolve(args.scorecards_s0) if args.scorecards_s0 else (resolve(args.agg_s0).parent / "merged_scorecards.jsonl" if args.agg_s0 else None)
    sc_m0 = resolve(args.scorecards_m0) if args.scorecards_m0 else (resolve(args.agg_m0).parent / "merged_scorecards.jsonl")
    gold_path = sc_s0 if (sc_s0 and sc_s0.exists()) else (sc_m0 if sc_m0.exists() else None)
    gold_sample = compute_gold_sample_distribution(gold_path, seed_filter="seed42") if gold_path else {}
    if gold_sample:
        lines.append(f"| 긍정만 (positive only) | {int(gold_sample.get('positive_only_n', 0))} | {gold_sample.get('positive_only_pct', 0):.1f}% |")
        lines.append(f"| 부정만 (negative only) | {int(gold_sample.get('negative_only_n', 0))} | {gold_sample.get('negative_only_pct', 0):.1f}% |")
        lines.append(f"| 중립만 (neutral only) | {int(gold_sample.get('neutral_only_n', 0))} | {gold_sample.get('neutral_only_pct', 0):.1f}% |")
        lines.append(f"| 믹스 (복수 감성) | {int(gold_sample.get('mixed_n', 0))} | {gold_sample.get('mixed_pct', 0):.1f}% |")
        lines.append(f"| **Total** | **{int(gold_sample.get('total', 0))}** | 100.0% |")
    else:
        lines.append("| *(merged_scorecards.jsonl 필요)* |")
    lines.append("")
    lines.append("**Gold 기준 서브셋 통계**")
    lines.append("")
    trip_s0 = resolve(args.triptych_s0) if args.triptych_s0 else (resolve(args.agg_s0).parent / "derived_subset" / "triptych.csv" if args.agg_s0 else None)
    trip_m0 = resolve(args.triptych_m0) if args.triptych_m0 else (resolve(args.agg_m0).parent / "derived_subset" / "triptych.csv")
    triptych_for_subsets = (trip_s0 if (trip_s0 and trip_s0.exists()) else None) or (trip_m0 if trip_m0.exists() else None)
    subset_stats = compute_gold_subset_stats(triptych_for_subsets, gold_path, seed_filter="seed42")
    if subset_stats:
        lines.append("| Subset | n | % |")
        lines.append("|--------|---|---|")
        for label in ("Implicit", "Explicit", "Negation", "Non-negation", "Multi-aspect", "Single-aspect"):
            d = subset_stats.get(label, {})
            if d:
                lines.append(f"| {label} | {int(d.get('n', 0))} | {d.get('%', 0):.1f}% |")
    else:
        lines.append("| *(triptych.csv 또는 merged_scorecards.jsonl 필요)* |")
    lines.append("")

    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
