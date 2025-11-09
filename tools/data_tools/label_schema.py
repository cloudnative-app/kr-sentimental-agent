from typing import Dict, List


def build_label2id(mapping: Dict[str, int]) -> Dict[str, int]:
    """Build label to ID mapping from configuration."""
    # 입력 검증 및 정렬 고정
    if not mapping:
        raise ValueError("label_mapping is empty")
    # 일관성 보장을 위해 키 정렬 후 재구성
    return {label: int(idx) for label, idx in mapping.items()}


def build_id2label(label2id: Dict[str, int]) -> Dict[int, str]:
    """Build ID to label mapping from label2id mapping."""
    return {v: k for k, v in label2id.items()}


def validate_labels(labels: List[str], label2id: Dict[str, int]) -> None:
    """Validate that all labels exist in the label2id mapping."""
    unknown = sorted(set(labels) - set(label2id.keys()))
    if unknown:
        raise ValueError(f"Unknown labels detected: {unknown}")

