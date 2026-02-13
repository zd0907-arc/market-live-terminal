import pytest
from backend.app.services.monitor import SentimentMonitor, TencentSource

def test_tencent_source_constants():
    """Verify key indices match Tencent API spec."""
    assert TencentSource.PRICE == 3
    assert TencentSource.OUTER_VOL == 7
    assert TencentSource.INNER_VOL == 8
    assert TencentSource.TOTAL_VOL == 6

def test_iceberg_sell_detection():
    """Test detection of Iceberg Sell Orders (Hidden liquidity at Ask1)."""
    monitor = SentimentMonitor()
    
    # Scenario: 
    # Active Buy (Outer) increased by 1000
    # Ask1 only decreased by 100 (meaning 900 was hidden refill)
    # This implies someone is reloading the Ask1 queue instantly.
    
    prev = {
        'outer_vol': 1000,
        'ask1_vol': 5000,
        'inner_vol': 0, 
        'bid1_vol': 0, 
        'price': 10.0
    }
    
    curr = {
        'outer_vol': 2000, # Delta Active Buy = +1000
        'ask1_vol': 4900,  # Delta Ask1 = -100
        'inner_vol': 0, 
        'bid1_vol': 0, 
        'price': 10.0
    }
    
    # Logic Trace:
    # delta_active_buy = 1000
    # delta_ask1 = -100
    # hidden_refill = -100 + 1000 = 900
    # Threshold: refill (900) > active_buy (1000) * 0.8 (800) -> True
    
    result = monitor.check_iceberg_sell(prev, curr)
    assert result is not None
    assert result['type'] == 'ICEBERG'
    assert result['level'] == 'High'
    # Verify detail message formatting
    assert "外盘吃进1000手" in result['detail']

def test_no_iceberg_normal_trade():
    """Test that normal trading (Ask1 drops = Buy amount) triggers no signal."""
    monitor = SentimentMonitor()
    
    prev = {'outer_vol': 1000, 'ask1_vol': 5000}
    curr = {'outer_vol': 2000, 'ask1_vol': 4000} # Buy 1000, Ask drops 1000
    
    # hidden_refill = -1000 + 1000 = 0
    result = monitor.check_iceberg_sell(prev, curr)
    assert result is None

def test_spoof_buy_detection():
    """Test detection of Spoofing (Fake Buy Order Withdrawal)."""
    monitor = SentimentMonitor()
    
    # Scenario:
    # Little to no selling (Inner delta small)
    # Bid1 drops significantly (Cancel order)
    
    prev = {
        'inner_vol': 1000,
        'bid1_vol': 5000
    }
    
    curr = {
        'inner_vol': 1050, # Delta Sell = 50 (< 100 threshold)
        'bid1_vol': 3000   # Delta Bid1 = -2000 (< -1000 threshold)
    }
    
    result = monitor.check_spoof_buy(prev, curr)
    assert result is not None
    assert result['type'] == 'SPOOFING'
    assert "主力撤托" in result['signal']
