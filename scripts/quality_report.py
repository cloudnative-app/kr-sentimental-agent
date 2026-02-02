"""
Quality report orchestrator.

Inputs (default paths):
- experiments/results/proposed/smoke_outputs.jsonl
- experiments/results/proposed/scorecards.jsonl (auto-generated if missing via scorecard_from_smoke.py)
- conflict_a_exclamations.jsonl
- conflict_b_targetless.jsonl
- conflict_c_mixed.jsonl

Outputs (default outdir=experiments/reports/proposed):
1) table_quality_overall.csv
2) table_quality_by_bucket.csv
3) error_profile_by_bucket.json
4) examples_bucket_a.md / examples_bucket_b.md / examples_bucket_c.md
5) ablation_quality_delta.csv
6) policy_card.md
7) fig_bucket_quality.png, fig_ablation_delta.png (best-effort; skipped if matplotlib unavailable)

Notes:
- Streaming JSONL reader to stay memory-safe.
- Deterministic sampling with seed=42.
- Buckets: "proposed" for smoke/scorecards, "a"/"b"/"c" for conflict sets.
- Ablation modes expected (if available): proposed, abl_no_stage2, abl_no_moderator, abl_no_validator.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SEED = 42
random.seed(SEED)
CONTRAST_TOKENS = ["지만", "는데", "그러나", "하지만", "반면", "반면에"]


def read_jsonl_stream(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def ensure_scorecards(smoke_path: Path, scorecard_path: Path):
    if scorecard_path.exists():
        return
    from subprocess import run, CalledProcessError

    cmd = ["python", "scripts/scorecard_from_smoke.py", "--smoke", str(smoke_path)]
    try:
        result = run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout.strip())
    except CalledProcessError as e:
        raise SystemExit(f"failed to generate scorecards via scorecard_from_smoke.py: {e.stderr}")


def backup_if_needed(path: Path, enable_backup: bool):
    if not enable_backup or not path.exists():
        return
    suffix = path.suffix
    backup_path = path.with_name(path.stem + f".bak.{SEED}" + suffix)
    shutil.copy2(path, backup_path)


def agg_mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0
    return statistics.mean(values), statistics.stdev(values)


def get_aspects_for_card(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Retrieve aspects with maximum recall, preferring stage1 meta then filtered aspects.
    """
    meta = card.get("meta", {}) or {}
    inputs = card.get("inputs", {}) or {}
    if meta.get("stage1_aspects"):
        return meta["stage1_aspects"]
    keeps = [a for a in inputs.get("filtered_aspects", []) if a.get("action") == "keep"]
    if keeps:
        return keeps
    ate_debug = inputs.get("ate_debug", {}) or {}
    if ate_debug.get("filtered"):
        return ate_debug["filtered"]
    if ate_debug.get("raw"):
        return ate_debug["raw"]
    return []


def get_polarities_for_card(card: Dict[str, Any]) -> List[str]:
    inputs = card.get("inputs", {}) or {}
    sentiments = inputs.get("aspect_sentiments") or []
    pols = []
    for s in sentiments:
        pol = s.get("polarity")
        if pol:
            pols.append(pol)
    return pols


def collect_metrics_from_scorecards(cards_path: Path, bucket_name: str) -> Dict[str, Any]:
    bucket_records: List[Dict[str, Any]] = []
    drop_counts = Counter()
    issue_counts = Counter()
    fail_counts = Counter()
    quality_pass_flags: List[bool] = []
    targeted_n = 0
    targetless_n = 0
    pass_targeted = 0
    pass_targetless = 0
    metric_store = defaultdict(list)
    contrast_total = 0
    contrast_with_two_aspects = 0
    contrast_with_polarity_split = 0

    for card in read_jsonl_stream(cards_path):
        bucket_records.append(card)
        meta = card.get("meta", {})
        inputs = card.get("inputs", {})
        text = meta.get("input_text", "")
        has_contrast = any(tok in text for tok in CONTRAST_TOKENS)
        if has_contrast:
            contrast_total += 1
            aspects = get_aspects_for_card(card)
            if len(aspects) >= 2:
                contrast_with_two_aspects += 1
                pols = set(get_polarities_for_card(card))
                if len(pols.intersection({"positive", "negative"})) == 2:
                    contrast_with_polarity_split += 1

        # Confidence priority:
        # 1) mean of aspect_sentiments confidences if present
        # 2) sentence_sentiment.confidence (targetless)
        # 3) final_confidence_score/meta
        aspect_sentiments = inputs.get("aspect_sentiments") or []
        aspect_conf_values = [
            s.get("confidence", 0.0) for s in aspect_sentiments if isinstance(s, dict) and s.get("confidence") is not None
        ]
        meta_conf = 0.0
        if aspect_conf_values:
            meta_conf = sum(aspect_conf_values) / len(aspect_conf_values)
        else:
            ss = inputs.get("sentence_sentiment") or {}
            if ss:
                meta_conf = ss.get("confidence", 0.0)
            if not meta_conf:
                meta_conf = meta.get("final_confidence_score", 0.0)
                if not meta_conf and "final_result" in card:
                    meta_conf = card["final_result"].get("confidence", 0.0)

        ate = card.get("ate_score", {})
        atsa = card.get("atsa_score", {})
        policy = card.get("stage_policy_score", {})
        summary = card.get("summary", {})
        debate = card.get("debate") or {}
        mapping_stats = debate.get("mapping_stats") or (card.get("meta") or {}).get("debate_mapping_stats") or {}
        mapping_fail = debate.get("mapping_fail_reasons") or (card.get("meta") or {}).get("debate_mapping_fail_reasons") or {}
        total_maps = sum(int(v) for v in mapping_stats.values()) if mapping_stats else 0
        if total_maps > 0:
            direct = int(mapping_stats.get("direct") or 0)
            fallback = int(mapping_stats.get("fallback") or 0)
            none = int(mapping_stats.get("none") or 0)
            metric_store["debate_mapping_coverage"].append((direct + fallback) / total_maps)
            metric_store["debate_mapping_direct_rate"].append(direct / total_maps)
            metric_store["debate_mapping_fallback_rate"].append(fallback / total_maps)
            metric_store["debate_mapping_none_rate"].append(none / total_maps)
            metric_store["debate_fail_no_aspects_rate"].append(int(mapping_fail.get("no_aspects") or 0) / total_maps)
            metric_store["debate_fail_no_match_rate"].append(int(mapping_fail.get("no_match") or 0) / total_maps)
            metric_store["debate_fail_neutral_stance_rate"].append(int(mapping_fail.get("neutral_stance") or 0) / total_maps)
            metric_store["debate_fail_fallback_used_rate"].append(int(mapping_fail.get("fallback_used") or 0) / total_maps)

        metric_store["confidence"].append(meta_conf)
        # Skip None (NA) metrics to keep averages meaningful for targetless cases
        va = ate.get("valid_aspect_rate")
        if va is not None:
            metric_store["valid_target_rate"].append(va)
        og = atsa.get("opinion_grounded_rate")
        if og is not None:
            metric_store["opinion_grounded_rate"].append(og)
        evr = atsa.get("evidence_relevance_score")
        if evr is not None:
            metric_store["evidence_relevance_score"].append(evr)
        metric_store["targetless_expected"].append(1.0 if policy.get("targetless_expected") else 0.0)

        passed = bool(summary.get("quality_pass", False))
        quality_pass_flags.append(passed)
        if policy.get("targetless_expected"):
            targetless_n += 1
            if passed:
                pass_targetless += 1
        else:
            targeted_n += 1
            if passed:
                pass_targeted += 1

        for fa in inputs.get("filtered_aspects", []):
            dr = fa.get("drop_reason")
            if dr:
                drop_counts[dr] += 1

        for j in atsa.get("sentiment_judgements", []):
            for issue in j.get("issues", []):
                issue_counts[issue] += 1

        for fr in summary.get("fail_reasons", []):
            fail_counts[fr] += 1

    stats = {
        "bucket": bucket_name,
        "n": len(bucket_records),
        "mean_confidence": agg_mean_std(metric_store["confidence"]),
        "valid_target_rate": agg_mean_std(metric_store["valid_target_rate"]),
        "opinion_grounded_rate": agg_mean_std(metric_store["opinion_grounded_rate"]),
        "evidence_relevance_score": agg_mean_std(metric_store["evidence_relevance_score"]),
        "targetless_ratio": sum(metric_store["targetless_expected"]) / len(metric_store["targetless_expected"])
        if metric_store["targetless_expected"]
        else 0.0,
        "pass_rate": sum(quality_pass_flags) / len(quality_pass_flags) if quality_pass_flags else 0.0,
        "n_targeted": targeted_n,
        "n_targetless": targetless_n,
        "pass_targeted_rate": (pass_targeted / targeted_n) if targeted_n else 0.0,
        "pass_targetless_rate": (pass_targetless / targetless_n) if targetless_n else 0.0,
        "drop_top": drop_counts.most_common(10),
        "issue_top": issue_counts.most_common(10),
        "fail_top": fail_counts.most_common(10),
        "records": bucket_records,
        # Contrast metrics
        "contrast_sentence_rate": (contrast_total / len(bucket_records)) if bucket_records else 0.0,
        "contrast_aspect_coverage_rate": (contrast_with_two_aspects / contrast_total) if contrast_total else 0.0,
        "contrast_polarity_split_rate": (contrast_with_polarity_split / contrast_with_two_aspects) if contrast_with_two_aspects else 0.0,
        "debate_mapping_coverage": agg_mean_std(metric_store["debate_mapping_coverage"]),
        "debate_mapping_direct_rate": agg_mean_std(metric_store["debate_mapping_direct_rate"]),
        "debate_mapping_fallback_rate": agg_mean_std(metric_store["debate_mapping_fallback_rate"]),
        "debate_mapping_none_rate": agg_mean_std(metric_store["debate_mapping_none_rate"]),
        "debate_fail_no_aspects_rate": agg_mean_std(metric_store["debate_fail_no_aspects_rate"]),
        "debate_fail_no_match_rate": agg_mean_std(metric_store["debate_fail_no_match_rate"]),
        "debate_fail_neutral_stance_rate": agg_mean_std(metric_store["debate_fail_neutral_stance_rate"]),
        "debate_fail_fallback_used_rate": agg_mean_std(metric_store["debate_fail_fallback_used_rate"]),
    }
    return stats


def write_overall_table(stats: Dict[str, Any], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "metric",
                "mean",
                "std",
                "n",
                "pass_rate",
                "pass_targeted_rate",
                "pass_targetless_rate",
                "n_targeted",
                "n_targetless",
            ]
        )
        writer.writerow(
            [
                "mean_confidence",
                f"{stats['mean_confidence'][0]:.4f}",
                f"{stats['mean_confidence'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                f"{stats['pass_targeted_rate']:.4f}",
                f"{stats['pass_targetless_rate']:.4f}",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "valid_target_rate",
                f"{stats['valid_target_rate'][0]:.4f}",
                f"{stats['valid_target_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "opinion_grounded_rate",
                f"{stats['opinion_grounded_rate'][0]:.4f}",
                f"{stats['opinion_grounded_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "evidence_relevance_score",
                f"{stats['evidence_relevance_score'][0]:.4f}",
                f"{stats['evidence_relevance_score'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "targetless_ratio",
                f"{stats['targetless_ratio']:.4f}",
                "0.0000",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                f"{stats['pass_targeted_rate']:.4f}",
                f"{stats['pass_targetless_rate']:.4f}",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "contrast_sentence_rate",
                f"{stats['contrast_sentence_rate']:.4f}",
                "0.0000",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                f"{stats['pass_targeted_rate']:.4f}",
                f"{stats['pass_targetless_rate']:.4f}",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "contrast_aspect_coverage_rate",
                f"{stats['contrast_aspect_coverage_rate']:.4f}",
                "0.0000",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                f"{stats['pass_targeted_rate']:.4f}",
                f"{stats['pass_targetless_rate']:.4f}",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "contrast_polarity_split_rate",
                f"{stats['contrast_polarity_split_rate']:.4f}",
                "0.0000",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                f"{stats['pass_targeted_rate']:.4f}",
                f"{stats['pass_targetless_rate']:.4f}",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_mapping_coverage",
                f"{stats['debate_mapping_coverage'][0]:.4f}",
                f"{stats['debate_mapping_coverage'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_mapping_direct_rate",
                f"{stats['debate_mapping_direct_rate'][0]:.4f}",
                f"{stats['debate_mapping_direct_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_mapping_fallback_rate",
                f"{stats['debate_mapping_fallback_rate'][0]:.4f}",
                f"{stats['debate_mapping_fallback_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_mapping_none_rate",
                f"{stats['debate_mapping_none_rate'][0]:.4f}",
                f"{stats['debate_mapping_none_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_fail_no_aspects_rate",
                f"{stats['debate_fail_no_aspects_rate'][0]:.4f}",
                f"{stats['debate_fail_no_aspects_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_fail_no_match_rate",
                f"{stats['debate_fail_no_match_rate'][0]:.4f}",
                f"{stats['debate_fail_no_match_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_fail_neutral_stance_rate",
                f"{stats['debate_fail_neutral_stance_rate'][0]:.4f}",
                f"{stats['debate_fail_neutral_stance_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )
        writer.writerow(
            [
                "debate_fail_fallback_used_rate",
                f"{stats['debate_fail_fallback_used_rate'][0]:.4f}",
                f"{stats['debate_fail_fallback_used_rate'][1]:.4f}",
                stats["n"],
                f"{stats['pass_rate']:.4f}",
                "",
                "",
                stats["n_targeted"],
                stats["n_targetless"],
            ]
        )


def write_bucket_table(by_bucket: Dict[str, Dict[str, Any]], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "bucket",
                "metric",
                "mean",
                "std",
                "n",
                "pass_rate",
                "pass_targeted_rate",
                "pass_targetless_rate",
                "n_targeted",
                "n_targetless",
            ]
        )
        for bucket, stats in by_bucket.items():
            writer.writerow(
                [
                    bucket,
                    "mean_confidence",
                    f"{stats['mean_confidence'][0]:.4f}",
                    f"{stats['mean_confidence'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    f"{stats['pass_targeted_rate']:.4f}",
                    f"{stats['pass_targetless_rate']:.4f}",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "valid_target_rate",
                    f"{stats['valid_target_rate'][0]:.4f}",
                    f"{stats['valid_target_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "opinion_grounded_rate",
                    f"{stats['opinion_grounded_rate'][0]:.4f}",
                    f"{stats['opinion_grounded_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "evidence_relevance_score",
                    f"{stats['evidence_relevance_score'][0]:.4f}",
                    f"{stats['evidence_relevance_score'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "targetless_ratio",
                    f"{stats['targetless_ratio']:.4f}",
                    "0.0000",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    f"{stats['pass_targeted_rate']:.4f}",
                    f"{stats['pass_targetless_rate']:.4f}",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "contrast_sentence_rate",
                    f"{stats['contrast_sentence_rate']:.4f}",
                    "0.0000",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    f"{stats['pass_targeted_rate']:.4f}",
                    f"{stats['pass_targetless_rate']:.4f}",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "contrast_aspect_coverage_rate",
                    f"{stats['contrast_aspect_coverage_rate']:.4f}",
                    "0.0000",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    f"{stats['pass_targeted_rate']:.4f}",
                    f"{stats['pass_targetless_rate']:.4f}",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "contrast_polarity_split_rate",
                    f"{stats['contrast_polarity_split_rate']:.4f}",
                    "0.0000",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    f"{stats['pass_targeted_rate']:.4f}",
                    f"{stats['pass_targetless_rate']:.4f}",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_mapping_coverage",
                    f"{stats['debate_mapping_coverage'][0]:.4f}",
                    f"{stats['debate_mapping_coverage'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_mapping_direct_rate",
                    f"{stats['debate_mapping_direct_rate'][0]:.4f}",
                    f"{stats['debate_mapping_direct_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_mapping_fallback_rate",
                    f"{stats['debate_mapping_fallback_rate'][0]:.4f}",
                    f"{stats['debate_mapping_fallback_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_mapping_none_rate",
                    f"{stats['debate_mapping_none_rate'][0]:.4f}",
                    f"{stats['debate_mapping_none_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_fail_no_aspects_rate",
                    f"{stats['debate_fail_no_aspects_rate'][0]:.4f}",
                    f"{stats['debate_fail_no_aspects_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_fail_no_match_rate",
                    f"{stats['debate_fail_no_match_rate'][0]:.4f}",
                    f"{stats['debate_fail_no_match_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_fail_neutral_stance_rate",
                    f"{stats['debate_fail_neutral_stance_rate'][0]:.4f}",
                    f"{stats['debate_fail_neutral_stance_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )
            writer.writerow(
                [
                    bucket,
                    "debate_fail_fallback_used_rate",
                    f"{stats['debate_fail_fallback_used_rate'][0]:.4f}",
                    f"{stats['debate_fail_fallback_used_rate'][1]:.4f}",
                    stats["n"],
                    f"{stats['pass_rate']:.4f}",
                    "",
                    "",
                    stats["n_targeted"],
                    stats["n_targetless"],
                ]
            )


def write_error_profile(by_bucket: Dict[str, Dict[str, Any]], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    payload = {}
    for bucket, stats in by_bucket.items():
        payload[bucket] = {
            "drop_reason_top": stats["drop_top"],
            "issue_top": stats["issue_top"],
            "fail_top": stats["fail_top"],
        }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_examples(records: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    if not records:
        return []
    random.shuffle(records)
    return records[: min(k, len(records))]


def write_examples_md(bucket: str, stats: Dict[str, Any], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    samples = sample_examples(stats.get("records", []), k=10)
    lines = [f"# Examples for bucket {bucket}", ""]
    for i, card in enumerate(samples, 1):
        meta = card.get("meta", {})
        inputs = card.get("inputs", {})
        lines.append(f"## Example {i}")
        lines.append(f"- text_id: {meta.get('text_id','')}")
        lines.append(f"- input_text: {meta.get('input_text','')}")
        lines.append(f"- kept_aspects: {[a['term'] for a in inputs.get('filtered_aspects', []) if a.get('action')=='keep']}")
        lines.append(f"- sentiments: {[s.get('polarity') for s in inputs.get('aspect_sentiments', [])]}")
        lines.append(f"- sentence_sentiment: {inputs.get('sentence_sentiment')}")
        lines.append(f"- summary_pass: {card.get('summary', {}).get('quality_pass')}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def load_conflict_texts(path: Path, bucket: str) -> List[Dict[str, Any]]:
    records = []
    for row in read_jsonl_stream(path):
        text = row.get("text") or row.get("sentence") or ""
        records.append({"meta": {"bucket": bucket}, "text": text})
    return records


def write_policy_card(by_bucket: Dict[str, Dict[str, Any]], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    lines = ["# Policy Card", ""]
    for bucket, stats in by_bucket.items():
        lines.append(f"## Bucket {bucket}")
        lines.append(f"- pass_rate: {stats['pass_rate']:.2f}")
        lines.append(f"- targetless_ratio: {stats['targetless_ratio']:.2f}")
        lines.append(f"- contrast_aspect_coverage_rate: {stats.get('contrast_aspect_coverage_rate', 0.0):.2f}")
        lines.append(f"- dominant_drop_reason: {stats['drop_top'][0][0] if stats['drop_top'] else 'n/a'}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def ablation_metrics(modes: List[str], base_mode: str, results_root: Path) -> List[Dict[str, Any]]:
    rows = []
    base_stats = None
    collected = {}
    for mode in modes:
        smoke_path = results_root / mode / "smoke_outputs.jsonl"
        if not smoke_path.exists():
            continue
        score_path = smoke_path.parent / "scorecards.jsonl"
        ensure_scorecards(smoke_path, score_path)
        stats = collect_metrics_from_scorecards(score_path, mode)
        collected[mode] = stats
        if mode == base_mode:
            base_stats = stats
    if not base_stats:
        return rows
    base_means = {
        "mean_confidence": base_stats["mean_confidence"][0],
        "valid_target_rate": base_stats["valid_target_rate"][0],
        "opinion_grounded_rate": base_stats["opinion_grounded_rate"][0],
        "evidence_relevance_score": base_stats["evidence_relevance_score"][0],
        "pass_rate": base_stats["pass_rate"],
    }
    for mode, stats in collected.items():
        if mode == base_mode:
            continue
        rows.append(
            {
                "mode": mode,
                "delta_mean_confidence": stats["mean_confidence"][0] - base_means["mean_confidence"],
                "delta_valid_target_rate": stats["valid_target_rate"][0] - base_means["valid_target_rate"],
                "delta_opinion_grounded_rate": stats["opinion_grounded_rate"][0] - base_means["opinion_grounded_rate"],
                "delta_evidence_relevance_score": stats["evidence_relevance_score"][0] - base_means["evidence_relevance_score"],
                "delta_pass_rate": stats["pass_rate"] - base_means["pass_rate"],
            }
        )
    return rows


def write_ablation_csv(rows: List[Dict[str, Any]], out_path: Path, backup: bool):
    backup_if_needed(out_path, backup)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "mode",
                "delta_mean_confidence",
                "delta_valid_target_rate",
                "delta_opinion_grounded_rate",
                "delta_evidence_relevance_score",
                "delta_pass_rate",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def maybe_plot_bucket_quality(by_bucket: Dict[str, Dict[str, Any]], out_path: Path):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    buckets = list(by_bucket.keys())
    means = [by_bucket[b]["pass_rate"] for b in buckets]
    plt.figure(figsize=(6, 4))
    plt.bar(buckets, means)
    plt.ylabel("pass_rate")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def maybe_plot_ablation(rows: List[Dict[str, Any]], out_path: Path):
    if not rows:
        return
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return
    modes = [r["mode"] for r in rows]
    deltas = [r["delta_pass_rate"] for r in rows]
    plt.figure(figsize=(6, 4))
    plt.bar(modes, deltas)
    plt.ylabel("delta_pass_rate vs proposed")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=str, default="experiments/results/proposed/smoke_outputs.jsonl")
    ap.add_argument("--scorecards", type=str, default=None, help="optional explicit scorecards path")
    ap.add_argument("--conflict_a", type=str, default="conflict_a_exclamations.jsonl")
    ap.add_argument("--conflict_b", type=str, default="conflict_b_targetless.jsonl")
    ap.add_argument("--conflict_c", type=str, default="conflict_c_mixed.jsonl")
    ap.add_argument("--outdir", type=str, default="experiments/reports/proposed")
    ap.add_argument("--backup", type=int, default=0)
    args = ap.parse_args()

    smoke_path = Path(args.smoke)
    if not smoke_path.exists():
        raise SystemExit(f"missing smoke_outputs: {smoke_path}")

    score_path = Path(args.scorecards) if args.scorecards else smoke_path.parent / "scorecards.jsonl"
    ensure_scorecards(smoke_path, score_path)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Metrics for main bucket (proposed)
    main_stats = collect_metrics_from_scorecards(score_path, bucket_name="proposed")
    by_bucket = {"proposed": main_stats}

    # Conflicts: just count presence (no outputs), we only create example files
    conflict_map = {
        "a": Path(args.conflict_a),
        "b": Path(args.conflict_b),
        "c": Path(args.conflict_c),
    }
    for bucket, cpath in conflict_map.items():
        if cpath.exists():
            recs = load_conflict_texts(cpath, bucket)
            by_bucket[bucket] = {
                "bucket": bucket,
                "n": len(recs),
                "mean_confidence": (0.0, 0.0),
                "valid_target_rate": (0.0, 0.0),
                "opinion_grounded_rate": (0.0, 0.0),
                "evidence_relevance_score": (0.0, 0.0),
                "targetless_ratio": 1.0,
                "pass_rate": 0.0,
                "n_targeted": 0,
                "n_targetless": len(recs),
                "pass_targeted_rate": 0.0,
                "pass_targetless_rate": 0.0,
                "drop_top": [],
                "issue_top": [],
                "fail_top": [],
                "records": recs,
                "contrast_sentence_rate": 0.0,
                "contrast_aspect_coverage_rate": 0.0,
                "contrast_polarity_split_rate": 0.0,
            }

    # Write overall and bucket tables
    write_overall_table(main_stats, outdir / "table_quality_overall.csv", bool(args.backup))
    write_bucket_table(by_bucket, outdir / "table_quality_by_bucket.csv", bool(args.backup))
    write_error_profile(by_bucket, outdir / "error_profile_by_bucket.json", bool(args.backup))

    # Examples per conflict bucket
    for bucket in ("a", "b", "c"):
        if bucket in by_bucket:
            write_examples_md(bucket, by_bucket[bucket], outdir / f"examples_bucket_{bucket}.md", bool(args.backup))

    # Policy card
    write_policy_card(by_bucket, outdir / "policy_card.md", bool(args.backup))

    # Ablation delta (if data present)
    ablation_rows = ablation_metrics(
        modes=["proposed", "abl_no_stage2", "abl_no_moderator", "abl_no_validator"],
        base_mode="proposed",
        results_root=Path("experiments/results"),
    )
    write_ablation_csv(ablation_rows, outdir / "ablation_quality_delta.csv", bool(args.backup))

    # Figures best-effort
    maybe_plot_bucket_quality(by_bucket, outdir / "fig_bucket_quality.png")
    maybe_plot_ablation(ablation_rows, outdir / "fig_ablation_delta.png")

    # Overall report summary (JSON)
    report_json = {
        "meta": {"seed": SEED, "scorecards": str(score_path), "outdir": str(outdir)},
        "buckets": {k: {kk: vv for kk, vv in v.items() if kk != "records"} for k, v in by_bucket.items()},
    }
    summary_path = outdir / "quality_report.json"
    backup_if_needed(summary_path, bool(args.backup))
    summary_path.write_text(json.dumps(report_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[quality_report] wrote outputs to {outdir}")


if __name__ == "__main__":
    main()
