"""
KR Sentiment Agent - 한국어 감성분석 멀티 에이전트 시스템

이 패키지는 한국어 텍스트의 감성을 분석하기 위한 멀티 에이전트 시스템을 제공합니다.
다양한 LLM과 전통적인 ML 모델을 지원하며, 프로덕션 환경에 적합한 구조로 설계되었습니다.
"""

__version__ = "2.0.0"
__author__ = "KR Sentiment Team"
__email__ = "contact@kr-sentiment.com"

# 주요 모듈들을 쉽게 import할 수 있도록 설정
from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from agents.supervisor_agent import SupervisorAgent
from tools.data_tools import (
    InternalExample,
    build_id2label,
    build_label2id,
    examples_to_dataframe,
    load_csv_dataset,
    load_csv_examples,
    load_datasets,
    load_internal_json_dir,
    load_nikluge_sa2022,
    load_split_examples,
)

__all__ = [
    # Traditional Agents
    "ATEAgent",
    "ATSAAgent",
    "ValidatorAgent",
    "Moderator",
    "SupervisorAgent",
    # Tools
    "InternalExample",
    "build_id2label",
    "build_label2id",
    "examples_to_dataframe",
    "load_csv_dataset",
    "load_csv_examples",
    "load_datasets",
    "load_internal_json_dir",
    "load_nikluge_sa2022",
    "load_split_examples",
]

