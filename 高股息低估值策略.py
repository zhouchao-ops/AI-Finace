'''
高股息/低估值选股策略
适用平台：聚宽（JoinQuant）

核心逻辑：
  每月第一个交易日调仓，在全A股中选股息率最高、
  同时PE/PB较低的股票，等权重买入20只。

赚钱逻辑：
  1. 分红收益 —— 高股息公司每年稳定派息
  2. 估值修复 —— 低PE/PB的"便宜"股票，长期会价值回归
  3. 防御属性 —— 高股息股通常是成熟行业，下跌市抗跌

参考聚宽社区经典高股息策略写法：
  https://www.joinquant.com/view/community/detail/63b1ccc0cd4185c3cc0e40d13f6d9614
'''


def initialize(context):
    # ==================== 基本设置 ====================
    set_benchmark('000300.XSHG')           # 基准：沪深300
    set_option('use_real_price', True)     # 使用真实价格交易
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
    g.max_pe = 15                 # 最大PE（经典写法 PE < 15）
    g.max_pb = 3                  # 最大PB
    g.min_dividend_yield = 3      # 最低股息率（%），经典写法 > 3.5%

    # ==================== 定时任务 ====================
    run_monthly(adjust_position, 1, time='open')


def filter_stocks(context, stock_list):
    '''
    过滤：停牌 + ST/*ST
    '''
    current_data = get_current_data()
    result = []
    for stock in stock_list:
        if not current_data[stock].paused and not current_data[stock].is_st:
            result.append(stock)
    return result


def select_stocks(context):
    '''
    选股：全A股 → 高股息 + 低PE + 低PB → 取前20
    '''
    q = query(
        valuation.code,
        valuation.market_cap,
        valuation.pe_ratio,
        valuation.pb_ratio,
        indicator.dividend_yield
    ).filter(
        indicator.dividend_yield > g.min_dividend_yield,
        valuation.pe_ratio > 0,
        valuation.pe_ratio < g.max_pe,
        valuation.pb_ratio > 0,
        valuation.pb_ratio < g.max_pb
    ).order_by(
        indicator.dividend_yield.desc()
    ).limit(g.stock_num * 2)      # 多取一些，留给后面的过滤

    df = get_fundamentals(q)
    if df.empty:
        return []

    # 过滤ST和停牌
    stock_list = filter_stocks(context, list(df['code']))

    return stock_list[:g.stock_num]


def adjust_position(context):
    '''调仓：先卖后买，等权重分配'''
    # ---- 选股 ----
    target_stocks = select_stocks(context)
    if not target_stocks:
        log.warn('未选出任何股票，跳过本次调仓')
        return

    # ---- 卖出所有持仓 ----
    for stock in list(context.portfolio.positions.keys()):
        order_target_value(stock, 0)

    # ---- 等权重买入目标股票 ----
    cash_per_stock = context.portfolio.total_value / len(target_stocks)

    for stock in target_stocks:
        order_value(stock, cash_per_stock)

    # ---- 调仓日志 ----
    log.info('=' * 40)
    log.info(f'调仓完成 | 持仓：{len(target_stocks)}只')
    for stock in target_stocks[:5]:                     # 只打印前5只
        log.info(f'  {stock}')
    if len(target_stocks) > 5:
        log.info(f'  ... 共{len(target_stocks)}只')
    log.info(f'总资产：{context.portfolio.total_value:.2f}')
    log.info('=' * 40)
