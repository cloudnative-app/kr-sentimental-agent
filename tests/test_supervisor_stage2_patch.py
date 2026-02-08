from agents.supervisor_agent import SupervisorAgent
from schemas import (
    AspectExtractionItem,
    AspectExtractionReviewItem,
    AspectExtractionStage1Schema,
    AspectExtractionStage2Schema,
    AspectSentimentItem,
    AspectSentimentStage1Schema,
    AspectSentimentStage2Schema,
    AspectTerm,
    SentimentReviewItem,
    Span,
)


def test_stage2_flip_polarity_applies_and_sets_confidence():
    agent = SupervisorAgent()

    stage1_ate = AspectExtractionStage1Schema(
        aspects=[AspectExtractionItem(term="서비스", span=Span(start=0, end=3), confidence=0.6, rationale="stage1")]
    )
    stage1_atsa = AspectSentimentStage1Schema(
        aspect_sentiments=[
            AspectSentimentItem(
                aspect_term=AspectTerm(term="서비스", span=Span(start=0, end=3)),
                polarity="positive",
                confidence=0.4,
                evidence="매우 좋지",
                polarity_distribution={"positive": 0.4},
            )
        ]
    )
    stage2_ate = AspectExtractionStage2Schema(
        aspect_review=[AspectExtractionReviewItem(term="서비스", action="keep")]
    )
    stage2_atsa = AspectSentimentStage2Schema(
        sentiment_review=[
            SentimentReviewItem(aspect_term="서비스", action="flip_polarity", revised_polarity="negative", reason="stage2 review")
        ]
    )

    patched_ate, patched_atsa, _, _ = agent._apply_stage2_reviews(stage1_ate, stage1_atsa, stage2_ate, stage2_atsa)
    agg_stage2 = agent._aggregate_label_from_sentiments(patched_atsa)

    assert patched_ate.aspects[0].term == "서비스"
    assert patched_atsa.aspect_sentiments[0].polarity == "negative"
    assert agg_stage2.label == "negative"
    assert agg_stage2.confidence > 0.0
    assert patched_atsa.aspect_sentiments[0].polarity_distribution.get("negative", 0) >= 0.9
