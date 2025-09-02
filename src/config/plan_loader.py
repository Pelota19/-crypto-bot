"""
Plan loader for YAML-based configuration management.
Loads, validates, and provides runtime access to plan settings.
"""
from __future__ import annotations
import os
import logging
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

@dataclass
class DynamicSelectorConfig:
    enabled: bool = True
    refresh_interval_min: int = 30
    min_quote_volume_24h_usdt: float = 300000000
    max_spread_bps: float = 2.0
    min_depth_usdt_within_5bps: float = 50000
    min_rvol_1m_bps: float = 10.0
    max_symbols: int = 10
    correlation_window_min: int = 720
    max_avg_corr: float = 0.75

@dataclass
class UniverseConfig:
    mode: str = "dynamic"  # dynamic | static
    static_symbols: List[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT", "BNB/USDT"])
    exclude_symbols: List[str] = field(default_factory=list)
    timeframe: str = "5m"
    dynamic_selector: DynamicSelectorConfig = field(default_factory=DynamicSelectorConfig)

@dataclass
class RiskConfig:
    position_size_pct: float = 0.5
    max_risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 2.0
    max_concurrent_positions: int = 3
    leverage: int = 5
    margin_mode: str = "ISOLATED"
    respect_exchange_filters: bool = True

@dataclass
class SlTpConfig:
    sl_pct: float = 0.20
    tp_pct: float = 0.40
    trailing_sl_enabled: bool = False
    trailing_sl_trail_pct: float = 0.15

@dataclass
class ExecutionConfig:
    working_type: str = "CONTRACT_PRICE"
    reduce_only_brackets: bool = True
    time_in_force: str = "GTC"

@dataclass
class AlertsConfig:
    telegram_enabled: bool = True
    notify_on: List[str] = field(default_factory=lambda: ["entry", "exit", "sl_tp_set", "error"])

@dataclass
class TradingPlan:
    profile_name: str = "conservative_scalping"
    mode: str = "live_testnet"  # paper | live_testnet | live_mainnet
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    sl_tp: SlTpConfig = field(default_factory=SlTpConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)

class PlanLoader:
    def __init__(self, plan_path: str = "config/plan.yml"):
        self.plan_path = plan_path
        self._plan: Optional[TradingPlan] = None
        self._active_symbols: Optional[List[str]] = None
        self._last_symbol_refresh: Optional[float] = None

    def load_plan(self) -> TradingPlan:
        """Load and validate the trading plan from YAML file."""
        if not os.path.exists(self.plan_path):
            log.warning(f"Plan file {self.plan_path} not found, using defaults")
            self._plan = TradingPlan()
            return self._plan

        try:
            with open(self.plan_path, 'r') as f:
                data = yaml.safe_load(f)
            
            if not data:
                log.warning(f"Empty plan file {self.plan_path}, using defaults")
                self._plan = TradingPlan()
                return self._plan

            self._plan = self._parse_plan(data)
            self._validate_plan(self._plan)
            log.info(f"Loaded plan '{self._plan.profile_name}' in mode '{self._plan.mode}'")
            return self._plan
            
        except Exception as e:
            log.error(f"Failed to load plan from {self.plan_path}: {e}")
            log.warning("Falling back to default plan")
            self._plan = TradingPlan()
            return self._plan

    def _parse_plan(self, data: Dict[str, Any]) -> TradingPlan:
        """Parse YAML data into TradingPlan objects."""
        # Parse universe config
        universe_data = data.get("universe", {})
        dynamic_data = universe_data.get("dynamic_selector", {})
        correlation_data = dynamic_data.get("correlation", {})
        
        dynamic_selector = DynamicSelectorConfig(
            enabled=dynamic_data.get("enabled", True),
            refresh_interval_min=dynamic_data.get("refresh_interval_min", 30),
            min_quote_volume_24h_usdt=dynamic_data.get("min_quote_volume_24h_usdt", 300000000),
            max_spread_bps=dynamic_data.get("max_spread_bps", 2.0),
            min_depth_usdt_within_5bps=dynamic_data.get("min_depth_usdt_within_5bps", 50000),
            min_rvol_1m_bps=dynamic_data.get("min_rvol_1m_bps", 10.0),
            max_symbols=dynamic_data.get("max_symbols", 10),
            correlation_window_min=correlation_data.get("window_min", 720),
            max_avg_corr=correlation_data.get("max_avg_corr", 0.75)
        )
        
        universe = UniverseConfig(
            mode=universe_data.get("mode", "dynamic"),
            static_symbols=universe_data.get("static_symbols", ["BTC/USDT", "ETH/USDT", "BNB/USDT"]),
            exclude_symbols=universe_data.get("exclude_symbols", []),
            timeframe=universe_data.get("timeframe", "5m"),
            dynamic_selector=dynamic_selector
        )

        # Parse risk config
        risk_data = data.get("risk", {})
        risk = RiskConfig(
            position_size_pct=risk_data.get("position_size_pct", 0.5),
            max_risk_per_trade_pct=risk_data.get("max_risk_per_trade_pct", 0.5),
            max_daily_loss_pct=risk_data.get("max_daily_loss_pct", 2.0),
            max_concurrent_positions=risk_data.get("max_concurrent_positions", 3),
            leverage=risk_data.get("leverage", 5),
            margin_mode=risk_data.get("margin_mode", "ISOLATED"),
            respect_exchange_filters=risk_data.get("respect_exchange_filters", True)
        )

        # Parse SL/TP config
        sl_tp_data = data.get("sl_tp", {})
        trailing_data = sl_tp_data.get("trailing_sl", {})
        sl_tp = SlTpConfig(
            sl_pct=sl_tp_data.get("sl_pct", 0.20),
            tp_pct=sl_tp_data.get("tp_pct", 0.40),
            trailing_sl_enabled=trailing_data.get("enabled", False),
            trailing_sl_trail_pct=trailing_data.get("trail_pct", 0.15)
        )

        # Parse execution config
        execution_data = data.get("execution", {})
        execution = ExecutionConfig(
            working_type=execution_data.get("working_type", "CONTRACT_PRICE"),
            reduce_only_brackets=execution_data.get("reduce_only_brackets", True),
            time_in_force=execution_data.get("time_in_force", "GTC")
        )

        # Parse alerts config
        alerts_data = data.get("alerts", {})
        alerts = AlertsConfig(
            telegram_enabled=alerts_data.get("telegram_enabled", True),
            notify_on=alerts_data.get("notify_on", ["entry", "exit", "sl_tp_set", "error"])
        )

        return TradingPlan(
            profile_name=data.get("profile_name", "conservative_scalping"),
            mode=data.get("mode", "live_testnet"),
            universe=universe,
            risk=risk,
            sl_tp=sl_tp,
            execution=execution,
            alerts=alerts
        )

    def _validate_plan(self, plan: TradingPlan) -> None:
        """Validate plan configuration values."""
        # Validate mode
        valid_modes = ["paper", "live_testnet", "live_mainnet"]
        if plan.mode not in valid_modes:
            raise ValueError(f"Invalid mode '{plan.mode}', must be one of: {valid_modes}")

        # Validate universe mode
        valid_universe_modes = ["dynamic", "static"]
        if plan.universe.mode not in valid_universe_modes:
            raise ValueError(f"Invalid universe mode '{plan.universe.mode}', must be one of: {valid_universe_modes}")

        # Validate risk parameters
        if not (1 <= plan.risk.leverage <= 125):
            raise ValueError(f"Leverage must be between 1 and 125, got {plan.risk.leverage}")
        
        if not (0 <= plan.risk.position_size_pct <= 100):
            raise ValueError(f"Position size percentage must be between 0 and 100, got {plan.risk.position_size_pct}")
        
        if not (0 <= plan.risk.max_risk_per_trade_pct <= 100):
            raise ValueError(f"Max risk per trade percentage must be between 0 and 100, got {plan.risk.max_risk_per_trade_pct}")
        
        if not (0 <= plan.risk.max_daily_loss_pct <= 100):
            raise ValueError(f"Max daily loss percentage must be between 0 and 100, got {plan.risk.max_daily_loss_pct}")

        # Validate margin mode
        valid_margin_modes = ["ISOLATED", "CROSSED"]
        if plan.risk.margin_mode not in valid_margin_modes:
            raise ValueError(f"Invalid margin mode '{plan.risk.margin_mode}', must be one of: {valid_margin_modes}")

        # Validate SL/TP percentages
        if not (0 <= plan.sl_tp.sl_pct <= 100):
            raise ValueError(f"Stop loss percentage must be between 0 and 100, got {plan.sl_tp.sl_pct}")
        
        if not (0 <= plan.sl_tp.tp_pct <= 100):
            raise ValueError(f"Take profit percentage must be between 0 and 100, got {plan.sl_tp.tp_pct}")

        # Validate working type
        valid_working_types = ["MARK_PRICE", "CONTRACT_PRICE"]
        if plan.execution.working_type not in valid_working_types:
            raise ValueError(f"Invalid working type '{plan.execution.working_type}', must be one of: {valid_working_types}")

        # Validate time in force
        valid_tif = ["GTC", "IOC", "FOK"]
        if plan.execution.time_in_force not in valid_tif:
            raise ValueError(f"Invalid time in force '{plan.execution.time_in_force}', must be one of: {valid_tif}")

    def get_plan(self) -> TradingPlan:
        """Get the loaded plan, loading it if necessary."""
        if self._plan is None:
            self.load_plan()
        return self._plan

    def get_active_symbols(self, exchange_client=None) -> List[str]:
        """Get active symbols based on plan configuration."""
        plan = self.get_plan()
        
        if plan.universe.mode == "static":
            # Return static symbols excluding any excluded ones
            symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.debug(f"Using static universe: {symbols}")
            return symbols
        
        elif plan.universe.mode == "dynamic":
            # For now, return static symbols as fallback
            # Dynamic selection will be implemented in src/universe/selector.py
            symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.debug(f"Dynamic universe not yet implemented, using static fallback: {symbols}")
            return symbols
        
        else:
            # Fallback to static symbols
            symbols = [s for s in plan.universe.static_symbols if s not in plan.universe.exclude_symbols]
            log.warning(f"Unknown universe mode '{plan.universe.mode}', using static fallback: {symbols}")
            return symbols

    def get_sl_pct(self) -> float:
        """Get stop loss percentage from plan."""
        return self.get_plan().sl_tp.sl_pct / 100.0

    def get_tp_pct(self) -> float:
        """Get take profit percentage from plan."""
        return self.get_plan().sl_tp.tp_pct / 100.0

    def get_working_type(self) -> str:
        """Get working type for orders from plan."""
        return self.get_plan().execution.working_type

    def get_time_in_force(self) -> str:
        """Get time in force for orders from plan."""
        return self.get_plan().execution.time_in_force

    def get_position_size_pct(self) -> float:
        """Get position size percentage from plan."""
        return self.get_plan().risk.position_size_pct / 100.0

    def get_leverage(self) -> int:
        """Get leverage from plan."""
        return self.get_plan().risk.leverage

    def get_margin_mode(self) -> str:
        """Get margin mode from plan.""" 
        return self.get_plan().risk.margin_mode

    def should_fallback_to_paper(self, api_key: str, api_secret: str) -> bool:
        """Check if should fallback to paper mode due to missing secrets."""
        plan = self.get_plan()
        if plan.mode == "paper":
            return False  # Already paper mode
        
        # If plan requests live mode but secrets are missing
        if plan.mode in ["live_testnet", "live_mainnet"] and (not api_key or not api_secret):
            log.warning(f"Plan mode is '{plan.mode}' but API credentials are missing. Falling back to paper mode.")
            return True
        
        return False


# Global instance for easy access
_plan_loader: Optional[PlanLoader] = None

def get_plan_loader() -> PlanLoader:
    """Get global plan loader instance."""
    global _plan_loader
    if _plan_loader is None:
        _plan_loader = PlanLoader()
    return _plan_loader