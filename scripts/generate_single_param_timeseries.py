#!/usr/bin/env python3
"""随机生成单参时序数据.csv（温度随时间的对数趋势 + 高斯扰动）。

输出文件位于工作区根目录（本脚本的上两级），默认文件名 `单参时序数据.csv`。
CSV 包含两列、带表头、无编号列：

    时间,温度(℃)
    00:00:00,25.03
    00:00:01,25.18
    ...

- 第一列：形如 hh:mm:ss 的时间戳，按固定间隔递增。
- 第二列：摄氏温度，沿对数趋势 `T(i) = t_start + amplitude * ln(1 + (i-1)/tau)`
  生成，并叠加均值为 0、标准差为 noise_std 的高斯噪声。

仅依赖 Python 标准库。运行示例：

    python scripts/generate_single_param_timeseries.py
    python scripts/generate_single_param_timeseries.py --points 100 --seed 42
    python scripts/generate_single_param_timeseries.py --output 单参时序.csv --noise-std 2.0
"""
import argparse
import csv
import math
import random
from pathlib import Path

# 默认输出到工作区根目录（本脚本的上两级目录）。
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "单参时序数据.csv"


def fmt_time(total_seconds: int) -> str:
    """把从零起算的总秒数格式化为 hh:mm:ss（小时位数不封顶，便于大间隔）。"""
    hours, rem = divmod(int(total_seconds), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def generate(args: argparse.Namespace) -> list[tuple[str, float]]:
    """生成 (时间, 温度) 数据点列表。"""
    rng = random.Random(args.seed)

    rows: list[tuple[str, float]] = []
    for i in range(args.points):
        timestamp = fmt_time(args.start_offset + i * args.interval)
        # 对数趋势：随采样序号增大，温度上升但增速放缓。
        trend = args.t_start + args.amplitude * math.log1p(i / args.time_constant)
        value = trend + rng.gauss(mu=0.0, sigma=args.noise_std)
        rows.append((timestamp, round(value, 2)))
    return rows


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="随机生成单参时序温度数据（对数趋势 + 高斯扰动）。")
    ap.add_argument("-n", "--points", type=int, default=100,
                    help="数据点数量（默认 100）")
    ap.add_argument("--interval", type=int, default=1,
                    help="相邻样本的时间间隔，单位秒（默认 1）")
    ap.add_argument("--start-offset", type=int, default=0,
                    help="首个时间戳相对 00:00:00 的偏移，单位秒（默认 0）")
    ap.add_argument("--t-start", type=float, default=25.0,
                    help="对数趋势起始温度 / 环境温度，单位 ℃（默认 25.0）")
    ap.add_argument("--amplitude", type=float, default=30.0,
                    help="对数趋势幅度，控制总升温量，单位 ℃（默认 30.0）")
    ap.add_argument("--time-constant", type=float, default=20.0,
                    help="对数趋势时间常数 tau，越大升温越缓（默认 20.0）")
    ap.add_argument("--noise-std", type=float, default=1.5,
                    help="高斯扰动标准差，单位 ℃（默认 1.5）")
    ap.add_argument("--seed", type=int, default=None,
                    help="随机数种子；不指定则每次运行结果不同")
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT,
                    help=f"输出 CSV 路径（默认：{DEFAULT_OUTPUT}）")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.points <= 0:
        raise SystemExit(f"--points 必须为正整数，收到 {args.points}")
    if args.interval < 0:
        raise SystemExit(f"--interval 不能为负，收到 {args.interval}")

    rows = generate(args)

    # utf-8-sig 带 BOM，便于 Windows Excel 正确识别中文表头；pandas 读取同样兼容。
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["时间", "温度(℃)"])
        writer.writerows(rows)

    temps = [t for _, t in rows]
    print(f"已生成 {len(rows)} 个数据点 -> {args.output}")
    print(f"时间范围：{rows[0][0]} ~ {rows[-1][0]}")
    print(f"温度范围：{min(temps):.2f} ~ {max(temps):.2f} ℃（均值 {sum(temps)/len(temps):.2f} ℃）")


if __name__ == "__main__":
    main()
