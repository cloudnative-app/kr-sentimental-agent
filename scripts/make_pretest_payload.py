import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

def safe_get(d, *keys, default=None):
    cur = d
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

def infer_case_id(rec):
    for k in ["case_id", "id", "uid", "example_id"]:
        if k in rec:
            return rec[k]
    # fallback: hash of input_text
    txt = rec.get("input_text") or rec.get("text") or ""
    return f"hash_{abs(hash(txt)) % (10**10)}"

def infer_case_type(rec):
    # prefer explicit metadata
    for k in ["case_type", "type", "meta_case_type"]:
        if k in rec:
            return rec[k]
    meta = rec.get("meta", {})
    if isinstance(meta, dict) and "case_type" in meta:
        return meta["case_type"]
    return "unknown"

def infer_pass(rec):
    # accept various key names
    if "pass" in rec:
        return bool(rec["pass"])
    if "passed" in rec:
        return bool(rec["passed"])
    if "is_pass" in rec:
        return bool(rec["is_pass"])
    # derive from fail_reason/error codes
    fr = rec.get("fail_reason")
    ec = rec.get("error_codes")
    if fr:
        return False
    if ec and len(ec) > 0:
        return False
    return True

def extract_failure_stage_fix_location(rec):
    # postprocess output already has these sometimes; otherwise look in trace/validator
    stage = rec.get("failure_stage")
    fix = rec.get("fix_location")
    if stage or fix:
        return stage, fix

    # fallback heuristics from fail_reason / error_codes
    fr = rec.get("fail_reason") or ""
    ecs = rec.get("error_codes") or []
    text = " ".join([fr] + ([str(x) for x in ecs] if isinstance(ecs, list) else [str(ecs)])).lower()

    # crude mapping (tune if your schema differs)
    if "span" in text:
        return "ATE", "prompts"
    if "other_not_target" in text or "valid_aspect" in text or "allowlist" in text or "target" in text:
        return "ATE", "target_filter/allowlist"
    if "polarity_split" in text or "polarity" in text:
        return "ATSA", "prompts"
    if "ground" in text:
        return "ATSA", "prompts"
    return None, None

def is_catastrophic(rec):
    e = (rec.get("fail_reason") or "") + " " + " ".join(rec.get("error_codes") or [])
    e = e.lower()
    for key in ["other_not_target", "polarity_split_failed", "opinion_not_grounded", "missed_aspect_in_contrast"]:
        if key in e:
            return True, key
    return False, "none"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", required=True, help="path to smoke_outputs.jsonl")
    ap.add_argument("--scorecards", required=True, help="path to scorecards_3runs.jsonl")
    ap.add_argument("--mode", default="proposed")
    ap.add_argument("--input", default="")
    ap.add_argument("--allowlist", default="")
    ap.add_argument("--out", default=None, help="Output JSON path; default is <scorecards_dir>/pretest_payload.json")
    args = ap.parse_args()

    smoke_rows = load_jsonl(Path(args.smoke))
    score_rows = load_jsonl(Path(args.scorecards))

    # smoke summary: if your smoke_outputs.jsonl is a list-like JSON, handle both
    # Some projects write smoke summary as a single JSON array in a .json (not jsonl).
    # Here we assume jsonl; if it's array-in-one-line, still loads as one row with list -> normalize.
    smoke_summary = None
    if len(smoke_rows) == 1 and isinstance(smoke_rows[0], list):
        smoke_summary = smoke_rows[0][0]
    elif len(smoke_rows) >= 1 and isinstance(smoke_rows[0], dict) and "passed" in smoke_rows[0]:
        # either first line is summary, or each line is sample; pick a summary if present
        smoke_summary = smoke_rows[0]
    else:
        smoke_summary = {"mode": args.mode, "passed": None, "total": None, "rate": None,
                         "parse_failures": None, "empty_aspects_failures": None, "errors": None,
                         "output_path": str(Path(args.smoke))}

    # stability + failures
    by_case = defaultdict(list)
    by_case_type = defaultdict(list)
    failed_case_ids = set()

    stage_counter = Counter()
    fix_counter = Counter()
    catastrophic_counter = Counter()

    for rec in score_rows:
        cid = infer_case_id(rec)
        ctype = infer_case_type(rec)
        passed = infer_pass(rec)

        by_case[cid].append(rec)
        by_case_type[ctype].append(rec)

        if not passed:
            failed_case_ids.add(cid)
            stage, fix = extract_failure_stage_fix_location(rec)
            if stage: stage_counter[stage] += 1
            if fix: fix_counter[fix] += 1

            cat, cat_type = is_catastrophic(rec)
            if cat:
                catastrophic_counter[cat_type] += 1

    # flip rates: compare runs per case_id
    pass_flips = 0
    label_flips = 0
    n_cases = 0

    # polarity extraction heuristic: expects final_result with aspects containing polarity
    def get_label_signature(rec):
        # Make a stable signature of (aspect span, polarity)
        fr = rec.get("final_result") or rec.get("final") or {}
        aspects = safe_get(fr, "aspects", default=None)
        if aspects is None:
            aspects = rec.get("final_aspects")
        if not aspects:
            return ""
        pairs = []
        for a in aspects:
            span = a.get("span") or a.get("aspect") or a.get("text") or ""
            pol = a.get("polarity") or a.get("sentiment") or ""
            pairs.append((span.strip().lower(), str(pol).strip().lower()))
        pairs.sort()
        return "|".join([f"{s}:{p}" for s,p in pairs])

    # overall + by case_type summary
    stability_by_type = {}
    for ctype, recs in by_case_type.items():
        # group by case_id for this type
        temp = defaultdict(list)
        for r in recs:
            temp[infer_case_id(r)].append(r)

        type_cases = 0
        type_pass_mean_sum = 0.0
        type_pass_worst_sum = 0.0
        type_pass_flips = 0
        type_label_flips = 0

        for cid, runs in temp.items():
            type_cases += 1
            passed_list = [infer_pass(r) for r in runs]
            pass_mean = sum(1 for x in passed_list if x) / max(1, len(passed_list))
            pass_worst = 1.0 if all(passed_list) else 0.0
            type_pass_mean_sum += pass_mean
            type_pass_worst_sum += pass_worst

            if len(set(passed_list)) > 1:
                type_pass_flips += 1

            labels = [get_label_signature(r) for r in runs]
            if len(set(labels)) > 1:
                type_label_flips += 1

        stability_by_type[ctype] = {
            "n_cases": type_cases,
            "pass_mean": round(type_pass_mean_sum / max(1, type_cases), 3),
            "pass_worst": round(type_pass_worst_sum / max(1, type_cases), 3),
            "pass_flip_rate": round(type_pass_flips / max(1, type_cases), 3),
            "label_flip_rate": round(type_label_flips / max(1, type_cases), 3),
        }

    # overall from by_case
    for cid, runs in by_case.items():
        n_cases += 1
        passed_list = [infer_pass(r) for r in runs]
        if len(set(passed_list)) > 1:
            pass_flips += 1
        labels = [get_label_signature(r) for r in runs]
        if len(set(labels)) > 1:
            label_flips += 1

    payload = {
        "MODE": args.mode,
        "ALLOWLIST_PATH": args.allowlist,
        "INPUT_JSONL_PATH": args.input,
        "SMOKE_PASSED": smoke_summary.get("passed"),
        "SMOKE_TOTAL": smoke_summary.get("total"),
        "SMOKE_RATE": smoke_summary.get("rate"),
        "PARSE_FAILURES": smoke_summary.get("parse_failures"),
        "EMPTY_ASPECTS_FAILURES": smoke_summary.get("empty_aspects_failures"),
        "ERRORS": smoke_summary.get("errors"),
        "PASS_FLIP_RATE": round(pass_flips / max(1, n_cases), 3),
        "LABEL_FLIP_RATE": round(label_flips / max(1, n_cases), 3),
        "CASE_TYPE_TABLE": stability_by_type,
        "N_FAILED_CASES": len(failed_case_ids),
        "TOP_FAILURE_STAGE": stage_counter.most_common(1)[0] if stage_counter else None,
        "TOP_FIX_LOCATION": fix_counter.most_common(1)[0] if fix_counter else None,
        "CATASTROPHIC_COUNT": sum(catastrophic_counter.values()),
        "CATASTROPHIC_BY_TYPE": dict(catastrophic_counter),
        "SMOKE_OUTPUT_PATH": smoke_summary.get("output_path"),
    }

    out_path = Path(args.out) if args.out else (Path(args.scorecards).parent / "pretest_payload.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote payload: {out_path}")

if __name__ == "__main__":
    main()
