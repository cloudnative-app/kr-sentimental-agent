#!/usr/bin/env python3
"""
IRR (Inter-Rater Reliability) module for ReviewA/B/C.

A. Process Reliability (Action IRR): reviewer action agreement (KEEP/DROP/FLIP_*/MERGE/OTHER).
B. Measurement Reliability: final measurement label agreement (POS/NEG/NEU/DROP).
   Action→final_label: KEEP→original pol, FLIP_POS→POS, FLIP_NEG→NEG, DROP→DROP, MERGE/OTHER→DROP.

SSOT: outputs.jsonl. Writes results to results/<run>/irr/.

Dependencies:
  - scikit-learn: Cohen's κ
  - statsmodels (optional): Fleiss' κ (pip install statsmodels). If missing, fleiss_kappa will be null.

Usage:
  python scripts/compute_irr.py --input results/cr_n10_m0__seed42_proposed/outputs.jsonl --outdir results/cr_n10_m0__seed42_proposed/irr/
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Lexical cues for negation/contrast subset (outputs-based, no gold/validator required)
NEGATION_PATTERNS = [
    r"\b안\b", r"\b못\b", r"않", r"없",
    r"\b아니\b", r"지만", r"그러나",
    r"반면", r"\b근데\b", r"\b는데\b",
]

# Canonical action labels (Process Reliability)
KEEP = "KEEP"
MERGE = "MERGE"
DROP = "DROP"
FLIP_POS = "FLIP_POS"
FLIP_NEG = "FLIP_NEG"
FLIP = "FLIP"  # fallback when polarity unknown
OTHER = "OTHER"
CANONICAL_LABELS = [KEEP, MERGE, DROP, FLIP_POS, FLIP_NEG, FLIP, OTHER]
LABEL_TO_IDX = {lbl: i for i, lbl in enumerate(CANONICAL_LABELS)}

# Measurement Reliability: final_label ∈ {POS, NEG, NEU, DROP}.
# Policy: MERGE/OTHER → DROP (측정에서 제외, 해석 용이성).
POS, NEG, NEU, DROP_LBL = "POS", "NEG", "NEU", "DROP"
MEASUREMENT_LABELS = [POS, NEG, NEU, DROP_LBL]
MEAS_LABEL_TO_IDX = {lbl: i for i, lbl in enumerate(MEASUREMENT_LABELS)}


def _get_review_actions_from_record(record: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Extract review_actions per reviewer A/B/C from record. Uses process_trace or analysis_flags."""
    # Prefer analysis_flags if present (SSOT)
    flags = record.get("analysis_flags") or {}
    combined = flags.get("review_actions") or []

    actions_a: List[Dict] = []
    actions_b: List[Dict] = []
    actions_c: List[Dict] = []

    if combined:
        for a in combined:
            actor = (a.get("actor") or "").strip().upper()
            if actor == "A":
                actions_a.append(a)
            elif actor == "B":
                actions_b.append(a)
            elif actor == "C":
                actions_c.append(a)
    else:
        # Fallback: process_trace
        for tr in record.get("process_trace") or []:
            agent = (tr.get("agent") or "").strip()
            output = tr.get("output") or {}
            ra_list = output.get("review_actions") or []
            if agent == "ReviewA":
                actions_a = ra_list
            elif agent == "ReviewB":
                actions_b = ra_list
            elif agent == "ReviewC":
                actions_c = ra_list

    return actions_a, actions_b, actions_c


def _infer_tuple_ids(record: Dict[str, Any]) -> List[str]:
    """Infer tuple_ids t0, t1, ... from stage1 triplets (P-NEG, P-IMP, P-LIT merge order)."""
    all_ids: set = set()
    # From final_result
    fr = record.get("final_result") or {}
    pre = fr.get("final_tuples_pre_review") or fr.get("stage1_tuples") or []
    n = len(pre)
    for i in range(n):
        all_ids.add(f"t{i}")

    # Also collect from any review_actions
    for tr in record.get("process_trace") or []:
        if (tr.get("agent") or "").startswith("Review"):
            for a in (tr.get("output") or {}).get("review_actions") or []:
                for tid in a.get("target_tuple_ids") or []:
                    all_ids.add(tid)

    flags = record.get("analysis_flags") or {}
    for a in flags.get("review_actions") or []:
        for tid in a.get("target_tuple_ids") or []:
            all_ids.add(tid)

    # Sort: t0, t1, t2, ...
    def _key(tid: str) -> int:
        try:
            return int(tid.lstrip("t"))
        except ValueError:
            return 999

    return sorted(all_ids, key=_key)


def _to_canonical(action: Dict[str, Any]) -> str:
    """Convert action_type + new_value to canonical label."""
    atype = (action.get("action_type") or "").strip().upper()
    if atype == "KEEP":
        return KEEP
    if atype == "MERGE":
        return MERGE
    if atype == "DROP":
        return DROP
    if atype == "FLIP":
        nv = action.get("new_value") or {}
        pol = (str(nv.get("polarity") or "")).strip().lower()
        if pol in ("positive", "pos"):
            return FLIP_POS
        if pol in ("negative", "neg"):
            return FLIP_NEG
        return FLIP
    return atype if atype in CANONICAL_LABELS else OTHER


def _get_stage1_polarity_map(record: Dict[str, Any]) -> Dict[str, str]:
    """Map tuple_id → normalized polarity (positive/negative/neutral). From stage1_tuples."""
    fr = record.get("final_result") or {}
    pre = fr.get("final_tuples_pre_review") or fr.get("stage1_tuples") or []
    out: Dict[str, str] = {}
    for i, t in enumerate(pre):
        tid = f"t{i}"
        if isinstance(t, dict):
            p = (t.get("polarity") or "").strip().lower()
            if p in ("positive", "pos"):
                out[tid] = "positive"
            elif p in ("negative", "neg"):
                out[tid] = "negative"
            elif p in ("neutral", "neu", "mixed"):
                out[tid] = "neutral"
            else:
                out[tid] = "neutral"
        else:
            out[tid] = "neutral"
    return out


def _action_to_final_label(action: str, stage1_polarity: str) -> str:
    """Map reviewer action → final measurement label {POS, NEG, NEU, DROP}. MERGE/OTHER→DROP."""
    if action == KEEP:
        if stage1_polarity in ("positive", "pos"):
            return POS
        if stage1_polarity in ("negative", "neg"):
            return NEG
        return NEU
    if action == FLIP_POS:
        return POS
    if action == FLIP_NEG:
        return NEG
    if action == FLIP:
        return NEU  # unknown flip → NEU
    if action == DROP:
        return DROP_LBL
    if action in (MERGE, OTHER):
        return DROP_LBL
    return DROP_LBL


def build_measurement_matrix(
    record: Dict[str, Any],
    action_matrix: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    """Build final_label matrix: { tuple_id: { "A": POS/NEG/NEU/DROP, "B": ..., "C": ... } }."""
    pol_map = _get_stage1_polarity_map(record)
    out: Dict[str, Dict[str, str]] = {}
    for tid, acts in action_matrix.items():
        pol = pol_map.get(tid, "neutral")
        out[tid] = {
            "A": _action_to_final_label(acts.get("A", KEEP), pol),
            "B": _action_to_final_label(acts.get("B", KEEP), pol),
            "C": _action_to_final_label(acts.get("C", KEEP), pol),
        }
    return out


def build_action_matrix(record: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Build action matrix: { tuple_id: { "A": canonical_label, "B": ..., "C": ... } }.

    Rules:
    - No action for tuple_id → KEEP
    - MERGE: all target_tuple_ids get MERGE
    - FLIP: FLIP_POS / FLIP_NEG from new_value.polarity
    """
    actions_a, actions_b, actions_c = _get_review_actions_from_record(record)
    tuple_ids = _infer_tuple_ids(record)

    def _label_per_rater(actions: List[Dict], rater: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for tid in tuple_ids:
            out[tid] = KEEP  # default
        for a in actions:
            ids = a.get("target_tuple_ids") or []
            canon = _to_canonical(a)
            for tid in ids:
                if tid in out:
                    out[tid] = canon
        return out

    labels_a = _label_per_rater(actions_a, "A")
    labels_b = _label_per_rater(actions_b, "B")
    labels_c = _label_per_rater(actions_c, "C")

    matrix: Dict[str, Dict[str, str]] = {}
    for tid in tuple_ids:
        matrix[tid] = {
            "A": labels_a.get(tid, KEEP),
            "B": labels_b.get(tid, KEEP),
            "C": labels_c.get(tid, KEEP),
        }
    return matrix


def _compute_cohen_kappa(labels_a: List[str], labels_b: List[str]) -> Optional[float]:
    """Cohen's κ for two raters."""
    try:
        from sklearn.metrics import cohen_kappa_score
    except ImportError:
        return None
    if not labels_a or not labels_b or len(labels_a) != len(labels_b):
        return None
    if labels_a == labels_b:
        return 1.0
    k = cohen_kappa_score(labels_a, labels_b, labels=list(CANONICAL_LABELS))
    return float(k) if k is not None and (k == k) else None  # exclude NaN


def _compute_fleiss_kappa(labels_a: List[str], labels_b: List[str], labels_c: List[str]) -> Optional[float]:
    """Fleiss' κ for 3 raters."""
    try:
        from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa
    except ImportError:
        return None
    n = len(labels_a)
    if n == 0 or len(labels_b) != n or len(labels_c) != n:
        return None
    # Map labels to 0..k-1
    data = []
    for i in range(n):
        row = []
        for lbl in [labels_a[i], labels_b[i], labels_c[i]]:
            idx = LABEL_TO_IDX.get(lbl, -1)
            if idx < 0:
                idx = LABEL_TO_IDX.get(KEEP, 0)
            row.append(idx)
        data.append(row)
    try:
        import numpy as np
        arr = np.array(data)
        table, _ = aggregate_raters(arr)
        return float(fleiss_kappa(table))
    except Exception:
        return None


def _percent_agreement(labels_a: List[str], labels_b: List[str], labels_c: List[str]) -> Tuple[int, int, int]:
    """Return (perfect, majority, none) counts."""
    perfect = majority = none = 0
    for i in range(len(labels_a)):
        a, b, c = labels_a[i], labels_b[i], labels_c[i]
        votes = [a, b, c]
        uniq = set(votes)
        if len(uniq) == 1:
            perfect += 1
        elif len(uniq) == 2:
            majority += 1
        else:
            none += 1
    return perfect, majority, none


def _compute_cohen_kappa_measurement(labels_a: List[str], labels_b: List[str]) -> Optional[float]:
    """Cohen's κ for measurement labels (POS, NEG, NEU, DROP)."""
    try:
        from sklearn.metrics import cohen_kappa_score
    except ImportError:
        return None
    if not labels_a or not labels_b or len(labels_a) != len(labels_b):
        return None
    if labels_a == labels_b:
        return 1.0
    k = cohen_kappa_score(labels_a, labels_b, labels=list(MEASUREMENT_LABELS))
    return float(k) if k is not None and (k == k) else None


def _compute_fleiss_kappa_measurement(
    labels_a: List[str], labels_b: List[str], labels_c: List[str]
) -> Optional[float]:
    """Fleiss' κ for 3 raters, measurement labels (POS, NEG, NEU, DROP)."""
    try:
        from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa
    except ImportError:
        return None
    n = len(labels_a)
    if n == 0 or len(labels_b) != n or len(labels_c) != n:
        return None
    data = []
    for i in range(n):
        row = []
        for lbl in [labels_a[i], labels_b[i], labels_c[i]]:
            idx = MEAS_LABEL_TO_IDX.get(lbl, -1)
            if idx < 0:
                idx = MEAS_LABEL_TO_IDX.get(NEU, 2)
            row.append(idx)
        data.append(row)
    try:
        import numpy as np
        arr = np.array(data)
        table, _ = aggregate_raters(arr)
        return float(fleiss_kappa(table))
    except Exception:
        return None


def _percent_agreement_measurement(
    labels_a: List[str], labels_b: List[str], labels_c: List[str]
) -> Tuple[int, int, int]:
    """Return (perfect, majority, none) for measurement labels."""
    return _percent_agreement(labels_a, labels_b, labels_c)


def _has_conflict(record: Dict[str, Any]) -> bool:
    """True if conflict_flags non-empty."""
    flags = record.get("analysis_flags") or {}
    cf = flags.get("conflict_flags") or []
    return len(cf) > 0


def _is_implicit_case(record: Dict[str, Any]) -> bool:
    """True if gold has at least one implicit tuple (aspect_term empty). Uses _gold_tuples or inputs.gold_tuples."""
    gold = record.get("_gold_tuples") or (record.get("inputs") or {}).get("gold_tuples") or []
    if not gold:
        return False
    for t in gold:
        if not isinstance(t, dict):
            continue
        term = (t.get("aspect_term") or "")
        if isinstance(term, dict):
            term = term.get("term") or ""
        if (term or "").strip() in ("", None):
            return True
    return False


def _has_negation_case(record: Dict[str, Any]) -> bool:
    """True if input text contains negation/contrast lexical cues (outputs-based)."""
    meta = record.get("meta") or {}
    text = meta.get("input_text") or record.get("input_text") or record.get("text") or ""
    if not isinstance(text, str):
        text = str(text)
    for pat in NEGATION_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _get_memory_mode(record: Dict[str, Any]) -> str:
    """Extract memory mode from meta."""
    meta = record.get("meta") or {}
    return meta.get("memory_mode") or meta.get("memory", {}).get("memory_mode") or "unknown"


def compute_sample_irr(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute Process (action) and Measurement (final_label) IRR for one sample."""
    meta = record.get("meta") or {}
    if (meta.get("protocol_mode") or "").strip() != "conflict_review_v1":
        return None

    action_matrix = build_action_matrix(record)
    if not action_matrix:
        return None

    tuple_ids = sorted(
        action_matrix.keys(),
        key=lambda t: int(t.lstrip("t")) if t.lstrip("t").isdigit() else 999,
    )
    labels_a = [action_matrix[t]["A"] for t in tuple_ids]
    labels_b = [action_matrix[t]["B"] for t in tuple_ids]
    labels_c = [action_matrix[t]["C"] for t in tuple_ids]

    # Process Reliability (action)
    kappa_ab = _compute_cohen_kappa(labels_a, labels_b)
    kappa_ac = _compute_cohen_kappa(labels_a, labels_c)
    kappa_bc = _compute_cohen_kappa(labels_b, labels_c)
    kappas = [k for k in [kappa_ab, kappa_ac, kappa_bc] if k is not None]
    kappa_mean = sum(kappas) / len(kappas) if kappas else None
    fleiss_k = _compute_fleiss_kappa(labels_a, labels_b, labels_c)
    perfect, majority, none = _percent_agreement(labels_a, labels_b, labels_c)

    # Measurement Reliability (final_label)
    meas_matrix = build_measurement_matrix(record, action_matrix)
    meas_a = [meas_matrix[t]["A"] for t in tuple_ids]
    meas_b = [meas_matrix[t]["B"] for t in tuple_ids]
    meas_c = [meas_matrix[t]["C"] for t in tuple_ids]
    kappa_meas_ab = _compute_cohen_kappa_measurement(meas_a, meas_b)
    kappa_meas_ac = _compute_cohen_kappa_measurement(meas_a, meas_c)
    kappa_meas_bc = _compute_cohen_kappa_measurement(meas_b, meas_c)
    kappas_meas = [k for k in [kappa_meas_ab, kappa_meas_ac, kappa_meas_bc] if k is not None]
    kappa_mean_measurement = sum(kappas_meas) / len(kappas_meas) if kappas_meas else None
    fleiss_k_measurement = _compute_fleiss_kappa_measurement(meas_a, meas_b, meas_c)
    perfect_meas, majority_meas, none_meas = _percent_agreement_measurement(meas_a, meas_b, meas_c)

    return {
        "text_id": meta.get("text_id") or meta.get("uid") or "",
        "kappa_ab": kappa_ab,
        "kappa_ac": kappa_ac,
        "kappa_bc": kappa_bc,
        "kappa_mean": kappa_mean,
        "fleiss_kappa": fleiss_k,
        "agreement_perfect": perfect,
        "agreement_majority": majority,
        "agreement_none": none,
        "kappa_mean_measurement": kappa_mean_measurement,
        "fleiss_kappa_measurement": fleiss_k_measurement,
        "agreement_perfect_measurement": perfect_meas,
        "agreement_majority_measurement": majority_meas,
        "agreement_none_measurement": none_meas,
        "has_conflict": _has_conflict(record),
        "is_implicit": _is_implicit_case(record),
        "has_negation": _has_negation_case(record),
        "memory_mode": _get_memory_mode(record),
        "n_tuples": len(tuple_ids),
    }


def _load_uid_to_gold(scorecards_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load uid -> gold_tuples from scorecards.jsonl (for implicit subset when outputs lack inputs)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not scorecards_path.exists():
        return out
    for line in scorecards_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            sc = json.loads(line)
        except json.JSONDecodeError:
            continue
        uid = (sc.get("meta") or {}).get("text_id") or (sc.get("meta") or {}).get("uid") or ""
        gold = (sc.get("inputs") or {}).get("gold_tuples") or []
        if uid and gold:
            out[uid] = gold
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute IRR for ReviewA/B/C from outputs.jsonl")
    ap.add_argument("--input", type=Path, required=True, help="outputs.jsonl path")
    ap.add_argument("--outdir", type=Path, required=True, help="Output directory (e.g. results/<run>/irr/)")
    ap.add_argument("--scorecards", type=Path, default=None, help="scorecards.jsonl to merge gold_tuples for implicit subset (when outputs lack inputs)")
    ap.add_argument("--scorecards_path", type=Path, default=None, help="Alias for --scorecards")
    args = ap.parse_args()

    inp = args.input.resolve()
    if not inp.is_absolute():
        inp = (PROJECT_ROOT / inp).resolve()
    if not inp.exists():
        print(f"[ERROR] Missing: {inp}", file=sys.stderr)
        return 1

    outdir = args.outdir.resolve()
    if not outdir.is_absolute():
        outdir = (PROJECT_ROOT / outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    uid_to_gold: Dict[str, List[Dict[str, Any]]] = {}
    scorecards_path = args.scorecards or args.scorecards_path
    if scorecards_path:
        sp = Path(scorecards_path).resolve()
        if not sp.is_absolute():
            sp = (PROJECT_ROOT / sp).resolve()
        uid_to_gold = _load_uid_to_gold(sp)
        if uid_to_gold:
            print(f"[OK] Loaded gold_tuples for {len(uid_to_gold)} uids from scorecards")

    rows: List[Dict[str, Any]] = []
    for line in inp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Merge gold_tuples from scorecards for implicit subset (when outputs lack inputs)
        if uid_to_gold:
            uid = (record.get("meta") or {}).get("text_id") or (record.get("meta") or {}).get("uid") or ""
            if uid in uid_to_gold:
                gold_tuples = uid_to_gold[uid]
                record.setdefault("inputs", {})["gold_tuples"] = gold_tuples
                record["_gold_tuples"] = gold_tuples
        result = compute_sample_irr(record)
        if result:
            rows.append(result)

    if not rows:
        print("[WARN] No CR samples with review data found.", file=sys.stderr)
        outdir.joinpath("irr_sample_level.csv").write_text(
            "text_id,kappa_ab,kappa_ac,kappa_bc,kappa_mean,fleiss_kappa,agreement_perfect,agreement_majority,agreement_none,"
            "kappa_mean_measurement,fleiss_kappa_measurement,agreement_perfect_measurement,agreement_majority_measurement,"
            "has_conflict,memory_mode\n",
            encoding="utf-8",
        )
        summary = {
            "n_samples": 0,
            "mean_kappa": None,
            "mean_fleiss": None,
            "mean_perfect_agreement": None,
            "mean_majority_agreement": None,
            "mean_kappa_measurement": None,
            "mean_fleiss_measurement": None,
            "mean_perfect_agreement_measurement": None,
            "mean_majority_agreement_measurement": None,
            "conflict_vs_no_conflict": {},
        }
    else:
        # irr_sample_level.csv
        cols = [
            "text_id", "kappa_ab", "kappa_ac", "kappa_bc", "kappa_mean", "fleiss_kappa",
            "agreement_perfect", "agreement_majority", "agreement_none",
            "kappa_mean_measurement", "fleiss_kappa_measurement",
            "agreement_perfect_measurement", "agreement_majority_measurement",
            "has_conflict", "is_implicit", "has_negation", "memory_mode",
        ]
        csv_path = outdir / "irr_sample_level.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            def _csv_val(v: Any) -> Any:
                if v is None:
                    return ""
                try:
                    if isinstance(v, float) and v != v:  # NaN
                        return ""
                except Exception:
                    pass
                return v

            for r in rows:
                w.writerow({k: _csv_val(r.get(k)) for k in cols})
        print(f"[OK] wrote: {csv_path}")

        # irr_run_summary.json
        def _valid_float(v: Any) -> bool:
            if v is None:
                return False
            try:
                return v == v  # exclude NaN
            except Exception:
                return False

        kappa_means = [r["kappa_mean"] for r in rows if _valid_float(r.get("kappa_mean"))]
        fleiss_vals = [r["fleiss_kappa"] for r in rows if _valid_float(r.get("fleiss_kappa"))]
        perfect_total = sum(r["agreement_perfect"] for r in rows)
        majority_total = sum(r["agreement_majority"] for r in rows)
        total_tuples = sum(r["n_tuples"] for r in rows)

        kappa_meas_vals = [r["kappa_mean_measurement"] for r in rows if _valid_float(r.get("kappa_mean_measurement"))]
        fleiss_meas_vals = [r["fleiss_kappa_measurement"] for r in rows if _valid_float(r.get("fleiss_kappa_measurement"))]
        perfect_meas_total = sum(r["agreement_perfect_measurement"] for r in rows)
        majority_meas_total = sum(r["agreement_majority_measurement"] for r in rows)

        conflict_yes = sum(1 for r in rows if r.get("has_conflict"))
        conflict_no = len(rows) - conflict_yes

        def _safe_mean(vals: List[float]) -> Optional[float]:
            if not vals:
                return None
            m = sum(vals) / len(vals)
            return m if m == m else None  # exclude NaN

        summary = {
            "n_samples": len(rows),
            "mean_kappa": _safe_mean(kappa_means),
            "mean_fleiss": _safe_mean(fleiss_vals),
            "mean_perfect_agreement": perfect_total / total_tuples if total_tuples else None,
            "mean_majority_agreement": majority_total / total_tuples if total_tuples else None,
            "mean_kappa_measurement": _safe_mean(kappa_meas_vals),
            "mean_fleiss_measurement": _safe_mean(fleiss_meas_vals),
            "mean_perfect_agreement_measurement": perfect_meas_total / total_tuples if total_tuples else None,
            "mean_majority_agreement_measurement": majority_meas_total / total_tuples if total_tuples else None,
            "conflict_vs_no_conflict": {"has_conflict": conflict_yes, "no_conflict": conflict_no},
        }

        # Subset IRR: conflict, implicit, negation
        def _subset_mean(rows_sub: List[Dict], key: str) -> Optional[float]:
            vals = [r[key] for r in rows_sub if _valid_float(r.get(key))]
            return _safe_mean(vals)

        rows_conflict = [r for r in rows if r.get("has_conflict")]
        rows_implicit = [r for r in rows if r.get("is_implicit")]
        rows_negation = [r for r in rows if r.get("has_negation")]

        subset_summary = {
            "conflict": {
                "n": len(rows_conflict),
                "meas_cohen_kappa_mean": _subset_mean(rows_conflict, "kappa_mean_measurement"),
                "irr_cohen_kappa_mean": _subset_mean(rows_conflict, "kappa_mean"),
            },
            "implicit": {
                "n": len(rows_implicit),
                "meas_cohen_kappa_mean": _subset_mean(rows_implicit, "kappa_mean_measurement"),
                "irr_cohen_kappa_mean": _subset_mean(rows_implicit, "kappa_mean"),
            },
            "negation": {
                "n": len(rows_negation),
                "meas_cohen_kappa_mean": _subset_mean(rows_negation, "kappa_mean_measurement"),
                "irr_cohen_kappa_mean": _subset_mean(rows_negation, "kappa_mean"),
            },
        }
        subset_path = outdir / "irr_subset_summary.json"
        subset_path.write_text(json.dumps(subset_summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] wrote: {subset_path}")

    summary_path = outdir / "irr_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] wrote: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
