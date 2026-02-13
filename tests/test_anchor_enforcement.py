from agents.supervisor_agent import SupervisorAgent
from schemas import (
    AspectExtractionItem,
    AspectTerm,
    AspectExtractionStage1Schema,
    AspectExtractionStage2Schema,
    AspectSentimentItem,
    AspectSentimentStage1Schema,
    AspectSentimentStage2Schema,
    SentimentReviewItem,
    Span,
)


def _stage1_struct(ate_term: str, atsa_term: str) -> tuple[AspectExtractionStage1Schema, AspectSentimentStage1Schema]:
    ate = AspectExtractionStage1Schema(aspects=[AspectExtractionItem(term=ate_term, span=Span(start=0, end=len(ate_term)))])
    atsa = AspectSentimentStage1Schema(
        aspect_sentiments=[
            AspectSentimentItem(
                aspect_term=AspectTerm(term=atsa_term, span=Span(start=0, end=len(atsa_term))),
                polarity="positive",
                confidence=0.5,
                evidence="dummy",
                polarity_distribution={"positive": 0.5},
            )
        ]
    )
    return ate, atsa


def test_stage1_anchor_issue_not_altering_output():
    agent = SupervisorAgent()
    ate, atsa = _stage1_struct("미국", "미국 방문")
    issues = agent._find_unanchored_aspects(ate, atsa)
    assert issues == ["stage1_aspect_term_not_in_ate:미국 방문"]
    assert atsa.aspect_sentiments[0].aspect_term and atsa.aspect_sentiments[0].aspect_term.term == "미국 방문"


def test_stage2_mapping_to_ate_term():
    agent = SupervisorAgent()
    ate, atsa = _stage1_struct("미국", "미국 방문")
    ate_review = AspectExtractionStage2Schema()
    atsa_review = AspectSentimentStage2Schema(sentiment_review=[SentimentReviewItem(aspect_term="미국 방문", action="maintain")])

    patched_ate, patched_atsa, issues, _ = agent._apply_stage2_reviews(ate, atsa, ate_review, atsa_review)

    assert patched_ate.aspects[0].term == "미국"
    assert patched_atsa.aspect_sentiments[0].aspect_term and patched_atsa.aspect_sentiments[0].aspect_term.term == "미국"
    assert any("mapped_aspect_term:미국 방문->미국" in s for s in issues)


def test_stage2_drop_unmatched_aspect_term():
    agent = SupervisorAgent()
    ate, atsa = _stage1_struct("미국", "파리")
    ate_review = AspectExtractionStage2Schema()
    atsa_review = AspectSentimentStage2Schema(sentiment_review=[SentimentReviewItem(aspect_term="파리", action="maintain")])

    _, patched_atsa, issues, _ = agent._apply_stage2_reviews(ate, atsa, ate_review, atsa_review)

    assert patched_atsa.aspect_sentiments == []
    assert any("dropped_unanchored_aspect_term:파리" in s for s in issues)
