from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

Direction = Literal["LONG", "FLAT"]

@dataclass
class AgentSignal:
    agent: str
    symbol: str
    timestamp: datetime
    score: float
    direction: Direction
    confidence: float
    reason: str
    metadata: dict = field(default_factory=dict)

@dataclass
class DeskDecision:
    symbol: str
    timestamp: datetime
    direction: Direction
    score: float
    confidence: float
    stop_price: float | None
    rationale: list[str]
    vetoed: bool = False
    veto_reason: str | None = None

@dataclass
class RiskDecision:
    approved: bool
    quantity: float = 0.0
    notional: float = 0.0
    risk_dollars: float = 0.0
    reason: str = ""
