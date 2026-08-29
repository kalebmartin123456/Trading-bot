from trading_desk.paper_broker import canonical_crypto_symbol, normalize_quantity


def test_symbol_normalization():
    assert canonical_crypto_symbol("BTCUSD") == "BTC/USD"
    assert canonical_crypto_symbol("ETH/USD") == "ETH/USD"


def test_quantity_rounds_down_to_increment():
    assert normalize_quantity(1.234567, "0.001", "0.001") == 1.234


def test_quantity_rejects_below_minimum():
    assert normalize_quantity(0.0004, "0.0001", "0.001") == 0.0
