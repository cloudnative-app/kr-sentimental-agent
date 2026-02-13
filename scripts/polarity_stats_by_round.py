#!/usr/bin/env python3
"""
라운드별 극성 통계·정답 극성 집계·달라진 것 표.

Triptych TSV에서 stage1_pairs, final_pairs, gold_pairs 파싱 후:
1. 라운드별(stage1/final/gold) 극성 집계: positive, negative, neutral 수
2. 정답(gold) 극성 집계
3. stage1→final 달라진 것 표 (text_id, aspect, stage1_pol, final_pol, gold_pol, changed)

Usage:
  python scripts/polarity_stats_by_round.py --run_dir results/beta_n50_c1__seed42_proposed
  python scripts/polarity_stats_by_round.py --run_dirs results/beta_n50_c2__seed42_proposed,results/beta_n50_c2__seed123_proposed,results/beta_n50_c2__seed456_proposed --out reports/polarity_stats_beta_n50_c2_per_seed.md
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _normalize_pol(p: str) -> str:
    p = (p or "").strip().lower()
    if p in ("pos", "positive"): return "positive"
    if p in ("neg", "negative"): return "negative"
    if p in ("neu", "neutral"): return "neutral"
    if p in ("mixed",): return "mixed"
    return p or "neutral"


def parse_pairs(s: str) -> List[Tuple[str, str]]:
    """Parse 'aspect1|pol1;aspect2|pol2' -> [(aspect1,pol1), (aspect2,pol2)]."""
    out = []
    if not s or not s.strip():
        return out
    for part in s.split(";"):
        part = part.strip()
        if "|" in part:
            aspect, pol = part.rsplit("|", 1)
            out.append((aspect.strip(), _normalize_pol(pol)))
        else:
            out.append((part, "neutral"))
    return out


def pairs_to_dict(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """aspect -> polarity (last wins for dupes)."""
    return dict(pairs)


def load_triptych(path: Path) -> List[Dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(r)
    return rows


def _extract_seed(run_name: str) -> str:
    """beta_n50_c2__seed42_proposed -> seed42"""
    for part in run_name.split("_"):
        if part.startswith("seed"):
            return part
    return run_name


def compute_stats(rows: List[Dict]) -> Dict:
    """Return stage1/final/gold counts, changed_rows, change_type_counts, match stats."""
    stage1_counts = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    final_counts = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    gold_counts = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    for r in rows:
        for _, pol in parse_pairs(r.get("stage1_pairs") or ""):
            stage1_counts[pol] = stage1_counts.get(pol, 0) + 1
        for _, pol in parse_pairs(r.get("final_pairs") or ""):
            final_counts[pol] = final_counts.get(pol, 0) + 1
        for _, pol in parse_pairs(r.get("gold_pairs") or ""):
            gold_counts[pol] = gold_counts.get(pol, 0) + 1

    changed_rows: List[Dict] = []
    for r in rows:
        s1 = pairs_to_dict(parse_pairs(r.get("stage1_pairs") or ""))
        s2 = pairs_to_dict(parse_pairs(r.get("final_pairs") or ""))
        gold = pairs_to_dict(parse_pairs(r.get("gold_pairs") or ""))
        text_id = r.get("text_id") or ""
        all_aspects = set(s1.keys()) | set(s2.keys())
        for asp in sorted(all_aspects):
            p1 = s1.get(asp, "—")
            p2 = s2.get(asp, "—")
            pg = gold.get(asp, "")
            if not pg and gold:
                for ga, gp in gold.items():
                    if not ga:
                        pg = gp
                        break
            if p1 != p2:
                changed_rows.append({
                    "text_id": text_id,
                    "aspect": asp or "(implicit)",
                    "stage1_polarity": p1,
                    "final_polarity": p2,
                    "gold_polarity": pg or "—",
                    "changed": "Y",
                    "change_type": f"{p1}→{p2}",
                })

    match_rows: List[Dict] = []
    for r in rows:
        final = pairs_to_dict(parse_pairs(r.get("final_pairs") or ""))
        gold = pairs_to_dict(parse_pairs(r.get("gold_pairs") or ""))
        text_id = r.get("text_id") or ""
        for asp, gpol in gold.items():
            fpol = final.get(asp, "")
            match_rows.append({"match": "Y" if fpol == gpol else "N"})

    n_match = sum(1 for r in match_rows if r["match"] == "Y")
    change_type_counts = Counter(r.get("change_type", "") for r in changed_rows)
    return {
        "stage1": stage1_counts,
        "final": final_counts,
        "gold": gold_counts,
        "changed_rows": changed_rows,
        "change_type_counts": change_type_counts,
        "n_match": n_match,
        "n_gold_aspects": len(match_rows),
        "n_samples": len(rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Polarity stats by round, gold agg, changed table")
    ap.add_argument("--run_dir", type=str, help="Single run directory")
    ap.add_argument("--run_dirs", type=str, help="Comma-separated run dirs (시드별 병합 없이 열로 표시)")
    ap.add_argument("--triptych", type=str, help="Direct path to triptych TSV")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    # --- Multi-seed mode (--run_dirs): 시드별 열, 병합 없음 ---
    if args.run_dirs:
        run_dirs = [Path(p.strip()).resolve() for p in args.run_dirs.split(",") if p.strip()]
        seeds_data: List[Tuple[str, Path, Dict]] = []
        for rd in run_dirs:
            tp = rd / "derived" / "tables" / "triptych_table.tsv"
            if not tp.exists():
                print(f"[WARN] Skip {rd.name}: triptych not found", flush=True)
                continue
            rows = load_triptych(tp)
            stats = compute_stats(rows)
            seed_label = _extract_seed(rd.name)
            seeds_data.append((seed_label, tp, stats))
        if not seeds_data:
            print("[ERROR] No valid runs found.", flush=True)
            return

        seed_labels = [s[0] for s in seeds_data]
        header = "| Metric | " + " | ".join(seed_labels) + " |"
        sep = "|-------|" + "|".join(["--------" for _ in seed_labels]) + "|"

        lines = [
            "# 라운드별 극성 통계 (시드별, 병합 없음)",
            "",
            f"**Runs**: {', '.join(s[1].parent.parent.parent.name for s in seeds_data)}",
            "",
            "---",
            "",
            "## 1. 라운드별 극성 집계 (시드별)",
            "",
            header,
            sep,
        ]
        metrics = [
            ("stage1_positive", "stage1", "positive"),
            ("stage1_negative", "stage1", "negative"),
            ("stage1_neutral", "stage1", "neutral"),
            ("stage1_total", "stage1", "__sum__"),
            ("final_positive", "final", "positive"),
            ("final_negative", "final", "negative"),
            ("final_neutral", "final", "neutral"),
            ("final_total", "final", "__sum__"),
            ("gold_positive", "gold", "positive"),
            ("gold_negative", "gold", "negative"),
            ("gold_neutral", "gold", "neutral"),
            ("gold_total", "gold", "__sum__"),
            ("changed_rows", None, None),
            ("final_vs_gold_match", None, None),
        ]
        for mname, round_key, pol_key in metrics:
            if round_key and pol_key:
                if pol_key == "__sum__":
                    vals = [str(sum(s[2][round_key].values())) for s in seeds_data]
                else:
                    vals = [str(s[2][round_key].get(pol_key, 0)) for s in seeds_data]
            elif mname == "changed_rows":
                vals = [str(len(s[2]["changed_rows"])) for s in seeds_data]
            elif mname == "final_vs_gold_match":
                vals = [f"{s[2]['n_match']}/{s[2]['n_gold_aspects']}" for s in seeds_data]
            else:
                vals = ["—"] * len(seeds_data)
            lines.append("| " + mname + " | " + " | ".join(vals) + " |")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 2. 변경 유형별 요약 (시드별)")
        lines.append("")
        lines.append("| stage1→final | " + " | ".join(seed_labels) + " |")
        lines.append("|--------------|" + "|".join(["--------" for _ in seed_labels]) + "|")

        all_change_types = set()
        for _, _, st in seeds_data:
            all_change_types.update(st["change_type_counts"].keys())
        for ct in sorted(all_change_types):
            row = [str(st["change_type_counts"].get(ct, 0)) for _, _, st in seeds_data]
            lines.append(f"| {ct} | " + " | ".join(row) + " |")
        if not all_change_types:
            lines.append("(변경 없음)")
        lines.append("")

        base = re.sub(r"__seed\d+_proposed$", "", run_dirs[0].name)
        out_path = Path(args.out) if args.out else PROJECT_ROOT / "reports" / f"polarity_stats_{base}_per_seed.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[OK] Wrote {out_path} (시드별)")
        return

    # --- Single-run mode ---
    if args.run_dir:
        triptych_path = Path(args.run_dir) / "derived" / "tables" / "triptych_table.tsv"
    elif args.triptych:
        triptych_path = Path(args.triptych)
    else:
        ap.error("--run_dir, --run_dirs, or --triptych required")

    if not triptych_path.exists():
        print(f"[ERROR] Triptych not found: {triptych_path}", flush=True)
        print("Run: python scripts/generate_triptych_and_count_conflicts.py --run_dir <run> first.")
        return

    rows = load_triptych(triptych_path)
    stats = compute_stats(rows)
    stage1_counts = stats["stage1"]
    final_counts = stats["final"]
    gold_counts = stats["gold"]
    changed_rows = stats["changed_rows"]
    change_type_counts = stats["change_type_counts"]

    # match_rows for section 3
    match_rows: List[Dict] = []
    for r in rows:
        final = pairs_to_dict(parse_pairs(r.get("final_pairs") or ""))
        gold = pairs_to_dict(parse_pairs(r.get("gold_pairs") or ""))
        text_id = r.get("text_id") or ""
        for asp, gpol in gold.items():
            fpol = final.get(asp, "")
            match_rows.append({
                "text_id": text_id,
                "aspect": asp or "(implicit)",
                "final_polarity": fpol or "—",
                "gold_polarity": gpol,
                "match": "Y" if fpol == gpol else "N",
            })

    # Output
    lines = [
        "# 라운드별 극성 통계 및 정답 극성 집계",
        "",
        f"**Source**: {triptych_path}  |  **n_samples**: {len(rows)}",
        "",
        "---",
        "",
        "## 1. 라운드별 극성 집계 (튜플 수)",
        "",
        "| Round | positive | negative | neutral | mixed | total |",
        "|-------|----------|----------|---------|-------|-------|",
    ]
    for name, cnt in [("stage1", stage1_counts), ("final", final_counts), ("gold", gold_counts)]:
        tot = sum(cnt.values())
        lines.append(f"| {name} | {cnt.get('positive',0)} | {cnt.get('negative',0)} | {cnt.get('neutral',0)} | {cnt.get('mixed',0)} | {tot} |")
    lines.append("")

    lines.extend([
        "---",
        "",
        "## 2. stage1→final 달라진 것",
        "",
    ])
    if change_type_counts:
        lines.append("### 변경 유형별 요약")
        lines.append("")
        lines.append("| stage1→final | count |")
        lines.append("|--------------|-------|")
        for ct, n in sorted(change_type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {ct} | {n} |")
        lines.append("")

    if changed_rows:
        lines.append("### 상세 (stage1≠final)")
        lines.append("")
        lines.append("| text_id | aspect | stage1 | final | gold | 변경유형 |")
        lines.append("|---------|--------|--------|-------|------|----------|")
        for row in changed_rows[:100]:
            lines.append(f"| {row['text_id']} | {row['aspect']} | {row['stage1_polarity']} | {row['final_polarity']} | {row['gold_polarity']} | {row['change_type']} |")
        if len(changed_rows) > 100:
            lines.append(f"| ... | ({len(changed_rows)} rows total) | | | | |")
        lines.append("")
    else:
        lines.append("(없음)")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 3. final vs gold (정답 일치)",
        "",
    ])
    if match_rows:
        n_match = stats["n_match"]
        n_total = stats["n_gold_aspects"]
        lines.append(f"*gold와 match 가능한 aspect 수: {n_total}, 일치: {n_match}*")
        lines.append("")
        lines.append("| text_id | aspect | final_polarity | gold_polarity | match |")
        lines.append("|---------|--------|----------------|---------------|-------|")
        for row in match_rows[:50]:
            lines.append(f"| {row['text_id']} | {row['aspect']} | {row['final_polarity']} | {row['gold_polarity']} | {row['match']} |")
        if len(match_rows) > 50:
            lines.append(f"| ... | ({len(match_rows)} rows total) | | | |")
    else:
        lines.append("(gold 없음 또는 implicit only)")
    lines.append("")

    if args.out:
        out_path = Path(args.out)
    else:
        run_name = Path(args.run_dir).name if args.run_dir else triptych_path.parent.parent.name
        out_path = PROJECT_ROOT / "reports" / f"polarity_stats_{run_name}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    print(f"  stage1: pos={stage1_counts['positive']} neg={stage1_counts['negative']} neu={stage1_counts['neutral']}")
    print(f"  final:  pos={final_counts['positive']} neg={final_counts['negative']} neu={final_counts['neutral']}")
    print(f"  gold:   pos={gold_counts['positive']} neg={gold_counts['negative']} neu={gold_counts['neutral']}")
    print(f"  changed rows: {len(changed_rows)}")


if __name__ == "__main__":
    main()
