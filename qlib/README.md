# Qlib 本地研究环境

第三周：数据 → 因子 → 模型 → 策略 → 回测 → 评价

## 目录

```
/data/chao/data/qlib/     # 数据与环境（大盘，勿放根分区）
/home/chao/AI-Finace/qlib/ # 脚本与配置
```

## 快速开始

```bash
source qlib/run.sh
export MLFLOW_TRACKING_URI=/data/chao/data/qlib/logs/mlruns
qrun workflow_config_lightgbm_Alpha158.yaml      # 官方 cn_data
qrun workflow_config_akshare_Alpha158.yaml      # 自采 Baostock 数据
```

## 环境

```bash
conda create -p /data/chao/data/qlib/env/qlib python=3.10 -y
conda activate /data/chao/data/qlib/env/qlib
pip install pyqlib lightgbm akshare baostock pandas mlflow loguru
export MLFLOW_ALLOW_FILE_STORE=true
```

## 数据采集

```bash
python baostock_download.py --source_dir /data/chao/data/qlib/source/akshare_csv
python ~/qlib-src/scripts/dump_bin.py dump_all \
  --data_path /data/chao/data/qlib/source/akshare_csv \
  --qlib_dir /data/chao/data/qlib/akshare_data \
  --include_fields open,close,high,low,volume,factor \
  --date_field_name date
```

详见 `第三周报告.md`。
