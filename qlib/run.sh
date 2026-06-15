#!/usr/bin/env bash
# Qlib 环境激活
# 用法: source qlib/run.sh

export QLIB_ENV="/data/chao/data/qlib/env/qlib"
export QLIB_DATA="/data/chao/data/qlib"
export MLFLOW_ALLOW_FILE_STORE=true

source /home/chao/miniconda3/etc/profile.d/conda.sh
conda activate "$QLIB_ENV"

cd /home/chao/AI-Finace/qlib
