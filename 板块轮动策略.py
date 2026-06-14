'''
板块轮动策略（双条件触发 V2）
适用平台：聚宽（JoinQuant）

核心逻辑：
  每周检查各申万一级行业的过去20日涨幅排名，
  买入涨幅最好的前N个行业（每个行业买市值最大的3只沪深300成分股）。

  双条件触发：
    1. 新行业的平均涨幅 > 旧行业涨幅 + 阈值 → 调仓
    2. 差距不够大 → 继续持有，不产生交易

  改进：
    当同一个行业连续入选时，已有持仓不会重复买卖，节省手续费。
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
    g.top_n = 3                   # 持仓行业数量
    g.lookback = 20               # 回看天数
    g.min_advantage = 0.05        # 最小优势阈值（5%）
    g.min_stocks_per_industry = 3 # 行业最少成分股数
    g.stocks_per_industry = 3     # 每个行业买几只股票

    # ==================== 定时任务 ====================
    # 每周一开盘检查
    run_weekly(adjust_position, 1, time='open')


def filter_stocks(context, stock_list):
    '''过滤停牌 + ST'''
    current_data = get_current_data()
    result = []
    for stock in stock_list:
        if not current_data[stock].paused and not current_data[stock].is_st:
            result.append(stock)
    return result


def calc_industry_returns(context):
    '''
    计算每个申万一级行业的过去N日平均涨幅
    返回：[(industry_code, industry_name, avg_return), ...]
    '''
    hs300 = get_index_stocks('000300.XSHG')
    industries = get_industries('sw_l1')

    results = []
    for ind_code in industries.index:
        ind_name = industries.loc[ind_code, 'name']

        ind_stocks_all = get_industry_stocks(ind_code)
        ind_stocks = [s for s in ind_stocks_all if s in hs300]

        if len(ind_stocks) < g.min_stocks_per_industry:
            continue

        price_df = get_price(ind_stocks, count=g.lookback + 1,
                             end_date=context.current_dt,
                             fields=['close'], panel=False)
        if price_df.empty:
            continue

        returns = []
        for stock in ind_stocks:
            stock_prices = price_df[price_df['code'] == stock]['close']
            if len(stock_prices) >= 2:
                ret = stock_prices.iloc[-1] / stock_prices.iloc[0] - 1
                returns.append(ret)

        if returns:
            avg_return = sum(returns) / len(returns)
            results.append((ind_code, ind_name, avg_return))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def get_current_industries(context):
    '''获取当前持仓所在的行业列表'''
    holdings = list(context.portfolio.positions.keys())
    if not holdings:
        return []

    if not hasattr(g, 'stock_industry_cache'):
        g.stock_industry_cache = {}

    current_ind_codes = set()
    for stock in holdings:
        if stock in g.stock_industry_cache:
            ind_code = g.stock_industry_cache[stock]
        else:
            ind_info = get_industry(stock)
            if ind_info and 'sw_l1' in ind_info:
                ind_code = ind_info['sw_l1']['industry_code']
                g.stock_industry_cache[stock] = ind_code
            else:
                continue
        current_ind_codes.add(ind_code)

    industries = get_industries('sw_l1')
    result = []
    for code in current_ind_codes:
        if code in industries.index:
            result.append((code, industries.loc[code, 'name']))
    return result


def get_target_stocks(context, top_industries):
    '''
    获取目标行业的具体股票（每个行业市值最大的N只）
    '''
    hs300 = set(get_index_stocks('000300.XSHG'))
    target_stocks = []

    for ind_code, ind_name, _ in top_industries:
        ind_stocks = get_industry_stocks(ind_code)
        ind_hs300 = [s for s in ind_stocks if s in hs300]

        # 按市值排序取前N只
        if len(ind_hs300) > g.stocks_per_industry:
            q = query(valuation.code).filter(
                valuation.code.in_(ind_hs300)
            ).order_by(valuation.market_cap.desc()).limit(g.stocks_per_industry)
            df = get_fundamentals(q)
            if not df.empty:
                ind_hs300 = list(df['code'])

        target_stocks.extend(ind_hs300)

    return filter_stocks(context, target_stocks)


def adjust_position(context):
    '''
    调仓逻辑：
    1. 计算行业涨幅排名
    2. 如果已有持仓，只有新行业优势差 > 阈值时才调仓
    3. 调仓时只买卖有变化的股票，已有的不动
    '''
    # ---- 行业排名 ----
    ranked = calc_industry_returns(context)
    if len(ranked) < g.top_n:
        return

    top_industries = ranked[:g.top_n]
    current_industries = get_current_industries(context)

    # ---- 判断调仓还是持有 ----
    should_rotate = False

    if not current_industries:
        should_rotate = True
    else:
        new_avg = sum(r[2] for r in top_industries) / len(top_industries)
        ranked_dict = {r[0]: r[2] for r in ranked}
        current_returns = [ranked_dict.get(c[0], 0)
                           for c in current_industries if c[0] in ranked_dict]
        if current_returns:
            old_avg = sum(current_returns) / len(current_returns)
            if new_avg - old_avg > g.min_advantage:
                should_rotate = True
        else:
            should_rotate = True

    if not should_rotate:
        return

    # ---- 计算目标股票清单 ----
    target_stocks = get_target_stocks(context, top_industries)
    if not target_stocks:
        return

    # ---- 智能调仓：只买卖有变化的 ----
    current_stocks = set(context.portfolio.positions.keys())
    target_set = set(target_stocks)

    stocks_to_sell = current_stocks - target_set  # 不再持有的股票 → 卖
    stocks_to_buy = target_set - current_stocks   # 新入选的股票 → 买

    # 卖出
    for stock in stocks_to_sell:
        order_target_value(stock, 0)

    # 买入（资金均分给新股票）
    if stocks_to_buy:
        cash_per_stock = context.portfolio.available_cash / len(stocks_to_buy)
        for stock in stocks_to_buy:
            order_value(stock, cash_per_stock)

    # ---- 日志 ----
    log.info('=== 调仓 ===')
    for ind_code, ind_name, ret in top_industries:
        log.info(f'  {ind_name} +{ret*100:.1f}%')
    log.info(f'  卖出 {len(stocks_to_sell)}只 / 买入 {len(stocks_to_buy)}只 / '
             f'保留 {len(current_stocks & target_set)}只')
