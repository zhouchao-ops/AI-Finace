#!/usr/bin/env python3
"""AKShare -> Qlib CSV collector for China A-share daily OHLCV."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import akshare as ak
import pandas as pd
from tqdm import tqdm


def to_qlib_symbol(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"SH{code}"
    return f"SZ{code}"


def fetch_symbol_csv(code: str, start: str, end: str, out_dir: Path, delay: float) -> bool:
    symbol = to_qlib_symbol(code)
    out_file = out_dir / f"{symbol.lower()}.csv"
    if out_file.exists():
        return True
    try:
        raw = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        if raw is None or raw.empty:
            return False
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(raw["日期"]).dt.strftime("%Y-%m-%d"),
                "open": raw["开盘"].astype(float),
                "high": raw["最高"].astype(float),
                "low": raw["最低"].astype(float),
                "close": raw["收盘"].astype(float),
                "volume": raw["成交量"].astype(float),
                "factor": 1.0,
            }
        )
        df.to_csv(out_file, index=False)
        time.sleep(delay)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] {code}: {exc}")
        time.sleep(delay)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download A-share OHLCV via AKShare")
    parser.add_argument("--source_dir", default="/data/chao/data/qlib/source/akshare_csv")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--index", default="000300")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    out_dir = Path(args.source_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.symbols.strip():
        codes = [c.strip() for c in args.symbols.split(",") if c.strip()]
    else:
        cons = ak.index_stock_cons(symbol=args.index)
        code_col = "品种代码" if "品种代码" in cons.columns else cons.columns[0]
        codes = cons[code_col].astype(str).str.zfill(6).tolist()

    if args.limit > 0:
        codes = codes[: args.limit]

    ok, fail = 0, 0
    for code in tqdm(codes, desc="download"):
        if fetch_symbol_csv(code, args.start, args.end, out_dir, args.delay):
            ok += 1
        else:
            fail += 1

    print(f"done: success={ok}, fail={fail}, dir={out_dir}")


if __name__ == "__main__":
    main()
