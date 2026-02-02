import inspect

from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator


def _first_param_is_text(func):
    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    assert params[1].name == "text", "first arg after self must be 'text'"
    anno = params[1].annotation
    assert anno in (str, "str"), "text must be annotated as str"


def test_ate_signature():
    _first_param_is_text(ATEAgent.run)


def test_atsa_signature():
    _first_param_is_text(ATSAAgent.run)


def test_validator_signature():
    sig = inspect.signature(ValidatorAgent.run)
    params = list(sig.parameters.values())
    assert params[1].name == "text"
    assert params[1].annotation in (str, "str")
    assert params[2].name == "ate"
    assert params[3].name == "atsa"


def test_moderator_signature():
    sig = inspect.signature(Moderator.decide)
    params = list(sig.parameters.values())
    assert params[1].name == "stage1_ate"
    assert params[2].name == "stage1_atsa"
