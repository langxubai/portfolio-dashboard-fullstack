def test_twr():
    # Day 1: buy 1000
    prev = 0
    inflow = 1000
    val = 1050
    pnl = val - prev - inflow
    base = prev + max(0, inflow)
    r1 = pnl / base
    print(f"Day 1: pnl={pnl}, base={base}, r1={r1}")
    
    # Day 2: sell 1100
    prev = 1050
    inflow = -1100
    val = 0
    pnl = val - prev - inflow
    base = prev + max(0, inflow)
    r2 = pnl / base
    print(f"Day 2: pnl={pnl}, base={base}, r2={r2}")
    
    # Total
    cum = (1+r1)*(1+r2) - 1
    print(f"Cum: {cum}")

test_twr()
