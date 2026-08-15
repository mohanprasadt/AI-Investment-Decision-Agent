"""
Phase 8 — Investment Decision Agent
=====================================
Thin conversational/orchestration layer over the Phase 1–7.8 analytical pipeline.

Architecture:
  intent_parser.py   — parse user input → Intent
  investment_agent.py — orchestrate pipeline, hold session state
  renderer.py        — format InvestmentDecisionAssessment as human-readable text

This layer does NOT duplicate or override Phase 1–7.8 logic.
All L3 conclusions come from InvestmentDecisionAssessment produced by
make_investment_decision() in analytics.decision.decision_synthesizer.
"""

from analytics.agent.investment_agent import InvestmentAgent
from analytics.agent.intent_parser import parse_intent, Intent

__all__ = ["InvestmentAgent", "parse_intent", "Intent"]
