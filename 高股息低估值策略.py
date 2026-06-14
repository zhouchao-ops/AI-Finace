'''
高股息/低估值选股策略
适用平台：聚宽（JoinQuant）

核心逻辑：
  每月调仓，在全A股中计算近12个月实际股息率，
  选出股息率最高、同时PE/PB较低的股票，等权重买入20只。

  股息率 = 近12个月每股分红总和 ÷ 当前股价
  数据来源：finance.STK_XR_XD（分红送配表），非indicator表

赚钱逻辑：
  1. 分红收益 —— 高股息公司每年稳定派息
  2. 估值修复 —— 低PE/PB的"便宜"股票，长期会价值回归
  3. 防御属性 —— 高股息股通常是成熟行业，下跌市抗跌
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
    g.stock_num = 20              # 持仓数量
    g.max_pe = 15                 # 最大PE
    g.max_pb = 3                  # 最大PB
    g.min_market_cap = 10         # 最低市值（亿元）
    g.min_dividend_yield = 4      # 最低股息率（%），大额存单~2.5% + 风险溢价

    # ==================== 定时任务 ====================
    # 每季度首月调仓（1月、4月、7月、10月），函数内部做月份判断
    run_monthly(adjust_position, 1, time='open')


def filter_stocks(context, stock_list):
    '''过滤停牌 + ST'''
    current_data = get_current_data()
    result = []
    for stock in stock_list:
        if not current_data[stock].paused and not current_data[stock].is_st:
            result.append(stock)
    return result


def get_ttm_dividend_yields(context, stock_list):
    '''
    计算每只股票的近12个月股息率（TTM）
    返回：{ code: dividend_yield_pct } 的字典
    '''
    end_date = context.current_dt
    start_date = end_date - datetime.timedelta(days=365)

    # 查询分红数据
    bonus_df = finance.run_query(query(
        finance.STK_XR_XD.code,
        finance.STK_XR_XD.bonus_ratio_rmb
    ).filter(
        finance.STK_XR_XD.code.in_(stock_list),
        finance.STK_XR_XD.a_bonus_date >= start_date,
        finance.STK_XR_XD.a_bonus_date <= end_date,
        finance.STK_XR_XD.bonus_ratio_rmb.isnot(None)
    ))

    if bonus_df.empty:
        return {}

    # 计算每只股票的分红总和（bonus_ratio_rmb 是每10股派现金）
    bonus_df['div_per_share'] = bonus_df['bonus_ratio_rmb'] / 10.0
    div_sum = bonus_df.groupby('code')['div_per_share'].sum().to_dict()

    # 获取当前不复权价格
    price_df = get_price(stock_list, end_date=end_date, count=1,
                         fields=['close'], fq=None, panel=False)
    if price_df.empty:
        return {}

    # 计算股息率
    yields = {}
    for _, row in price_df.iterrows():
        code = row['code']
        price = row['close']
        if code in div_sum and price > 0:
            yields[code] = (div_sum[code] / price) * 100

    return yields


def select_stocks(context):
    '''
    选股逻辑：
    1. 全A股中筛选低PE、低PB的候选股票
    2. 计算每只候选股的TTM股息率
    3. 按股息率降序排列，取前20只
    '''
    # ---- 第一步：获取沪深300成分股，筛选低PE、低PB ----
    hs300 = get_index_stocks('000300.XSHG')

    q = query(
        valuation.code,
        valuation.market_cap,
        valuation.pe_ratio,
        valuation.pb_ratio
    ).filter(
        valuation.code.in_(hs300),
        valuation.pe_ratio > 0,
        valuation.pe_ratio < g.max_pe,
        valuation.pb_ratio > 0,
        valuation.pb_ratio < g.max_pb,
        valuation.market_cap > g.min_market_cap
    ).order_by(
        valuation.pe_ratio.asc()
    ).limit(g.stock_num * 10)

    df = get_fundamentals(q)
    if df.empty:
        return []
    candidates = list(df['code'])

    # ---- 第二步：计算候选股的TTM股息率 ----
    yield_dict = get_ttm_dividend_yields(context, candidates)

    # 筛掉没有分红数据或股息率不足的
    qualified = [(code, y) for code, y in yield_dict.items()
                 if y > g.min_dividend_yield]

    if not qualified:
        return []

    # ---- 第三步：按股息率降序排列 ----
    qualified.sort(key=lambda x: x[1], reverse=True)
    top_stocks = [s[0] for s in qualified[:g.stock_num]]

    # ---- 第四步：过滤停牌和ST ----
    top_stocks = filter_stocks(context, top_stocks)

    return top_stocks[:g.stock_num]


def adjust_position(context):
    '''调仓：每季度首月执行（1/4/7/10月），先卖后买，等权重分配'''
    # 季度调仓：只在1月、4月、7月、10月执行
    if context.current_dt.month not in [1, 4, 7, 10]:
        return

    target_stocks = select_stocks(context)
    if not target_stocks:
        log.warn('未选出任何股票，跳过本次调仓')
        return

    # ---- 卖出所有持仓 ----
    for stock in list(context.portfolio.positions.keys()):
        order_target_value(stock, 0)

    # ---- 等权重买入 ----
    cash_per_stock = context.portfolio.total_value / len(target_stocks)
    for stock in target_stocks:
        order_value(stock, cash_per_stock)

    # ---- 调仓日志 ----
    log.info('=' * 40)
    log.info(f'调仓完成 | 持仓：{len(target_stocks)}只')
    for stock in target_stocks[:5]:
        log.info(f'  {stock}')
    if len(target_stocks) > 5:
        log.info(f'  ... 共{len(target_stocks)}只')
    log.info(f'总资产：{context.portfolio.total_value:.2f}')
    log.info('=' * 40)
