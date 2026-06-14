'''
个股动量策略（双条件触发）
适用平台：聚宽（JoinQuant）

核心逻辑：
  在沪深300里，计算每只股票过去20日的涨幅，
  买入涨幅最好的前N只。

  双条件：
    1. 新入选股票的平均涨幅 > 当前持仓平均涨幅 + 阈值 → 调仓
    2. 差距不够大 → 继续持有，不动

  调仓时只买卖有变化的股票，已有的保留，节省手续费。
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
    g.top_n = 9                   # 持仓股票数量
    g.lookback = 20               # 回看天数
    g.min_advantage = 0.05        # 最小优势阈值（5%），低于此不换

    # ==================== 定时任务 ====================
    run_weekly(adjust_position, 1, time='open')


def filter_stocks(context, stock_list):
    '''过滤停牌 + ST'''
    current_data = get_current_data()
    result = []
    for stock in stock_list:
        if not current_data[stock].paused and not current_data[stock].is_st:
            result.append(stock)
    return result


def calc_stock_returns(context, stock_list):
    '''
    计算每只股票的过去N日涨幅
    返回：{ stock_code: return_pct }
    '''
    price_df = get_price(stock_list, count=g.lookback + 1,
                         end_date=context.current_dt,
                         fields=['close'], panel=False)
    if price_df.empty:
        return {}

    returns = {}
    for stock in stock_list:
        stock_prices = price_df[price_df['code'] == stock]['close']
        if len(stock_prices) >= 2:
            ret = stock_prices.iloc[-1] / stock_prices.iloc[0] - 1
            returns[stock] = ret
    return returns


def select_top_stocks(context):
    '''
    选股：沪深300中按过去涨幅排序，取涨幅最大的前N只
    '''
    hs300 = get_index_stocks('000300.XSHG')

    # 计算每只股票的涨幅
    returns = calc_stock_returns(context, hs300)

    # 过滤停牌和ST
    hs300 = filter_stocks(context, hs300)

    # 按涨幅降序排列
    ranked = [(stock, ret) for stock, ret in returns.items()
              if stock in hs300 and ret is not None]
    ranked.sort(key=lambda x: x[1], reverse=True)

    if not ranked:
        return [], []

    # 取前N只
    top_stocks = [s[0] for s in ranked[:g.top_n]]
    top_returns = ranked[:g.top_n]

    return top_stocks, top_returns


def adjust_position(context):
    '''
    调仓逻辑：
    1. 计算所有股票涨幅排名
    2. 如果已有持仓，只有新股票平均涨幅 > 旧持仓阈值时才换
    3. 调仓时只买卖有变化的，已有的不动
    '''
    # ---- 选股 ----
    target_stocks, top_returns = select_top_stocks(context)
    if not target_stocks:
        return

    # ---- 判断是否调仓 ----
    current_stocks = list(context.portfolio.positions.keys())
    should_rotate = False

    if not current_stocks:
        # 首次建仓
        should_rotate = True
        log.info('首次建仓')
    else:
        # 新入选股票的平均涨幅
        new_avg = sum(r[1] for r in top_returns) / len(top_returns)

        # 当前持仓股票的平均涨幅（从排名结果中查）
        returns_dict = dict(top_returns)
        current_returns = [returns_dict.get(s, 0) for s in current_stocks
                           if s in returns_dict]
        if current_returns:
            old_avg = sum(current_returns) / len(current_returns)
            advantage = new_avg - old_avg

            # 打印排名前5
            log.info(f'涨幅前5：')
            for s, r in top_returns[:5]:
                log.info(f'  {s}  +{r*100:.1f}%')
            log.info(f'优势差={advantage*100:.1f}%  (阈值{g.min_advantage*100:.0f}%)')

            if advantage > g.min_advantage:
                should_rotate = True
            else:
                return  # 不够优势，不动
        else:
            should_rotate = True

    if not should_rotate:
        return

    # ---- 智能调仓：只买卖有变化的 ----
    current_set = set(current_stocks)
    target_set = set(target_stocks)

    stocks_to_sell = current_set - target_set
    stocks_to_buy = target_set - current_set

    # 卖出
    for stock in stocks_to_sell:
        order_target_value(stock, 0)

    # 买入（资金均分给新股票）
    if stocks_to_buy:
        cash_per_stock = context.portfolio.available_cash / len(stocks_to_buy)
        for stock in stocks_to_buy:
            order_value(stock, cash_per_stock)

    # ---- 日志 ----
    log.info(f'调仓 | 卖出{len(stocks_to_sell)}只 / 买入{len(stocks_to_buy)}只 / '
             f'保留{len(current_set & target_set)}只 / '
             f'总资产{context.portfolio.total_value:.2f}')
