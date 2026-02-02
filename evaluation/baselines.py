from __future__ import annotations

from typing import Dict, Optional

from agents import SupervisorAgent, BaselineRunner
from tools.backbone_client import BackboneClient


def resolve_run_mode(cli_mode: Optional[str], env_mode: Optional[str], cfg_mode: Optional[str]) -> str:
    """
    Determine run_mode with precedence: CLI > env(RUN_MODE) > config run_mode > default 'proposed'.
    """
    return (cli_mode or env_mode or cfg_mode or "proposed").lower()


def make_runner(
    *,
    run_mode: str,
    backbone: Optional[BackboneClient],
    config: Optional[Dict],
    run_id: str,
):
    """
    Factory that returns a runner producing FinalOutputSchema for any mode.
    - proposed -> SupervisorAgent
    - bl1/bl2/bl3 -> BaselineRunner
    """
    if run_mode == "proposed":
        return SupervisorAgent(backbone=backbone, config=config or {}, run_id=run_id)
    if run_mode in {"bl1", "bl2", "bl3"}:
        return BaselineRunner(mode=run_mode, backbone=backbone, config=config or {}, run_id=run_id)
    raise ValueError(f"Unsupported run_mode '{run_mode}'")
