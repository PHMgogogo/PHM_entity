#!/usr/bin/env python3
"""随机生成多参时序数据.csv（四种参数随时间变化，均叠加高斯扰动）。

输出文件位于工作区根目录（本脚本的上两级）的 data 目录下，文件名 `多参时序数据.csv`。
CSV 包含四列、带英文表头、无编号列：

    time,logarithmic,linear,power
    00:00:00,25.03,25.18,25.05
    00:00:01,26.71,25.68,25.15
    ...

- 第一列：形如 hh:mm:ss 的时间戳，按固定间隔递增。
- 第二列 logarithmic：对数趋势 `T = base + amp * ln(1 + i/tau)`。
- 第三列 linear：线性趋势 `T = base + slope * i`。
- 第四列 power：幂指趋势（指数约 1.5）`T = base + coef * i ** 1.5`。

仅依赖 Python 标准库。运行示例：

    python scripts/generate_multi_param_timeseries.py
"""
import csv
import math
import random
from pathlib import Path

# 默认输出到工作区根目录（本脚本的上两级目录）的 data 子目录。
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "多参时序数据.csv"

POINTS = 100          # 数据点数量
INTERVAL = 1          # 相邻样本的时间间隔，单位秒
START_OFFSET = 0      # 首个时间戳相对 00:00:00 的偏移，单位秒
NOISE_STD = 1.5       # 高斯扰动标准差
SEED = 42             # 固定随机数种子，保证结果可复现

# 各列趋势参数
LOG_BASE, LOG_AMP, LOG_TAU = 25.0, 30.0, 20.0   # 对数趋势
LIN_BASE, LIN_SLOPE = 25.0, 0.5                 # 线性趋势
POW_BASE, POW_COEF, POW_EXP = 25.0, 0.05, 1.5   # 幂指趋势（指数约 1.5）


def fmt_time(total_seconds: int) -> str:
    """把从零起算的总秒数格式化为 hh:mm:ss（小时位数不封顶，便于大间隔）。"""
    hours, rem = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main() -> None:
    rng = random.Random(SEED)

    rows: list[list] = []
    for i in range(POINTS):
        timestamp = fmt_time(START_OFFSET + i * INTERVAL)
        # 三种趋势，各自叠加独立的高斯扰动。
        logarithmic = LOG_BASE + LOG_AMP * math.log1p(i / LOG_TAU) + rng.gauss(0.0, NOISE_STD)
        linear = LIN_BASE + LIN_SLOPE * i + rng.gauss(0.0, NOISE_STD)
        power = POW_BASE + POW_COEF * (i ** POW_EXP) + rng.gauss(0.0, NOISE_STD)
        rows.append([timestamp, round(logarithmic, 2), round(linear, 2), round(power, 2)])

    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "logarithmic", "linear", "power"])
        writer.writerows(rows)

    print(f"已生成 {len(rows)} 个数据点 -> {OUTPUT}")
    print(f"时间范围：{rows[0][0]} ~ {rows[-1][0]}")
    for col_idx, name in enumerate(["logarithmic", "linear", "power"], start=1):
        values = [r[col_idx] for r in rows]
        print(f"{name:<11} 范围：{min(values):.2f} ~ {max(values):.2f}（均值 {sum(values)/len(values):.2f}）")


if __name__ == "__main__":
    main()
