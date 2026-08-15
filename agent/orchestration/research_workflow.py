"""
Research Workflow Orchestrator
==============================
Sequences the 10-step business research workflow for a given ticker.
Loads appropriate prompt templates and financial context for each step.
Returns a structured workflow plan that Claude executes step by step.

This module does NOT:
- Execute research itself (Claude does that)
- Make investment decisions
- Access network or external data

It DOES:
- Define the step sequence and dependencies
- Load prompt templates with financial context injected
- Track which steps are complete vs. pending
- Validate prerequisites before each step proceeds
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class WorkflowStep:
    step_number: int
    name: str
    description: str
    prompt_template: Optional[str]   # filename in agent/prompts/
    prerequisites: List[int]          # step numbers that must be complete first
    dimension_key: str                # key in BusinessResearchAssessment
    is_mandatory: bool = True
    status: StepStatus = StepStatus.PENDING
    skip_reason: str = ""
    completed_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "step_number": self.step_number,
            "name": self.name,
            "description": self.description,
            "prompt_template": self.prompt_template,
            "prerequisites": self.prerequisites,
            "dimension_key": self.dimension_key,
            "is_mandatory": self.is_mandatory,
            "status": self.status.value,
            "skip_reason": self.skip_reason,
            "completed_at": self.completed_at,
            "notes": self.notes,
        }


def _load_prompt(filename: str, context: Dict[str, Any]) -> str:
    """Load a prompt template and inject context variables."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        return f"[Prompt template not found: {filename}]"
    text = path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace(f"{{{key}}}", str(value) if value is not None else "N/A")
    return text


def build_workflow_steps() -> List[WorkflowStep]:
    """
    Define the 10-step research workflow in order.
    Steps are ordered to respect dependencies (e.g., moat requires business understanding first).
    """
    return [
        WorkflowStep(
            step_number=1,
            name="ETF / Instrument Check",
            description="Determine if this is an ETF, fund, or instrument that should be excluded from fundamental analysis.",
            prompt_template=None,
            prerequisites=[],
            dimension_key="etf_check",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=2,
            name="Business Understanding",
            description="What does this business do, how does it make money, and is it within the circle of competence?",
            prompt_template="business_understanding.md",
            prerequisites=[1],
            dimension_key="business_understanding",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=3,
            name="Industry Analysis",
            description="Is the industry structurally attractive, neutral, or challenging?",
            prompt_template="industry_analysis.md",
            prerequisites=[2],
            dimension_key="industry_assessment",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=4,
            name="Financial Quality Review",
            description="Review the Python-generated financial quality assessment — understand what the numbers say.",
            prompt_template=None,
            prerequisites=[2],
            dimension_key="financial_quality_summary",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=5,
            name="Moat Analysis",
            description="Does this company have a durable competitive advantage? What kind, how strong, how durable?",
            prompt_template="moat_analysis.md",
            prerequisites=[2, 3, 4],
            dimension_key="moat_assessment",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=6,
            name="Growth Assessment",
            description="What is the quality and sustainability of the company's growth?",
            prompt_template="growth_assessment.md",
            prerequisites=[4, 5],
            dimension_key="growth_assessment",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=7,
            name="Management Assessment",
            description="Evaluate capital allocation track record, integrity, and alignment.",
            prompt_template="management_assessment.md",
            prerequisites=[4],
            dimension_key="management_assessment",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=8,
            name="Risk Analysis",
            description="What are the key risks? Which are temporary vs. structural?",
            prompt_template="risk_analysis.md",
            prerequisites=[3, 5, 6, 7],
            dimension_key="risk_assessment",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=9,
            name="Bull / Bear Case & Devil's Advocate",
            description="Mandatory devil's advocate research. What is the bear case? What evidence challenges the thesis?",
            prompt_template="bull_bear_case.md",
            prerequisites=[5, 6, 7, 8],
            dimension_key="bull_bear",
            is_mandatory=True,
        ),
        WorkflowStep(
            step_number=10,
            name="Research Synthesis",
            description="Consolidate all dimensions into a BusinessResearchAssessment. Identify contradictions and gaps.",
            prompt_template=None,
            prerequisites=[2, 3, 4, 5, 6, 7, 8, 9],
            dimension_key="synthesis",
            is_mandatory=True,
        ),
    ]


@dataclass
class ResearchWorkflow:
    """
    Manages the state and progression of a business research workflow
    for a single ticker.
    """
    ticker: str
    company_name: str
    is_etf: bool = False
    steps: List[WorkflowStep] = field(default_factory=build_workflow_steps)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    financial_context: Dict[str, Any] = field(default_factory=dict)

    # -------------------------------------------------------------------
    # Step management
    # -------------------------------------------------------------------

    def get_step(self, step_number: int) -> Optional[WorkflowStep]:
        for s in self.steps:
            if s.step_number == step_number:
                return s
        return None

    def mark_complete(self, step_number: int, notes: str = "") -> None:
        step = self.get_step(step_number)
        if step:
            step.status = StepStatus.COMPLETE
            step.completed_at = datetime.now().isoformat()
            step.notes = notes

    def mark_skipped(self, step_number: int, reason: str) -> None:
        step = self.get_step(step_number)
        if step:
            step.status = StepStatus.SKIPPED
            step.skip_reason = reason

    def prerequisites_met(self, step_number: int) -> bool:
        step = self.get_step(step_number)
        if not step:
            return False
        for prereq_num in step.prerequisites:
            prereq = self.get_step(prereq_num)
            if prereq and prereq.status not in (StepStatus.COMPLETE, StepStatus.SKIPPED):
                return False
        return True

    def next_step(self) -> Optional[WorkflowStep]:
        """Return the next step that is pending and whose prerequisites are met."""
        for step in self.steps:
            if step.status == StepStatus.PENDING and self.prerequisites_met(step.step_number):
                return step
        return None

    def pending_steps(self) -> List[WorkflowStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    def complete_steps(self) -> List[WorkflowStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETE]

    def is_complete(self) -> bool:
        mandatory = [s for s in self.steps if s.is_mandatory]
        return all(s.status in (StepStatus.COMPLETE, StepStatus.SKIPPED) for s in mandatory)

    # -------------------------------------------------------------------
    # Prompt loading
    # -------------------------------------------------------------------

    def load_step_prompt(self, step_number: int) -> str:
        """Load and render the prompt template for a given step."""
        step = self.get_step(step_number)
        if not step or not step.prompt_template:
            return f"[No prompt template for step {step_number}]"
        ctx = {
            "ticker": self.ticker,
            "company_name": self.company_name,
            **self.financial_context,
        }
        return _load_prompt(step.prompt_template, ctx)

    # -------------------------------------------------------------------
    # ETF short-circuit
    # -------------------------------------------------------------------

    def apply_etf_short_circuit(self) -> None:
        """
        If the instrument is an ETF, skip all fundamental research steps.
        ETFs get step 1 (ETF check) marked complete and all others skipped.
        """
        if not self.is_etf:
            return
        self.mark_complete(1, "Confirmed ETF — skipping fundamental research")
        for step in self.steps:
            if step.step_number != 1:
                self.mark_skipped(step.step_number, "ETF — fundamental analysis not applicable")

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "is_etf": self.is_etf,
            "started_at": self.started_at,
            "is_complete": self.is_complete(),
            "steps_complete": len(self.complete_steps()),
            "steps_pending": len(self.pending_steps()),
            "financial_context": self.financial_context,
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    # -------------------------------------------------------------------
    # Status report
    # -------------------------------------------------------------------

    def status_report(self) -> str:
        lines = [
            f"Research Workflow: {self.company_name} ({self.ticker})",
            f"Started: {self.started_at}",
            f"Progress: {len(self.complete_steps())}/{len(self.steps)} steps complete",
            "",
        ]
        for step in self.steps:
            icon = {
                StepStatus.COMPLETE: "✓",
                StepStatus.PENDING: "○",
                StepStatus.IN_PROGRESS: "→",
                StepStatus.SKIPPED: "⊘",
                StepStatus.BLOCKED: "✗",
            }.get(step.status, "?")
            line = f"  {icon} Step {step.step_number}: {step.name} [{step.status.value}]"
            if step.skip_reason:
                line += f" — {step.skip_reason}"
            lines.append(line)

        next_s = self.next_step()
        if next_s:
            lines.append(f"\nNext: Step {next_s.step_number} — {next_s.name}")
        elif self.is_complete():
            lines.append("\nAll steps complete — ready for synthesis.")
        else:
            lines.append("\nNo next step available — check prerequisites.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_workflow(
    ticker: str,
    company_name: str,
    is_etf: bool = False,
    financial_context: Optional[Dict[str, Any]] = None,
) -> ResearchWorkflow:
    """
    Create a new ResearchWorkflow for a ticker.
    Apply ETF short-circuit immediately if applicable.
    """
    wf = ResearchWorkflow(
        ticker=ticker,
        company_name=company_name,
        is_etf=is_etf,
        financial_context=financial_context or {},
    )
    if is_etf:
        wf.apply_etf_short_circuit()
    return wf


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing research_workflow.py...")

    # Test 1: Normal stock workflow
    wf = create_workflow(
        ticker="FFH.TO",
        company_name="Fairfax Financial Holdings",
        financial_context={
            "sector": "Financial Services",
            "roic_current": "12.4",
            "roic_5yr_avg": "10.8",
            "revenue_cagr_5yr": "18.2",
            "revenue_cagr_10yr": "14.5",
            "eps_trend": "positive",
            "industry_name": "Property & Casualty Insurance",
            "moat_strength": "TBD",
            "preliminary_direction": "None",
            "ceo_name": "Prem Watsa",
            "ceo_tenure": "38",
            "roic_moat_note": "ROIC above 10% supports but does not prove a moat",
        },
    )

    print(wf.status_report())

    # Simulate completing steps 1-2
    wf.mark_complete(1, "Not an ETF")
    wf.mark_complete(2, "Business model well understood: P&C insurance + investment portfolio")
    print(f"\nNext step: {wf.next_step().name}")

    # Test prompt loading
    prompt = wf.load_step_prompt(5)
    print(f"\nMoat analysis prompt loaded ({len(prompt)} chars), "
          f"ticker injected: {'FFH.TO' in prompt}")

    # Test 2: ETF short-circuit
    etf_wf = create_workflow("CGL.C.TO", "iShares Gold Bullion ETF (CAD)", is_etf=True)
    print(f"\nETF workflow complete: {etf_wf.is_complete()}")
    skipped = [s.step_number for s in etf_wf.steps if s.status == StepStatus.SKIPPED]
    print(f"Skipped steps: {skipped}")

    # Test 3: Serialization
    d = wf.to_dict()
    assert d["ticker"] == "FFH.TO"
    assert d["steps_complete"] == 2
    print(f"\nSerialization: OK — {d['steps_complete']} steps complete")

    print("\nresearch_workflow.py: OK")
