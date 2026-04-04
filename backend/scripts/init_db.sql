-- 启用 uuid 扩展（通常 Supabase 默认启用，但为求稳妥可以开启）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. 资金账户表 (accounts)
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. 资产基础信息表 (assets)
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(50) NOT NULL, -- Stock, Fund, Crypto, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. 交易流水表 (transactions)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    trade_type VARCHAR(20) NOT NULL, -- BUY, SELL, DIVIDEND
    price DECIMAL(18, 4) NOT NULL,
    quantity DECIMAL(18, 4) NOT NULL,
    trade_time TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. 自定义报警规则表 (alert_rules)
CREATE TABLE IF NOT EXISTS alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    rule_type VARCHAR(50) NOT NULL, -- TARGET_PRICE, CHANGE_PERCENT, CHANGE_ABS
    direction VARCHAR(20) NOT NULL, -- UP, DOWN
    target_value DECIMAL(18, 4) NOT NULL,
    time_window_minutes INTEGER, -- 当 rule_type 为 CHANGE 时需要
    is_active BOOLEAN DEFAULT TRUE,
    cooldown_minutes INTEGER DEFAULT 1440,
    last_triggered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 为了方便查询，给频繁查询的外键添加索引
CREATE INDEX IF NOT EXISTS idx_transactions_account_id ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_asset_id ON transactions(asset_id);
CREATE INDEX IF NOT EXISTS idx_transactions_trade_time ON transactions(trade_time DESC);

CREATE INDEX IF NOT EXISTS idx_alert_rules_asset_id ON alert_rules(asset_id);
CREATE INDEX IF NOT EXISTS idx_alert_rules_is_active ON alert_rules(is_active) WHERE is_active = TRUE;

-- 5. 自定义资产历史价格表 (custom_asset_prices)
CREATE TABLE IF NOT EXISTS custom_asset_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
    price DECIMAL(18, 4) NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_asset_prices_asset_id ON custom_asset_prices(asset_id);
CREATE INDEX IF NOT EXISTS idx_custom_asset_prices_recorded_at ON custom_asset_prices(recorded_at DESC);
