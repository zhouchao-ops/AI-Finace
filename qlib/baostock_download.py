#!/usr/bin/env python3
"""Baostock -> Qlib CSV collector (stable bulk download for A-shares)."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import akshare as ak
import baostock as bs
import pandas as pd
from tqdm import tqdm


def to_baostock_code(code: str) -> str:
    code = str(code).zfill(6)
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}.{code}"


def to_qlib_fname(code: str) -> str:
    code = str(code).zfill(6)
    prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}.csv"


def fetch_one(code: str, start: str, end: str, out_dir: Path, retries: int = 3) -> bool:
    out_file = out_dir / to_qlib_fname(code)
    if out_file.exists() and out_file.stat().st_size > 100:
        return True

    bs_code = to_baostock_code(code)
    for attempt in range(retries):
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag="2",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        if rs.error_code == "0" and rows:
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["factor"] = 1.0
            df = df.dropna(subset=["close"])
            if df.empty:
                return False
            df.to_csv(out_file, index=False)
            return True
        time.sleep(0.5 * (attempt + 1))
    print(f"[WARN] failed: {code}")
    return False


def get_codes(index: str, symbols: str) -> list[str]:
    if symbols.strip():
        return [c.strip().zfill(6) for c in symbols.split(",") if c.strip()]
    cons = ak.index_stock_cons(symbol=index)
    col = "品种代码" if "品种代码" in cons.columns else cons.columns[0]
    return cons[col].astype(str).str.zfill(6).tolist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source_dir", default="/data/chao/data/qlib/source/akshare_csv")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--index", default="000300")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    out_dir = Path(args.source_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    codes = get_codes(args.index, args.symbols)
    if args.limit > 0:
        codes = codes[: args.limit]

    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(lg.error_msg)

    ok = fail = 0
    try:
        for code in tqdm(codes, desc="baostock"):
            if fetch_one(code, args.start, args.end, out_dir):
                ok += 1
            else:
                fail += 1
            time.sleep(0.05)
    finally:
        bs.logout()

    print(f"done: success={ok}, fail={fail}, dir={out_dir}")


if __name__ == "__main__":
    main()
