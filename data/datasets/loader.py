from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


@dataclass(frozen=True)
class InternalExample:
    """
    Unified in-memory representation for any dataset row we ingest.

    Fields:
        uid: Stable identifier for the example or turn.
        text: Input text that downstream components will consume.
        case_type: Dataset-defined case bucket (e.g., conflict, hard_negation). Defaults to "unknown".
        split: Dataset split name (train/valid/test). Defaults to "unknown".
        label: Canonical label string (polarity/emotion/etc.).
        target: Optional target/aspect/speaker the label refers to.
        span: Optional character span (start, end) for the target.
        metadata: Optional extra fields preserved for tracing.
        language_code: Language tag (BCP47 or short code), defaults to "unknown".
        domain_id: Dataset/domain bucket identifier, defaults to "unknown".
    """

    uid: str
    text: str
    case_type: str = "unknown"
    split: str = "unknown"
    label: Optional[str] = None
    target: Optional[str] = None
    span: Optional[Tuple[int, int]] = None
    metadata: Optional[Dict[str, Any]] = None
    language_code: str = "unknown"
    domain_id: str = "unknown"

    def to_record(
        self,
        *,
        include_metadata: bool = False,
        label2id: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """Convert to a flat dict for DataFrame/HF dataset creation."""
        record: Dict[str, Any] = {"uid": self.uid, "text": self.text, "case_type": self.case_type, "split": self.split}
        if self.label is not None:
            if label2id is not None:
                if self.label not in label2id:
                    raise ValueError(f"Label '{self.label}' missing in label2id mapping")
                record["label"] = label2id[self.label]
            else:
                record["label"] = self.label
        if self.target is not None:
            record["target"] = self.target
        if self.span is not None:
            record["span_start"], record["span_end"] = self.span
        if include_metadata and self.metadata:
            record.update({k: v for k, v in self.metadata.items() if v is not None})
        record["language_code"] = self.language_code or "unknown"
        record["domain_id"] = self.domain_id or "unknown"
        return record


def _clean_value(value: Any) -> Any:
    """Normalize pandas/JSON values to plain Python primitives."""
    if value is None:
        return None
    if pd.isna(value):  # type: ignore[arg-type]
        return None
    return value


def resolve_data_path(base_root: Optional[str], path: Optional[str]) -> Optional[str]:
    """
    Resolve a path against dataset_root if provided.
    - Absolute paths are returned unchanged.
    - Relative paths are joined with base_root when given.
    - None / non-str inputs are returned as-is.
    """
    if path is None or not isinstance(path, str):
        return path
    p = Path(path)
    if p.is_absolute():
        return str(p.resolve())
    if base_root:
        return str((Path(base_root) / p).resolve())
    return str(p.resolve())


class BlockedDatasetPathError(RuntimeError):
    pass


def resolve_dataset_paths(data_cfg: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str], List[str]]:
    """
    Return (resolved_cfg, resolved_paths_map, allowed_roots_abs).
    Enforces allowed_roots (default ["experiments/data"]) fail-fast on violations.
    """
    allowed_roots_cfg = data_cfg.get("allowed_roots") or ["experiments/data"]
    allowed_roots_abs = [str(Path(r).resolve()) for r in allowed_roots_cfg]
    root = data_cfg.get("dataset_root")
    root_abs = str(Path(root).resolve()) if root else None

    resolved_cfg: Dict[str, Any] = dict(data_cfg)
    resolved_cfg["dataset_root"] = root_abs if root_abs else root
    resolved_cfg["allowed_roots"] = allowed_roots_cfg
    resolved_paths: Dict[str, str] = {}

    def _check_allowed(path_str: str) -> None:
        p = Path(path_str).resolve()
        for ar in allowed_roots_abs:
            try:
                p.relative_to(ar)
                return
            except ValueError:
                continue
        raise BlockedDatasetPathError(f"Dataset path not allowed: {p}. Allowed roots: {allowed_roots_abs}")

    for k, v in data_cfg.items():
        if isinstance(v, str) and any(token in k for token in ["file", "path", "dir"]):
            new_v = resolve_data_path(root_abs, v)
            if new_v is not None:
                _check_allowed(new_v)
                resolved_paths[k] = new_v
            resolved_cfg[k] = new_v
    return resolved_cfg, resolved_paths, allowed_roots_abs


def load_csv_examples(
    csv_path: str,
    *,
    text_column: str = "text",
    label_column: Optional[str] = "label",
    target_column: Optional[str] = None,
    split: str = "unknown",
    default_language_code: str = "unknown",
    default_domain_id: str = "unknown",
) -> List[InternalExample]:
    """Load a CSV file into InternalExample rows."""
    df = pd.read_csv(csv_path)
    if text_column not in df.columns:
        raise KeyError(f"Missing text column '{text_column}' in {csv_path}")

    examples: List[InternalExample] = []
    for idx, row in df.iterrows():
        text = str(_clean_value(row[text_column]) or "")
        label = None
        if label_column and label_column in df.columns:
            label_val = _clean_value(row[label_column])
            label = None if label_val is None else str(label_val)

        target = None
        if target_column and target_column in df.columns:
            target_val = _clean_value(row[target_column])
            target = None if target_val is None else str(target_val)

        metadata: Dict[str, Any] = {}
        for col in df.columns:
            if col in {text_column, label_column, target_column}:
                continue
            cleaned = _clean_value(row[col])
            if cleaned is not None:
                metadata[col] = cleaned

        language_code = str(_clean_value(row.get("language_code")) or _clean_value(row.get("lang")) or default_language_code or "unknown")
        domain_id = str(_clean_value(row.get("domain_id")) or _clean_value(row.get("domain")) or default_domain_id or "unknown")

        case_type_val = None
        for candidate in ("case_type", "type"):
            if candidate in df.columns:
                ct_val = _clean_value(row[candidate])
                case_type_val = None if ct_val is None else str(ct_val)
                if case_type_val:
                    break

        uid_val = _clean_value(row.get("uid") or row.get("id"))
        uid_str = str(uid_val).strip() if uid_val is not None else ""
        if not uid_str:
            uid_str = f"{Path(csv_path).stem}:{idx}"

        examples.append(
            InternalExample(
                uid=uid_str,
                text=text,
                case_type=case_type_val or "unknown",
                split=split or "unknown",
                label=label,
                target=target,
                metadata=metadata or None,
                language_code=language_code or "unknown",
                domain_id=domain_id or "unknown",
            )
        )

    return examples


def load_internal_json_dir(
    json_dir: str,
    *,
    text_key: str = "Text",
    label_key: str = "VerifyEmotionCategory",
    split: str = "unknown",
    default_language_code: str = "unknown",
    default_domain_id: str = "unknown",
) -> List[InternalExample]:
    """
    Load conversation-style internal JSON files into InternalExample rows.

    Each JSON file contains a Conversation list; every turn becomes an example.
    """
    examples: List[InternalExample] = []
    for path in sorted(Path(json_dir).glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)

        file_name = obj.get("File", {}).get("FileName", Path(path).stem)
        for turn in obj.get("Conversation", []):
            text = str(_clean_value(turn.get(text_key)) or "").strip()
            if not text:
                continue
            label_val = _clean_value(turn.get(label_key))
            label = None if label_val is None else str(label_val)
            target = _clean_value(turn.get("VerifyEmotionTarget")) or _clean_value(turn.get("SpeakerEmotionTarget"))
            target = None if target is None else str(target)

            span = None
            start = _clean_value(turn.get("StartTime"))
            end = _clean_value(turn.get("EndTime"))
            if start is not None and end is not None:
                try:
                    span = (float(start), float(end))
                except (TypeError, ValueError):
                    span = None

            metadata = {
                "file": file_name,
                "text_no": _clean_value(turn.get("TextNo")),
                "speaker_no": _clean_value(turn.get("SpeakerNo")),
                "verify_target": _clean_value(turn.get("VerifyEmotionTarget")),
                "speaker_target": _clean_value(turn.get("SpeakerEmotionTarget")),
                "verify_level": _clean_value(turn.get("VerifyEmotionLevel")),
                "speaker_level": _clean_value(turn.get("SpeakerEmotionLevel")),
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}

            language_code = str(_clean_value(turn.get("language_code") or turn.get("Language")) or default_language_code or "unknown")
            domain_id = str(_clean_value(turn.get("domain_id") or turn.get("Domain")) or default_domain_id or "unknown")

            examples.append(
                InternalExample(
                    uid=f"{file_name}:{turn.get('TextNo', len(examples))}",
                    text=text,
                    case_type=str(_clean_value(turn.get("case_type") or turn.get("CaseType")) or "unknown"),
                    split=split or "unknown",
                    label=label,
                    target=target,
                    span=span,
                    metadata=metadata or None,
                    language_code=language_code or "unknown",
                    domain_id=domain_id or "unknown",
                )
            )

    if not examples:
        raise ValueError(f"No records parsed from {json_dir}")
    return examples


def load_nikluge_sa2022(jsonl_path: str, *, split: str = "unknown") -> List[InternalExample]:
    """Load the nikluge-sa-2022 train/dev/test JSONL into InternalExample rows."""
    examples: List[InternalExample] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            base_id = obj.get("id", f"nikluge-sa-2022-{line_no:05d}")
            text = str(obj.get("sentence_form", "")).strip()
            annotations = obj.get("annotation") or []
            language_code = str(obj.get("language_code") or "ko" or "unknown")
            domain_id = str(obj.get("domain_id") or "nikluge_sa2022" or "unknown")

            if not annotations:
                examples.append(
                    InternalExample(
                        uid=base_id,
                        text=text,
                        case_type="unknown",
                        split=split or "unknown",
                        label=None,
                        metadata={"source": "nikluge_sa_2022"},
                        language_code=language_code,
                        domain_id=domain_id,
                    )
                )
                continue

            for ann_idx, ann in enumerate(annotations):
                if not isinstance(ann, (list, tuple)) or len(ann) < 3:
                    continue
                target_raw, span_info, label_raw = ann
                target = None if target_raw in (None, "") else str(target_raw)
                label = None if label_raw in (None, "") else str(label_raw)

                span = None
                span_text = None
                if isinstance(span_info, (list, tuple)) and len(span_info) >= 3:
                    span_text = span_info[0]
                    start, end = span_info[1], span_info[2]
                    if start is not None and end is not None:
                        try:
                            span = (int(start), int(end))
                        except (TypeError, ValueError):
                            span = None

                meta = {"source": "nikluge_sa_2022"}
                if span_text not in (None, ""):
                    meta["span_text"] = span_text

                examples.append(
                    InternalExample(
                        uid=f"{base_id}::ann{ann_idx}",
                        text=text,
                        case_type="unknown",
                        split=split or "unknown",
                        label=label,
                        target=target,
                        span=span,
                        metadata=meta or None,
                        language_code=language_code,
                        domain_id=domain_id,
                    )
                )

    if not examples:
        raise ValueError(f"No records parsed from {jsonl_path}")
    return examples


def load_split_examples(data_cfg: Dict[str, Any], split: str) -> List[InternalExample]:
    """
    Load a specific split using the configured input_format.

    Supported formats:
        - csv: expects `<split>_file`
        - json_internal: expects `json_dir_<split>`
        - nikluge_sa_2022: expects `<split>_file`
    """
    fmt = data_cfg.get("input_format", "csv")
    root = data_cfg.get("dataset_root")
    default_language_code = data_cfg.get("language_code", "unknown")
    default_domain_id = data_cfg.get("domain_id", "unknown")
    if fmt == "csv":
        file_key = f"{split}_file"
        if file_key not in data_cfg:
            raise KeyError(f"{file_key} missing in data config for split '{split}'")
        return load_csv_examples(
            resolve_data_path(root, data_cfg[file_key]),
            text_column=data_cfg.get("text_column", "text"),
            label_column=data_cfg.get("label_column", "label"),
            target_column=data_cfg.get("target_column"),
            split=split,
            default_language_code=default_language_code,
            default_domain_id=default_domain_id,
        )
    if fmt == "json_internal":
        dir_key = f"json_dir_{split}"
        if dir_key not in data_cfg:
            raise KeyError(f"{dir_key} missing in data config for split '{split}'")
        return load_internal_json_dir(
            resolve_data_path(root, data_cfg[dir_key]),
            text_key=data_cfg.get("text_key", "Text"),
            label_key=data_cfg.get("label_key", "VerifyEmotionCategory"),
            split=split,
            default_language_code=default_language_code,
            default_domain_id=default_domain_id,
        )
    if fmt == "nikluge_sa_2022":
        file_key = f"{split}_file"
        path = resolve_data_path(root, data_cfg.get(file_key))
        if path is None:
            return []
        return load_nikluge_sa2022(path, split=split)

    raise ValueError(f"Unsupported input_format '{fmt}'")


def load_datasets(
    data_cfg: Dict[str, Any],
    splits_to_load: Optional[Sequence[str]] = None,
) -> Tuple[List[InternalExample], List[InternalExample], List[InternalExample]]:
    """
    Convenience loader for train/valid/test splits.

    When splits_to_load is None, loads all configured splits (current behavior).
    When splits_to_load is set (e.g. ["valid"]), only those splits are loaded;
    others return empty lists. Use this for eval-only runs to avoid loading train.
    """
    fmt = data_cfg.get("input_format", "csv")
    want = set(splits_to_load) if splits_to_load is not None else {"train", "valid", "test"}

    has_train = (
        (fmt == "json_internal" and "json_dir_train" in data_cfg)
        or (fmt in {"csv", "nikluge_sa_2022"} and "train_file" in data_cfg)
    )
    has_valid = (
        (fmt == "json_internal" and "json_dir_valid" in data_cfg)
        or (fmt in {"csv", "nikluge_sa_2022"} and "valid_file" in data_cfg)
    )
    has_test = (
        (fmt == "json_internal" and "json_dir_test" in data_cfg)
        or (fmt in {"csv", "nikluge_sa_2022"} and "test_file" in data_cfg)
    )

    train_examples = (
        load_split_examples(data_cfg, "train") if "train" in want and has_train else []
    )
    valid_examples = (
        load_split_examples(data_cfg, "valid") if "valid" in want and has_valid else []
    )
    test_examples = (
        load_split_examples(data_cfg, "test") if "test" in want and has_test else []
    )
    return train_examples, valid_examples, test_examples


def examples_to_dataframe(
    examples: Sequence[InternalExample],
    *,
    label2id: Optional[Dict[str, int]] = None,
    include_metadata: bool = False,
) -> pd.DataFrame:
    """Convert InternalExample list to a DataFrame with normalized columns."""
    rows = [ex.to_record(include_metadata=include_metadata, label2id=label2id) for ex in examples]
    return pd.DataFrame(rows)
