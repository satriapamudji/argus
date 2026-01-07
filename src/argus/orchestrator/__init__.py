"""Run orchestrator module for Argus.

Provides end-to-end run execution for us_close, weekend_wrap, and monday_preview modes.
"""

from argus.orchestrator.holiday import (
    check_holiday_status,
    get_next_trading_date_for_run,
    should_run_monday_preview,
)
from argus.orchestrator.orchestrator import (
    OrchestratorOptions,
    RunOrchestrator,
    run_orchestrator,
)
from argus.orchestrator.risk_score import (
    calculate_calendar_score,
    calculate_headline_score,
    calculate_market_score,
    calculate_risk_score,
)
from argus.orchestrator.types import (
    HalfDayBehavior,
    HolidayBehavior,
    HolidayInfo,
    RiskScoreBreakdown,
    RunMode,
    RunResult,
    RunStatus,
    RunTimings,
    WindowConfig,
)
from argus.orchestrator.window import (
    get_trading_date_for_run,
    get_window_for_mode,
)

__all__ = [
    # Types
    "HalfDayBehavior",
    "HolidayBehavior",
    "HolidayInfo",
    "RiskScoreBreakdown",
    "RunMode",
    "RunResult",
    "RunStatus",
    "RunTimings",
    "WindowConfig",
    # Window functions
    "get_trading_date_for_run",
    "get_window_for_mode",
    # Risk score functions
    "calculate_calendar_score",
    "calculate_headline_score",
    "calculate_market_score",
    "calculate_risk_score",
    # Holiday functions
    "check_holiday_status",
    "get_next_trading_date_for_run",
    "should_run_monday_preview",
    # Orchestrator
    "OrchestratorOptions",
    "RunOrchestrator",
    "run_orchestrator",
]
