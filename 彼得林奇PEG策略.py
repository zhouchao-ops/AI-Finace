'''
彼得林奇PEG选股策略（V4 — PEG选股 + 回撤止盈）
适用平台：聚宽（JoinQuant）

核心逻辑：
  选股按PEG（低估时买入），持有期间不盯涨跌，PEG不变贵就一直拿着。
  但如果股价从最高点回落超过15%，说明趋势变了，止盈锁定利润。

卖出条件：
  1. PEG > 1.5  → 基本面变贵了，卖
  2. 股价从最高点回落 > 15% → 趋势变了，止盈卖

买入：PEG < 1.0  → 低估，买入
持有：监控PEG + 跟踪最高价
'''


def initialize(context):
    # ==================== 基本设置 ====================
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_option('order_volume_ratio', 1)

    # ==================== 手续费 & 滑点 ====================
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        close_today_commission=0,
        min_commission=5
    ), type='stock')
    set_slippage(PriceRelatedSlippage(0.002))

    # ==================== 策略参数 ====================
    g.stock_num = 15              # 持仓数量
    g.max_pe = 40                 # 最大PE
    g.min_growth = 10             # 最低增长率（%）
    g.buy_peg = 1.0               # PEG买入阈值
    g.sell_peg = 1.5              # PEG卖出阈值
    g.trailing_stop = 0.15        # 回撤止盈：从最高点回落15%就卖
    g.freeze_days = 3             # 卖出后冻结天数，禁止立即回购

    # 跟踪每只股票的历史最高价 { stock_code: peak_price }
    g.peak_prices = {}

    # 冻结列表 { stock_code: 解冻日期 }，卖出后短期禁止回购
    g.frozen_stocks = {}

    # ==================== 定时任务 ====================
    run_daily(daily_check, time='every_bar')


def filter_stocks(context, stock_list):
    '''过滤停牌 + ST + 冻结期内禁止回购'''
    current_data = get_current_data()
    result = []
    for stock in stock_list:
        if current_data[stock].paused or current_data[stock].is_st:
            continue
        if stock in g.frozen_stocks and context.current_dt < g.frozen_stocks[stock]:
            continue
        result.append(stock)
    return result


def select_stocks(context):
    '''选股：沪深300中筛选 PEG < buy_peg，按PEG排序取前N只'''
    hs300_stocks = get_index_stocks('000300.XSHG')

    q = query(
        valuation.code,
        valuation.pe_ratio,
        valuation.market_cap,
        indicator.inc_net_profit_year_on_year
    ).filter(
        valuation.code.in_(hs300_stocks),
        valuation.pe_ratio > 0,
        valuation.pe_ratio < g.max_pe,
        indicator.inc_net_profit_year_on_year > g.min_growth,
        valuation.pe_ratio / indicator.inc_net_profit_year_on_year < g.buy_peg
    ).order_by(
        valuation.pe_ratio / indicator.inc_net_profit_year_on_year
    ).limit(g.stock_num * 2)

    df = get_fundamentals(q)
    if df.empty:
        return []

    stock_list = filter_stocks(context, list(df['code']))
    return stock_list[:g.stock_num]


def initial_buy(context):
    '''首次启动：买入初始的15只股票'''
    target_stocks = select_stocks(context)
    if not target_stocks:
        return

    cash_per_stock = context.portfolio.total_value / len(target_stocks)
    for stock in target_stocks:
        order_value(stock, cash_per_stock)
        # 初始记录最高价 = 买入时的价格（用昨日收盘价作为参考）
        hist = attribute_history(stock, 1, '1d', ['close'], df=True)
        if hist is not None and not hist.empty:
            g.peak_prices[stock] = hist['close'].iloc[-1]

    # 打印买入明细
    q = query(
        valuation.code,
        valuation.pe_ratio,
        indicator.inc_net_profit_year_on_year
    ).filter(
        valuation.code.in_(target_stocks)
    )
    df = get_fundamentals(q)
    if not df.empty:
        df['peg'] = df['pe_ratio'] / df['inc_net_profit_year_on_year']
        log.info('=== 首次买入 ===')
        for _, row in df.iterrows():
            log.info(f'  {row["code"]}  PE={row["pe_ratio"]:.1f}  '
                     f'G={row["inc_net_profit_year_on_year"]:.1f}%  '
                     f'PEG={row["peg"]:.2f}')
        log.info(f'总资产：{context.portfolio.total_value:.2f}')


def daily_check(context):
    '''
    每日监控：
    1. 首次启动 → 初始买入
    2. 更新每只持仓的最高价
    3. 检查是否触发卖出条件（PEG变贵 / 回撤止盈）
    4. 如有卖出，补入新的低PEG股票
    '''
    # ---- 清理过期冻结记录 ----
    expired = [s for s in list(g.frozen_stocks.keys())
               if context.current_dt >= g.frozen_stocks[s]]
    for s in expired:
        del g.frozen_stocks[s]

    # ---- 首次启动 ----
    if len(context.portfolio.positions) == 0 and context.portfolio.available_cash > 0:
        initial_buy(context)
        return

    holdings = list(context.portfolio.positions.keys())
    if not holdings:
        return

    # 查询持仓股票当前PEG
    q = query(
        valuation.code,
        valuation.pe_ratio,
        valuation.market_cap,
        indicator.inc_net_profit_year_on_year
    ).filter(
        valuation.code.in_(holdings)
    )
    df = get_fundamentals(q)
    if df.empty:
        return

    df['peg'] = df['pe_ratio'] / df['inc_net_profit_year_on_year']
    current_data = get_current_data()

    # 找出需要卖出的股票
    stocks_to_sell = []

    for stock in holdings:
        row = df[df['code'] == stock]
        if row.empty:
            continue

        peg = row['peg'].values[0]
        reason = None

        # 条件1：PEG > 卖出阈值（基本面变贵）
        if peg > g.sell_peg:
            reason = f'PEG={peg:.2f} > {g.sell_peg}'

        else:
            # 没有触发PEG卖出的，才检查价格趋势
            # 获取当前价格
            hist = attribute_history(stock, 1, '1d', ['close'], df=True)
            if hist is not None and not hist.empty:
                current_price = hist['close'].iloc[-1]

                if current_data[stock].paused:
                    continue

                # 更新最高价（从未记录过的，取昨日收盘价作为起点）
                if stock not in g.peak_prices:
                    g.peak_prices[stock] = current_price
                    if current_price > g.peak_prices[stock]:
                        g.peak_prices[stock] = current_price

                # 条件2：回撤止盈（从最高点回落超过阈值）
                peak = g.peak_prices[stock]
                drawdown = (peak - current_price) / peak
                if drawdown > g.trailing_stop:
                    reason = (f'回撤止盈：最高{peak:.2f} → 现{current_price:.2f} '
                              f'回落{drawdown*100:.1f}%')

        if reason:
            stocks_to_sell.append((stock, reason))

    if not stocks_to_sell:
        return  # 一切正常，不动

    # ---- 卖出 ----
    for stock, reason in stocks_to_sell:
        order_target_value(stock, 0)
        # 卖出后加入冻结列表，短期禁止回购
        g.frozen_stocks[stock] = context.current_dt + datetime.timedelta(days=g.freeze_days)
        # 清除最高价记录
        g.peak_prices.pop(stock, None)
        log.info(f'【卖出】{stock}  原因：{reason}  （冻结{g.freeze_days}天）')

    # ---- 用卖出的钱买入替代股票 ----
    new_candidates = select_stocks(context)
    current_holdings = list(context.portfolio.positions.keys())
    to_buy = [s for s in new_candidates if s not in current_holdings]

    if not to_buy:
        return

    cash_per_stock = context.portfolio.available_cash / len(to_buy)
    for stock in to_buy:
        order_value(stock, cash_per_stock)
        # 记录新买入股票的最高价（用昨日收盘价）
        hist = attribute_history(stock, 1, '1d', ['close'], df=True)
        if hist is not None and not hist.empty:
            g.peak_prices[stock] = hist['close'].iloc[-1]
        log.info(f'【买入】{stock}  (替代仓位)')

    log.info(f'当前持仓：{len(context.portfolio.positions)}只  '
             f'总资产：{context.portfolio.total_value:.2f}')
