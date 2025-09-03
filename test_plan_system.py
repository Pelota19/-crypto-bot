#!/usr/bin/env python3
"""
Test script to validate that the plan-driven system integrates correctly
without requiring network access or API credentials.
"""
import sys
import os
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))

def test_plan_loading():
    """Test that plan configuration loads correctly."""
    print("Testing plan loading...")
    
    from src.config.plan_loader import get_plan_loader
    loader = get_plan_loader()
    plan = loader.load_plan()
    
    assert plan.profile_name == "conservative_scalping"
    assert plan.mode == "live_testnet"
    assert plan.risk.position_size_pct == 0.5
    assert plan.risk.leverage == 5
    
    print(f"✅ Plan loaded: {plan.profile_name} ({plan.mode})")
    return True

def test_guardrails():
    """Test risk guardrails functionality."""
    print("Testing risk guardrails...")
    
    from src.risk.guardrails import get_guardrails, TradeContext
    from src.config.plan_loader import get_plan_loader
    
    loader = get_plan_loader()
    guardrails = get_guardrails(loader)
    
    # Test valid trade
    valid_context = TradeContext(
        symbol='BTC/USDT',
        side='buy',
        entry_price=50000.0,
        position_size_usd=10.0,  # 0.5% of 2000 USD
        equity_usd=2000.0,
        current_positions=0,
        daily_pnl=0.0
    )
    
    result = guardrails.should_open_trade(valid_context)
    assert result['allowed'] == True
    
    # Test oversized trade
    oversized_context = TradeContext(
        symbol='BTC/USDT',
        side='buy',
        entry_price=50000.0,
        position_size_usd=100.0,  # 5% - too large
        equity_usd=2000.0,
        current_positions=0,
        daily_pnl=0.0
    )
    
    result = guardrails.should_open_trade(oversized_context)
    assert result['allowed'] == False
    assert 'risk per trade' in result['reason']
    
    print("✅ Risk guardrails working correctly")
    return True

def test_universe_selector():
    """Test universe selection functionality.""" 
    print("Testing universe selector...")
    
    from src.universe.selector import get_universe_selector
    from src.config.plan_loader import get_plan_loader
    
    loader = get_plan_loader()
    selector = get_universe_selector(loader)
    
    # Test static mode fallback (since we don't have exchange client)
    plan = loader.get_plan()
    assert plan.universe.mode == "dynamic"
    assert len(plan.universe.static_symbols) > 0
    
    print("✅ Universe selector initialized")
    return True

def test_mode_fallback():
    """Test mode fallback logic."""
    print("Testing mode fallback...")
    
    from src.config.plan_loader import get_plan_loader
    
    loader = get_plan_loader()
    
    # Test fallback with missing credentials
    should_fallback = loader.should_fallback_to_paper("", "")
    assert should_fallback == True
    
    # Test no fallback with credentials
    should_fallback = loader.should_fallback_to_paper("fake_key", "fake_secret")
    assert should_fallback == False
    
    print("✅ Mode fallback logic working")
    return True

def test_cli_script():
    """Test CLI script functionality."""
    print("Testing CLI script...")
    
    import subprocess
    result = subprocess.run([
        sys.executable, "scripts/apply_profile.py", "--dry-run"
    ], capture_output=True, text=True, cwd=repo_root)
    
    assert result.returncode == 0
    assert "Changes to apply" in result.stdout
    assert "MODE:" in result.stdout
    
    print("✅ CLI script working")
    return True

def test_backward_compatibility():
    """Test that system works without plan.yml."""
    print("Testing backward compatibility...")
    
    import shutil
    plan_path = repo_root / "config" / "plan.yml"
    backup_path = repo_root / "config" / "plan.yml.test_backup"
    
    # Backup plan
    shutil.move(str(plan_path), str(backup_path))
    
    try:
        from src.config.plan_loader import PlanLoader
        loader = PlanLoader()
        plan = loader.load_plan()  # Should use defaults
        
        assert plan.profile_name == "conservative_scalping"
        print("✅ Backward compatibility working")
        
    finally:
        # Restore plan
        shutil.move(str(backup_path), str(plan_path))
    
    return True

def main():
    """Run all validation tests."""
    print("🧪 Running plan-driven system validation tests...\n")
    
    tests = [
        test_plan_loading,
        test_guardrails,
        test_universe_selector, 
        test_mode_fallback,
        test_cli_script,
        test_backward_compatibility
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed: {e}")
            failed += 1
        print()
    
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All plan-driven system tests passed!")
        print("\nNext steps:")
        print("1. Add API credentials to .env if testing live mode")
        print("2. Run: python scripts/apply_profile.py --write")
        print("3. Run: python validate_config.py")
        print("4. Run: python -m src.main")
        return 0
    else:
        print("❌ Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())