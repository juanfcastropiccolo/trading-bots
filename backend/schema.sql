-- Supabase PostgreSQL schema for Crypto Trading Mission Control
-- Execute in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS agent_configs (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT 'BTC/USDT',
    strategy TEXT NOT NULL DEFAULT 'trend_following',
    budget_usd DOUBLE PRECISION NOT NULL DEFAULT 100.0,
    max_trade_usd DOUBLE PRECISION NOT NULL DEFAULT 10.0,
    mode TEXT NOT NULL DEFAULT 'paper',
    is_active BOOLEAN DEFAULT TRUE,
    max_position_pct DOUBLE PRECISION DEFAULT 0.50,
    drawdown_limit_pct DOUBLE PRECISION DEFAULT 0.20,
    daily_loss_limit_pct DOUBLE PRECISION DEFAULT 0.05,
    cooldown_minutes INTEGER DEFAULT 2,
    max_consecutive_losses INTEGER DEFAULT 3,
    rsi_buy_max DOUBLE PRECISION DEFAULT 70.0,
    rsi_sell_min DOUBLE PRECISION DEFAULT 30.0,
    is_protected BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_snapshots (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS features (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    ema_fast DOUBLE PRECISION,
    ema_slow DOUBLE PRECISION,
    rsi DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    close DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    direction TEXT NOT NULL,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS llm_decisions (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    signal_id INTEGER REFERENCES signals(id),
    model_used TEXT,
    tokens_used INTEGER DEFAULT 0,
    cost_usd DOUBLE PRECISION DEFAULT 0.0,
    reasoning TEXT,
    recommendation TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_checks (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    signal_id INTEGER REFERENCES signals(id),
    approved BOOLEAN NOT NULL,
    max_trade_ok BOOLEAN DEFAULT TRUE,
    max_position_ok BOOLEAN DEFAULT TRUE,
    drawdown_ok BOOLEAN DEFAULT TRUE,
    daily_loss_ok BOOLEAN DEFAULT TRUE,
    cooldown_ok BOOLEAN DEFAULT TRUE,
    consecutive_loss_ok BOOLEAN DEFAULT TRUE,
    data_complete_ok BOOLEAN DEFAULT TRUE,
    rejection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    signal_id INTEGER REFERENCES signals(id),
    side TEXT NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    fee DOUBLE PRECISION DEFAULT 0.0,
    slippage DOUBLE PRECISION DEFAULT 0.0,
    total_cost DOUBLE PRECISION NOT NULL,
    status TEXT DEFAULT 'filled',
    mode TEXT DEFAULT 'paper',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    side TEXT NOT NULL,
    entry_price DOUBLE PRECISION DEFAULT 0.0,
    quantity DOUBLE PRECISION DEFAULT 0.0,
    unrealized_pnl DOUBLE PRECISION DEFAULT 0.0,
    realized_pnl DOUBLE PRECISION DEFAULT 0.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER NOT NULL REFERENCES agent_configs(id),
    cash DOUBLE PRECISION NOT NULL,
    equity DOUBLE PRECISION NOT NULL,
    total_pnl DOUBLE PRECISION DEFAULT 0.0,
    total_pnl_pct DOUBLE PRECISION DEFAULT 0.0,
    win_count INTEGER DEFAULT 0,
    loss_count INTEGER DEFAULT 0,
    total_trades INTEGER DEFAULT 0,
    max_drawdown DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
