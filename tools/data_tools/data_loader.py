from typing import Dict, Tuple, List

import pandas as pd
from pathlib import Path
import json


def load_csv_dataset(
    train_file: str,
    valid_file: str,
    test_file: str,
    text_column: str,
    label_column: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load CSV datasets for training, validation, and testing."""
    train_df = pd.read_csv(train_file)
    valid_df = pd.read_csv(valid_file)
    test_df = pd.read_csv(test_file)

    for df_name, df in {
        "train": train_df,
        "valid": valid_df,
        "test": test_df,
    }.items():
        if text_column not in df.columns:
            raise KeyError(f"{df_name} missing column: {text_column}")
        if label_column not in df.columns:
            raise KeyError(f"{df_name} missing column: {label_column}")
        df[text_column] = df[text_column].astype(str).fillna("")
        df[label_column] = df[label_column].astype(str)

    return train_df, valid_df, test_df


def apply_label_mapping(df: pd.DataFrame, label_column: str, label2id: Dict[str, int]) -> pd.DataFrame:
    """Apply label mapping to convert string labels to integer IDs."""
    unknown = sorted(set(df[label_column].unique()) - set(label2id.keys()))
    if unknown:
        raise ValueError(f"Unknown labels in dataset: {unknown}")
    df = df.copy()
    df[label_column] = df[label_column].map(label2id)
    return df


def load_internal_json_dir(
    json_dir: str,
    *,
    text_key: str = "Text",
    label_key: str = "VerifyEmotionCategory",
    include_meta: bool = True,
) -> pd.DataFrame:
    """
    지정 폴더의 내부 JSON 샘플을 평탄화하여 DataFrame으로 반환합니다.
    - 각 JSON의 Conversation 항목에서 text_key/label_key를 추출합니다.
    - 대표 라벨 필드는 기본으로 검수 기준(Verify*)을 사용합니다. 필요시 Speaker*로 변경하세요.
    """
    records: List[Dict] = []
    for path in sorted(Path(json_dir).glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        file_name = obj.get("File", {}).get("FileName", Path(path).stem)
        conv_list = obj.get("Conversation", [])
        for turn in conv_list:
            text = str(turn.get(text_key, "")).strip()
            label = str(turn.get(label_key, "")).strip()
            if not text:
                continue
            rec: Dict[str, str] = {
                "file": file_name,
                "text": text,
                "label": label,
            }
            if include_meta:
                rec.update(
                    {
                        "text_no": turn.get("TextNo"),
                        "speaker_no": turn.get("SpeakerNo"),
                        "start_time": turn.get("StartTime"),
                        "end_time": turn.get("EndTime"),
                        "verify_target": turn.get("VerifyEmotionTarget"),
                        "speaker_target": turn.get("SpeakerEmotionTarget"),
                        "verify_level": turn.get("VerifyEmotionLevel"),
                        "speaker_level": turn.get("SpeakerEmotionLevel"),
                    }
                )
            records.append(rec)

    if not records:
        raise ValueError(f"No records parsed from {json_dir}")
    return pd.DataFrame.from_records(records)

