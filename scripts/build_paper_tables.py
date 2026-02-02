"""
Paper-ready table builder for ABSA runs.

Reads existing artifacts (manifest.json, scorecards.jsonl, traces.jsonl, optional smoke_outputs.jsonl)
and produces summary CSV/MD tables under <run_dir>/paper_outputs/.

Non-intrusive: does not touch model code, prompts, or integrity guards.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ---------- IO helpers ----------

def load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> List[Dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ---------- Text & triplet helpers ----------

PUNCT = ".,;:!?\"'`“”‘’()[]{}"


def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    text = text.strip().lower()
    text = text.strip(PUNCT)
    # collapse whitespace
    text = " ".join(text.split())
    return text


Triplet = Tuple[str, str, str]


def triplet_from_sentiment(sent: Dict) -> Triplet:
    aspect = normalize_text(sent.get("aspect_ref") or sent.get("term"))
    opinion = normalize_text((sent.get("opinion_term") or {}).get("term"))
    polarity = normalize_text(sent.get("polarity") or sent.get("label"))
    return (aspect, opinion, polarity)


def triplets_from_list(items: Iterable[Dict]) -> Set[Triplet]:
    return {triplet_from_sentiment(it) for it in items if it}


# ---------- Extraction from artifacts ----------


def extract_final_triplets(sc_row: Dict) -> Set[Triplet]:
    aspect_sents = sc_row.get("inputs", {}).get("aspect_sentiments")
    if isinstance(aspect_sents, list):
        return triplets_from_list(aspect_sents)
    return set()


def extract_stage1_triplets(sc_row: Dict) -> Set[Triplet]:
    trace = sc_row.get("runtime", {}).get("process_trace") or []
    for entry in trace:
        if entry.get("stage") == "stage1" and entry.get("agent", "").lower() == "atsa":
            sents = entry.get("output", {}).get("aspect_sentiments")
            if isinstance(sents, list):
                return triplets_from_list(sents)
    # fallback to final if missing
    return extract_final_triplets(sc_row)


def extract_stage2_triplets(sc_row: Dict) -> Set[Triplet]:
    # Stage2 review outputs are deltas; use final as post-review proxy.
    return extract_final_triplets(sc_row)


def extract_gold_triplets(sc_row: Dict) -> Optional[Set[Triplet]]:
    gold = sc_row.get("gold_triplets") or sc_row.get("inputs", {}).get("gold_triplets")
    if isinstance(gold, list):
        return triplets_from_list(gold)
    return None


def has_structural_risk(sc_row: Dict) -> bool:
    # scorecards flags first
    flags = sc_row.get("flags", {})
    if flags.get("structural_risk"):
        return True
    # look into validator output inside process_trace
    trace = sc_row.get("runtime", {}).get("process_trace") or []
    for entry in trace:
        if entry.get("agent", "").lower() == "validator":
            risks = entry.get("output", {}).get("structural_risks")
            if isinstance(risks, list) and len(risks) > 0:
                return True
    return False


def has_unanchored_ref(sc_row: Dict) -> bool:
    analysis = sc_row.get("analysis_flags") or sc_row.get("flags", {}).get("analysis_flags", {})
    if isinstance(analysis, dict) and analysis.get("unanchored_aspect_ref"):
        return True
    return False


def is_targetless(sc_row: Dict) -> bool:
    sp = sc_row.get("stage_policy_score") or {}
    if sp.get("targetless_policy_applied"):
        return True
    return False


def polarity_conflict_flag(final_triplets: Set[Triplet]) -> bool:
    by_aspect: Dict[str, Set[str]] = defaultdict(set)
    for aspect, _op, pol in final_triplets:
        by_aspect[aspect].add(pol)
    return any(len(pols) >= 2 for pols in by_aspect.values())


def get_flags(sc_row: Dict) -> Dict[str, bool]:
    flags = sc_row.get("flags", {}) or {}
    return {
        "parse_failed": bool(flags.get("parse_failed")),
        "generate_failed": bool(flags.get("generate_failed")),
        "fallback_used": bool(flags.get("fallback_used")),
    }


def fallback_from_trace(sc_row: Dict) -> bool:
    trace = sc_row.get("runtime", {}).get("process_trace") or []
    for entry in trace:
        cm = entry.get("call_metadata") or {}
        if cm.get("fallback_construct_used"):
            return True
    return False


def structural_pass(sc_row: Dict) -> Optional[bool]:
    summary = sc_row.get("summary") or {}
    if "quality_pass" in summary:
        return bool(summary.get("quality_pass"))
    return None


def token_cost_latency(sc_row: Dict):
    meta = sc_row.get("meta") or {}
    rt = sc_row.get("runtime") or {}
    tokens_in = rt.get("tokens_in") if rt else meta.get("tokens_in")
    tokens_out = rt.get("tokens_out") if rt else meta.get("tokens_out")
    cost = rt.get("cost_usd") if rt else meta.get("cost_usd")
    latency = meta.get("latency_ms")
    return tokens_in, tokens_out, cost, latency


# ---------- Metric computations ----------


def precision_recall_f1(pred: Set[Triplet], gold: Set[Triplet]) -> Tuple[float, float, float]:
    if gold is None or len(gold) == 0:
        return (math.nan, math.nan, math.nan)
    if pred is None:
        pred = set()
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if prec + rec == 0:
        f1 = 0.0
    else:
        f1 = 2 * prec * rec / (prec + rec)
    return (prec, rec, f1)


def mean_std(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if not vals:
        return (None, None)
    if len(vals) == 1:
        return (vals[0], 0.0)
    return (statistics.mean(vals), statistics.pstdev(vals))


# ---------- Core processing ----------


class RunArtifacts:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        manifest_path = run_dir / "manifest.json"
        score_path = run_dir / "scorecards.jsonl"
        if not manifest_path.exists():
            alt = Path("experiments") / "reports" / run_dir.name / "manifest.json"
            if alt.exists():
                manifest_path = alt
            else:
                # keep running with placeholder manifest to avoid crash
                print(f"[build_paper_tables] Warning: manifest.json not found in {run_dir} or {alt}; using empty manifest.")
                self.manifest = {"run_id": run_dir.name}
            # continue even if placeholder is used
        if manifest_path.exists():
            self.manifest = load_json(manifest_path)
        if score_path.exists():
            self.scorecards = load_jsonl(score_path)
        else:
            print(f"[build_paper_tables] Warning: scorecards.jsonl not found in {run_dir}; proceeding with empty rows.")
            self.scorecards = []
        self.traces = load_jsonl(run_dir / "traces.jsonl") if (run_dir / "traces.jsonl").exists() else []
        self.smoke_outputs = (
            load_jsonl(run_dir / "smoke_outputs.jsonl") if (run_dir / "smoke_outputs.jsonl").exists() else []
        )


def build_smoke_preview_map(smoke_rows: List[Dict]) -> Dict[str, str]:
    preview = {}
    for r in smoke_rows:
        uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
        txt = (r.get("meta") or {}).get("input_text") or (r.get("input") or r.get("text"))
        if uid and txt:
            preview[uid] = txt[:200]
    return preview


def filter_splits(rows: List[Dict], splits: Set[str]) -> List[Dict]:
    if not splits:
        return rows
    return [
        r
        for r in rows
        if ((r.get("meta") or {}).get("split") in splits) or (r.get("split") in splits)
    ]


def compute_run_metrics(art: RunArtifacts, report_splits: Set[str], smoke_preview: Dict[str, str]) -> Dict:
    rows = filter_splits(art.scorecards, report_splits)
    included_uids = set((r.get("meta") or {}).get("text_id") or r.get("uid") for r in rows)

    # Triplets
    final_triplets_by_uid: Dict[str, Set[Triplet]] = {}
    stage1_triplets_by_uid: Dict[str, Set[Triplet]] = {}
    stage2_triplets_by_uid: Dict[str, Set[Triplet]] = {}
    gold_by_uid: Dict[str, Optional[Set[Triplet]]] = {}

    for r in rows:
        uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
        final_triplets_by_uid[uid] = extract_final_triplets(r)
        stage1_triplets_by_uid[uid] = extract_stage1_triplets(r)
        stage2_triplets_by_uid[uid] = extract_stage2_triplets(r)
        gold_by_uid[uid] = extract_gold_triplets(r)

    # Metrics containers
    pass_flags = []
    valid_triplet = []
    parse_failed = []
    generate_failed = []
    fallback_used = []
    conflict_flags = []
    structural_risk_flags = []
    unanchored_flags = []
    targetless_flags = []
    tokens_in_vals = []
    tokens_out_vals = []
    cost_vals = []
    latency_vals = []

    # Hard subset ids
    hard_subset_uids: Set[str] = set()

    for r in rows:
        uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
        flags = get_flags(r)
        parse_failed.append(flags["parse_failed"])
        generate_failed.append(flags["generate_failed"])
        fb = flags["fallback_used"] or fallback_from_trace(r)
        fallback_used.append(fb)

        srisk = has_structural_risk(r)
        structural_risk_flags.append(srisk)
        if srisk:
            hard_subset_uids.add(uid)

        unanchored_flags.append(has_unanchored_ref(r))
        targetless_flags.append(is_targetless(r))

        final_ts = final_triplets_by_uid[uid]
        conflict_flags.append(polarity_conflict_flag(final_ts))
        valid_triplet.append(len(final_ts) > 0)

        sp = structural_pass(r)
        if sp is not None:
            pass_flags.append(sp)

        ti, to, cost, lat = token_cost_latency(r)
        tokens_in_vals.append(ti)
        tokens_out_vals.append(to)
        cost_vals.append(cost)
        latency_vals.append(lat)

    # Rates
    def mean_bool(lst: List[bool]) -> Optional[float]:
        if not lst:
            return None
        return sum(1 for x in lst if x) / len(lst)

    metrics = {
        "run_id": art.manifest.get("run_id"),
        "runner_name": art.manifest.get("mode"),
        "backbone_model_id": (art.manifest.get("backbone") or {}).get("model"),
        "included_row_count": len(rows),
        "pass_rate": mean_bool(pass_flags),
        "valid_aspect_rate": mean_bool(valid_triplet),
        "polarity_conflict_rate": mean_bool(conflict_flags),
        "unanchored_rate": mean_bool(unanchored_flags),
        "structural_risk_rate": mean_bool(structural_risk_flags),
        "targetless_rate": mean_bool(targetless_flags),
        "parse_failure_rate": mean_bool(parse_failed),
        "generate_failure_rate": mean_bool(generate_failed),
        "fallback_used_rate": mean_bool(fallback_used),
        "tokens_in_mean": mean_std(tokens_in_vals)[0],
        "tokens_in_std": mean_std(tokens_in_vals)[1],
        "tokens_out_mean": mean_std(tokens_out_vals)[0],
        "tokens_out_std": mean_std(tokens_out_vals)[1],
        "cost_usd_mean": mean_std(cost_vals)[0],
        "cost_usd_std": mean_std(cost_vals)[1],
        "latency_ms_mean": mean_std(latency_vals)[0],
        "latency_ms_std": mean_std(latency_vals)[1],
    }

    # Failure breakdown counts
    metrics.update(
        {
            "count_structural_risk": sum(structural_risk_flags),
            "count_unanchored": sum(unanchored_flags),
            "count_targetless": sum(targetless_flags),
            "count_polarity_conflict": sum(conflict_flags),
            "count_parse_failed": sum(parse_failed),
            "count_generate_failed": sum(generate_failed),
        }
    )

    # Hard subset F1 and stage deltas (if gold exists)
    gold_available = any(g is not None for g in gold_by_uid.values())
    if gold_available:
        f1_stage1 = []
        f1_stage2 = []
        f1_final = []
        hard_f1_stage1 = []
        hard_f1_stage2 = []
        for uid in included_uids:
            gold = gold_by_uid.get(uid)
            if gold is None:
                continue
            _, _, f1_1 = precision_recall_f1(stage1_triplets_by_uid.get(uid, set()), gold)
            _, _, f1_2 = precision_recall_f1(stage2_triplets_by_uid.get(uid, set()), gold)
            _, _, f1_f = precision_recall_f1(final_triplets_by_uid.get(uid, set()), gold)
            f1_stage1.append(f1_1)
            f1_stage2.append(f1_2)
            f1_final.append(f1_f)
            if uid in hard_subset_uids:
                hard_f1_stage1.append(f1_1)
                hard_f1_stage2.append(f1_2)

        metrics.update(
            {
                "f1_stage1": mean_std(f1_stage1)[0],
                "f1_stage2": mean_std(f1_stage2)[0],
                "delta_f1": (mean_std(f1_stage2)[0] - mean_std(f1_stage1)[0])
                if f1_stage1 and f1_stage2
                else None,
                "hard_f1_stage1": mean_std(hard_f1_stage1)[0],
                "hard_f1_stage2": mean_std(hard_f1_stage2)[0],
                "hard_delta_f1": (mean_std(hard_f1_stage2)[0] - mean_std(hard_f1_stage1)[0])
                if hard_f1_stage1 and hard_f1_stage2
                else None,
            }
        )

        # Error correction
        c01 = c10 = 0
        n = 0
        for uid in included_uids:
            gold = gold_by_uid.get(uid)
            if gold is None:
                continue
            n += 1
            st1 = stage1_triplets_by_uid.get(uid, set()) == gold
            st2 = stage2_triplets_by_uid.get(uid, set()) == gold
            if not st1 and st2:
                c01 += 1
            if st1 and not st2:
                c10 += 1
        if n > 0:
            metrics.update(
                {
                    "net_error_correction_rate": (c01 - c10) / n,
                    "correction_rate": c01 / n,
                    "degradation_rate": c10 / n,
                }
            )
    else:
        metrics.update(
            {
                "f1_stage1": None,
                "f1_stage2": None,
                "delta_f1": None,
                "hard_f1_stage1": None,
                "hard_f1_stage2": None,
                "hard_delta_f1": None,
                "net_error_correction_rate": None,
                "correction_rate": None,
                "degradation_rate": None,
            }
        )

    # Case summary
    case_rows = []
    for r in rows:
        uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
        final_ts = final_triplets_by_uid[uid]
        stage1_ts = stage1_triplets_by_uid[uid]
        case_rows.append(
            {
                "uid": uid,
                "run_id": art.manifest.get("run_id"),
                "timestamp_utc": art.manifest.get("timestamp_utc"),
                "split": (r.get("meta") or {}).get("split"),
                "case_type": (r.get("meta") or {}).get("case_type"),
                "structural_risk": uid in hard_subset_uids,
                "parse_failed": get_flags(r)["parse_failed"],
                "generate_failed": get_flags(r)["generate_failed"],
                "fallback_used": fallback_from_trace(r) or get_flags(r)["fallback_used"],
                "polarity_conflict": polarity_conflict_flag(final_ts),
                "final_triplet_count": len(final_ts),
                "stage1_triplet_count": len(stage1_ts),
                "text_preview": smoke_preview.get(uid),
            }
        )

    # row count check
    if len(case_rows) != len(rows):
        raise ValueError(f"Case summary row count mismatch for run {art.manifest.get('run_id')}: {len(case_rows)} vs {len(rows)}")

    return {
        "metrics": metrics,
        "case_rows": case_rows,
        "included_uids": included_uids,
        "hard_subset_uids": hard_subset_uids,
    }


def compute_self_consistency(run_metric_list: List[Dict], runs_data: List[RunArtifacts], report_split: str, n_runs_required: int) -> Optional[float]:
    if len(runs_data) < n_runs_required:
        return None

    # Load final triplets per run
    per_run_uid_triplets: List[Dict[str, Set[Triplet]]] = []
    uid_sets = []
    for art in runs_data:
        rows = filter_split(art.scorecards, report_split)
        uid_to_triplets = {}
        for r in rows:
            uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
            uid_to_triplets[uid] = extract_final_triplets(r)
        per_run_uid_triplets.append(uid_to_triplets)
        uid_sets.append(set(uid_to_triplets.keys()))

    eligible_uids = set.intersection(*uid_sets) if uid_sets else set()
    if not eligible_uids:
        return None

    exact_matches = []
    for uid in eligible_uids:
        first = per_run_uid_triplets[0].get(uid, set())
        exact = all(per_run_uid_triplets[i].get(uid, set()) == first for i in range(1, len(per_run_uid_triplets)))
        exact_matches.append(1 if exact else 0)

    if not exact_matches:
        return None
    return sum(exact_matches) / len(exact_matches)


# ---------- Output writers ----------


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: List[Dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_md_table(path: Path, rows: List[Dict], float_fmt="{:.3f}"):
    if not rows:
        return
    headers = list(rows[0].keys())
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join([" --- " for _ in headers]) + "|")
    for row in rows:
        cells = []
        for h in headers:
            val = row.get(h)
            if isinstance(val, float):
                if math.isnan(val):
                    cells.append("null")
                else:
                    cells.append(float_fmt.format(val))
            else:
                cells.append(str(val))
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines), encoding="utf-8")


def aggregate_metrics(per_run_results: List[Dict]) -> List[Dict]:
    grouped: Dict[Tuple[str, str], Dict[str, List[Optional[float]]]] = {}
    keys_mean_std = [
        "pass_rate",
        "valid_aspect_rate",
        "polarity_conflict_rate",
        "unanchored_rate",
        "structural_risk_rate",
        "targetless_rate",
        "parse_failure_rate",
        "generate_failure_rate",
        "fallback_used_rate",
        "cost_usd_mean",
        "latency_ms_mean",
        "tokens_in_mean",
        "tokens_out_mean",
    ]
    count_keys = [
        "count_structural_risk",
        "count_unanchored",
        "count_targetless",
        "count_polarity_conflict",
        "count_parse_failed",
        "count_generate_failed",
    ]
    rows = []
    # prepare containers
    for res in per_run_results:
        m = res["metrics"]
        key = (m.get("runner_name"), m.get("backbone_model_id"))
        if key not in grouped:
            grouped[key] = {k: [] for k in keys_mean_std + count_keys}
        for k in keys_mean_std + count_keys:
            grouped[key][k].append(m.get(k))

    for (runner, backbone), vals in grouped.items():
        row = {"runner_name": runner, "backbone_model_id": backbone}
        for k in keys_mean_std:
            mean, std = mean_std(vals[k])
            row[f"{k}_mean"] = mean
            row[f"{k}_std"] = std
        for k in count_keys:
            mean, std = mean_std(vals[k])
            row[f"{k}_mean"] = mean
            row[f"{k}_std"] = std
        rows.append(row)
    return rows


def build_tables_for_runs(
    run_dirs: List[Path],
    report_splits: Optional[Set[str]],
    hard_subset_source: str,
    n_runs_for_consistency: int,
    force_smoke_sanity: bool = False,
    smoke_sanity_warning: Optional[str] = None,
    strict: bool = False,
):
    run_artifacts = [RunArtifacts(rd) for rd in run_dirs]

    # sort by timestamp_utc (fallback: file mtime) to keep tables ordered chronologically
    def _ts(art: RunArtifacts) -> float:
        ts = art.manifest.get("timestamp_utc")
        if ts:
            try:
                from datetime import datetime

                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        try:
            return art.run_dir.stat().st_mtime
        except Exception:
            return 0.0

    # File key -> split name for sources-based roles
    FILE_KEY_TO_SPLIT = {"train_file": "train", "valid_file": "valid", "test_file": "test"}

    run_artifacts = sorted(run_artifacts, key=_ts)
    if not report_splits:
        # Prefer manifest data_roles.report_sources (file keys) -> split names; else report_set; else default
        roles = (run_artifacts[0].manifest.get("data_roles") or {})
        report_src = roles.get("report_sources")
        if report_src is not None and isinstance(report_src, list):
            report_splits = {FILE_KEY_TO_SPLIT[k] for k in report_src if k in FILE_KEY_TO_SPLIT}
        else:
            report_splits = set(roles.get("report_set") or ["valid"])
    per_run_results = []
    for art in run_artifacts:
        smoke_preview = build_smoke_preview_map(art.smoke_outputs)
        res = compute_run_metrics(art, report_splits, smoke_preview)
        per_run_results.append(res)

    # self consistency across provided runs
    self_consistency = compute_self_consistency(
        [r["metrics"] for r in per_run_results], run_artifacts, list(report_splits)[0] if report_splits else "", n_runs_for_consistency
    )
    agg_rows = aggregate_metrics(per_run_results)

    report_split_label = ",".join(sorted(report_splits)) if report_splits else "all"

    # Build tables per run
    for res, art in zip(per_run_results, run_artifacts):
        outdir = art.run_dir / "paper_outputs"
        ensure_dir(outdir)

        metrics = res["metrics"]
        if self_consistency is not None:
            metrics["self_consistency_exact"] = self_consistency
        else:
            metrics["self_consistency_exact"] = None

        # Table 1: manifest summary
        manifest = art.manifest
        dataset_paths = ""
        if manifest.get("dataset", {}).get("paths"):
            try:
                dataset_paths = ";".join(manifest.get("dataset", {}).get("paths", {}).values())
            except Exception:
                dataset_paths = str(manifest.get("dataset", {}).get("paths"))
        t1_rows = [
            {
                "run_id": manifest.get("run_id"),
                "timestamp_utc": manifest.get("timestamp_utc"),
                "cfg_hash": manifest.get("cfg_hash"),
                "backbone_model_id": (manifest.get("backbone") or {}).get("model"),
                "backbone_provider": (manifest.get("backbone") or {}).get("provider"),
                "prompt_version_count": len(manifest.get("prompt_versions") or {}),
                "report_split": report_split_label,
                "split_train": (manifest.get("dataset") or {}).get("split_counts", {}).get("train"),
                "split_valid": (manifest.get("dataset") or {}).get("split_counts", {}).get("valid"),
                "split_test": (manifest.get("dataset") or {}).get("split_counts", {}).get("test"),
                "dataset_paths": dataset_paths,
            }
        ]
        write_csv(outdir / "paper_table_1_manifest.csv", t1_rows)
        write_md_table(outdir / "paper_table_1_manifest.md", t1_rows)

        # Table 2: dataset roles (report_sources / blind_sources when present)
        roles = manifest.get("data_roles") or {}
        t2_rows = [
            {
                "run_id": manifest.get("run_id"),
                "demo_pool": roles.get("demo_pool"),
                "tuning_pool": roles.get("tuning_pool"),
                "report_set": roles.get("report_set"),
                "blind_set": roles.get("blind_set"),
                "report_sources": roles.get("report_sources"),
                "blind_sources": roles.get("blind_sources"),
            }
        ]
        write_csv(outdir / "paper_table_2_dataset_roles.csv", t2_rows)
        write_md_table(outdir / "paper_table_2_dataset_roles.md", t2_rows)

        # Table 3: main results
        # Check for missing required fields
        required_fields = ["pass_rate", "valid_aspect_rate", "polarity_conflict_rate", "parse_failure_rate", "generate_failure_rate"]
        missing_fields = [f for f in required_fields if metrics.get(f) is None]
        
        if missing_fields:
            warning_msg = f"WARN: missing fields in paper_table_3: {', '.join(missing_fields)}"
            print(f"[build_paper_tables] {warning_msg}", file=sys.stderr)
            if strict:
                raise SystemExit(f"FAIL: Required fields missing in paper table 3: {', '.join(missing_fields)}")
        
        t3_rows = [
            {
                "runner_name": metrics.get("runner_name"),
                "backbone_model_id": metrics.get("backbone_model_id"),
                "timestamp_utc": (art.manifest or {}).get("timestamp_utc"),
                "pass_rate": metrics.get("pass_rate"),
                "valid_aspect_rate": metrics.get("valid_aspect_rate"),
                "polarity_conflict_rate": metrics.get("polarity_conflict_rate"),
                "unanchored_rate": metrics.get("unanchored_rate"),
                "self_consistency_exact": metrics.get("self_consistency_exact"),
                "parse_failure_rate": metrics.get("parse_failure_rate"),
                "generate_failure_rate": metrics.get("generate_failure_rate"),
                "fallback_used_rate": metrics.get("fallback_used_rate"),
                "cost_usd_mean": metrics.get("cost_usd_mean"),
                "cost_usd_std": metrics.get("cost_usd_std"),
                "latency_ms_mean": metrics.get("latency_ms_mean"),
                "latency_ms_std": metrics.get("latency_ms_std"),
                "tokens_in_mean": metrics.get("tokens_in_mean"),
                "tokens_in_std": metrics.get("tokens_in_std"),
                "tokens_out_mean": metrics.get("tokens_out_mean"),
                "tokens_out_std": metrics.get("tokens_out_std"),
            }
        ]
        write_csv(outdir / "paper_table_3_main_results.csv", t3_rows)
        write_md_table(outdir / "paper_table_3_main_results.md", t3_rows)

        # Aggregated main results across provided runs (if >1)
        if len(run_dirs) > 1 and agg_rows:
            write_csv(outdir / "paper_table_3_main_results_agg.csv", agg_rows)
            write_md_table(outdir / "paper_table_3_main_results_agg.md", agg_rows)

        # Table 4: failure breakdown
        t4_rows = [
            {
                "runner_name": metrics.get("runner_name"),
                "backbone_model_id": metrics.get("backbone_model_id"),
                "structural_risk_rate": metrics.get("structural_risk_rate"),
                "structural_risk": metrics.get("count_structural_risk"),
                "unanchored_rate": metrics.get("unanchored_rate"),
                "unanchored_aspect_ref": metrics.get("count_unanchored"),
                "targetless_rate": metrics.get("targetless_rate"),
                "targetless": metrics.get("count_targetless"),
                "polarity_conflict_count": metrics.get("count_polarity_conflict"),
                "polarity_conflict_rate": metrics.get("polarity_conflict_rate"),
                "parse_failed": metrics.get("count_parse_failed"),
                "generate_failed": metrics.get("count_generate_failed"),
            }
        ]
        write_csv(outdir / "paper_table_4_failure_breakdown.csv", t4_rows)
        write_md_table(outdir / "paper_table_4_failure_breakdown.md", t4_rows)

        # Unified case summary
        write_csv(outdir / "unified_case_summary.csv", res["case_rows"])

        # Paper report
        report_lines = []

        # Add DO NOT REPORT banner for smoke/sanity runs
        if force_smoke_sanity and smoke_sanity_warning:
            report_lines.append("---")
            report_lines.append("## ⚠️ DO NOT REPORT ⚠️")
            report_lines.append("")
            report_lines.append("**This report was generated from smoke/sanity runs and should NOT be used for paper reporting.**")
            report_lines.append(f"- Affected runs: {smoke_sanity_warning}")
            report_lines.append("- Reason: Smoke/sanity runs may use synthetic data, duplicated splits, or incomplete configurations.")
            report_lines.append("")
            report_lines.append("---")
            report_lines.append("")

        report_lines.append(f"# Paper Report for {manifest.get('run_id')}")
        report_lines.append("")
        report_lines.append(f"- purpose: {manifest.get('purpose', 'unknown')}")
        report_lines.append(f"- report_split: {report_split_label}")
        report_lines.append(f"- included rows: {metrics.get('included_row_count')}")
        report_lines.append(f"- self_consistency_exact: {metrics.get('self_consistency_exact')}")
        report_lines.append("")
        report_lines.append("## Generated Tables")
        for name in [
            "paper_table_1_manifest",
            "paper_table_2_dataset_roles",
            "paper_table_3_main_results",
            "paper_table_4_failure_breakdown",
            "unified_case_summary",
        ]:
            report_lines.append(f"- {name} (md/csv) in paper_outputs/")
        if len(run_dirs) > 1 and agg_rows:
            report_lines.append("- paper_table_3_main_results_agg (md/csv) aggregated across provided runs")
        (outdir / "paper_report.md").write_text("\n".join(report_lines), encoding="utf-8")


# ---------- CLI ----------


def parse_args():
    p = argparse.ArgumentParser(description="Build paper-ready tables from run artifacts.")
    p.add_argument("--run_dir", type=str, help="Single run directory containing manifest/scorecards/traces.")
    p.add_argument("--run_dirs", nargs="+", help="Multiple run directories for consistency analysis.")
    p.add_argument("--report_split", type=str, default="valid", help="Split to report on (default: valid).")
    p.add_argument(
        "--hard_subset_source",
        type=str,
        default="validator_risk",
        help="Hard subset source (currently validator_risk only).",
    )
    p.add_argument(
        "--include_splits",
        nargs="+",
        help="If provided, include these splits (overrides report_set).",
    )
    p.add_argument(
        "--n_runs_for_consistency",
        type=int,
        default=3,
        help="Number of runs required to compute self-consistency.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force building tables even for smoke/sanity runs (adds DO NOT REPORT banner).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: missing required fields in paper tables -> FAIL (exit code 1).",
    )
    return p.parse_args()


def _check_smoke_sanity_enforcement(run_dirs: List[Path], force: bool) -> Optional[str]:
    """
    Check if any run is smoke/sanity and return warning message if so.
    Returns None if all runs are paper/dev purpose.
    """
    smoke_sanity_runs = []
    for rd in run_dirs:
        manifest_path = rd / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = load_json(manifest_path)
                purpose = manifest.get("purpose", "unknown")
                if purpose in ("smoke", "sanity"):
                    smoke_sanity_runs.append((rd.name, purpose))
            except Exception:
                pass
    if smoke_sanity_runs:
        runs_str = ", ".join(f"{name} ({purpose})" for name, purpose in smoke_sanity_runs)
        return runs_str
    return None


def main():
    args = parse_args()
    if args.run_dir and args.run_dirs:
        run_dirs = [Path(args.run_dir)] + [Path(p) for p in args.run_dirs]
    elif args.run_dir:
        run_dirs = [Path(args.run_dir)]
    elif args.run_dirs:
        run_dirs = [Path(p) for p in args.run_dirs]
    else:
        raise SystemExit("Please provide --run_dir or --run_dirs.")

    # Check for smoke/sanity runs
    smoke_sanity_warning = _check_smoke_sanity_enforcement(run_dirs, args.force)
    if smoke_sanity_warning and not args.force:
        # Exit code convention:
        # - 2: intentionally blocked (smoke/sanity policy)
        # - 1: real error
        msg = (
            f"BLOCKED: Cannot build paper tables for smoke/sanity runs: {smoke_sanity_warning}\n"
            f"Use --force to override (will add DO NOT REPORT banner)."
        )
        print(msg, file=__import__("sys").stderr)
        raise SystemExit(2)

    include_splits = set(args.include_splits) if args.include_splits else None
    if include_splits:
        report_splits = include_splits
    else:
        report_splits = {args.report_split} if args.report_split else None
    build_tables_for_runs(run_dirs, report_splits, args.hard_subset_source, args.n_runs_for_consistency, args.force, smoke_sanity_warning, strict=args.strict)


if __name__ == "__main__":
    main()
