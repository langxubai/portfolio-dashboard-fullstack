with open('README.md', 'r', encoding='utf-8') as f:
    lines = f.readlines()

replacement = """### 第二步（本地）：启动 Streamlit 前端看板

1. 进入前端目录：`cd frontend`
2. 确保您已经在根目录下设置了 `.env` 并配置好 Supabase 的关联信息。
3. 启动应用：
   ```bash
   uv run streamlit run app.py
   ```
4. 浏览器将自动打开并运行在 `http://localhost:8501`。

---

## 8. 近期更新与修复日志 (Changelog)

- **自定义资产处理**: 新增了 `Custom` 这一强交互类型，且在底层增设了一套专属于历史账面的更新界面（包含日期回溯选择控件与价格提交表单）。且规避了自定义资产手动更新时无意义的警报推送。(✅ 已完成)
- **交易时区选择**: 保证交易时间不产生混乱。新增下拉框用于确保正确处理 ISO 格式化。并在后端配合 `zoneinfo` 模块解决。数据库原生依靠 `TIMESTAMP WITH TIME ZONE` 类型安全承接。(✅ 已完成)
- **高危操作二次确认**: 删除账户/资产/交易之前需要弹窗再点确认，并统计显示相关级联数据（如剩余持仓量/相关单号）。(✅ 已完成)
- **自动推导总金额**: 交易支持输入总金额，允许单价/数量/总金额三选二辅助推导，解决了以总金额为核算标准时的痛点。后台通过精算拆解保证不破坏精确量价记录表结构。(✅ 已完成)
- **前端看板升级**: 加入带涨跌标记的昨日收益；调整已实现/未实现收益的解耦逻辑；新增多种颗粒度的资产互动走势表。(✅ 已完成)
- **扩容至 8 位小数字段精细存取**: 后端 Pydantic 全面支持 8 位小数（顺应加密货币精细记录要求），解除前端高精度数据的提交拦截问题。(✅ 已完成)
- **彻底清除细小浮点误差**: 针对接近清仓操作引发的问题，引入了绝对值 < `1e-8` 级残币抹平与沉淀清空兜底，配合前端 `Decimal.normalize()`，解决界面经常被暴露科学计数法零头的情况。(✅ 已完成)
- **精细化时间输入**: 替换 Streamlit 原生 15 分内定时间组件为任意精准可填的文本校验框，强化体验。(✅ 已完成)
- **基准货币与外汇换算**: 大盘支持选择全局 Base Currency，并在合并估值时由 `yfinance` 自动抓取并融合雅虎外盘汇率 (`XXXCNY=X` 等)，同时原生开放 `Forex` 资产种类类型。(✅ 已完成)
- **解决前端静默掉线/卡死**: 使用自带连接池的持久化 `httpx.Client` ，开启多维度长短时长探测并且植入二次网络抖动自动试错连接，彻底终结 Streamlit 因用户搁置界面过久从而偶发 500 假死需反复刷新的隐患。(✅ 已完成)
- **合并 Custom 资产定价优化**: 修正不同账户等重名资产更新后价格会混串渲染污染的 BUG，未及时刷新会保留最新沉淀价格计入加权。(✅ 已完成)
- **支持接入中国公募场外基金**: 利用 `akshare` 增加 `FundCN` 支持自动拉取其对应 6 位数代码历史曲线和单位净额走势，同样支持多空 PnL 核算。(✅ 已完成)
- **收益率曲线崩溃修复 (TWR & Timezone 修正)**: (✅ 本次修复完毕) 
    - a. 原计算公式会导致平空后收益率计算出现畸变（剧烈掉落 -100%），已改为正确的 TWR（Time-Weighted Return 时间加权收益率算法），即使中途抽资也能稳健地展长期的实际盈亏复利斜率。
    - b. 之前收益率曲线因合并多源的 DatetimeIndex 时受到 tz-naive 与 tz-aware 不一致的影响而中断报错：`"Failed to calculate portfolio history: Cannot join tz-naive with tz-aware DatetimeIndex"`。已查证并修复 Custom 资产由于自带 `tz` 引发的报错，在提取合并之前主动去除了所有的时区以保证无缝显示合成曲线图。

---

### 目前可以进行的计划
"""

# The start line is the line with ### 第二步（本地）：启动 Streamlit 前端看板
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "### 第二步（本地）：启动 Streamlit 前端看板" in line:
        start_idx = i
    if "1. 收益率曲线图现在无法显示" in line:
        end_idx = i

if start_idx != -1 and end_idx != -1:
    new_lines = lines[:start_idx] + [replacement] + lines[end_idx+1:]
    with open('README.md', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Successfully replaced content.")
else:
    print(f"Could not find start_idx ({start_idx}) or end_idx ({end_idx})")
