from __future__ import annotations

from data.datasets.loader import (
    InternalExample,
    examples_to_dataframe,
    load_csv_examples,
    load_datasets,
    load_internal_json_dir,
    load_nikluge_sa2022,
    load_split_examples,
)


# Compatibility wrappers that delegate to the centralized loader in data/datasets/loader.py.
def load_csv_dataset(
    train_file: str,
    valid_file: str,
    test_file: str,
    text_column: str,
    label_column: str,
):
    train = load_csv_examples(train_file, text_column=text_column, label_column=label_column, split="train")
    valid = load_csv_examples(valid_file, text_column=text_column, label_column=label_column, split="valid")
    test = load_csv_examples(test_file, text_column=text_column, label_column=label_column, split="test")
    return (
        examples_to_dataframe(train),
        examples_to_dataframe(valid),
        examples_to_dataframe(test),
    )


def apply_label_mapping(*args, **kwargs):
    raise RuntimeError(
        "apply_label_mapping has been replaced by examples_to_dataframe(..., label2id=...). "
        "Update call sites to use the centralized loader outputs."
    )


__all__ = [
    "InternalExample",
    "examples_to_dataframe",
    "load_csv_dataset",
    "load_csv_examples",
    "load_datasets",
    "load_internal_json_dir",
    "load_nikluge_sa2022",
    "load_split_examples",
]
