import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
import httpx

from app.config import (
    DISPLAY_CANVAS_DIR,
    DISPLAY_CANVAS_MAX_COUNT,
    DISPLAY_CANVAS_TTL_SECONDS,
    SQL_ENDPOINT,
)

router = APIRouter(prefix="/api", tags=["display"])

# 进程级共享 HTTP 客户端:全模块复用同一个连接池 + keep-alive。
# 此前每次请求都 `async with httpx.AsyncClient(...)`,仅客户端构造就耗时
# ~2.2s(默认会建 SSL 上下文加载系统证书库 + trust_env 读代理,而目标
# 是 http LAN 地址,二者均用不上)。改为启动期构造一次,从热路径移除。
# trust_env=False:只访问 LAN http 主机,不需要代理 / .netrc 查找。
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, connect=10.0),
    trust_env=False,
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)

# 时序维度的特殊单位标识:前端按 time/date 做特殊解析与展示。
# 后端无法区分 time 与 date,时序轴统一用 "time" 标识。
TIME_UNIT = "time"

# type 枚举:决定向 SQL 请求的列数与行式 → 系列式的转换规则
DisplayType = Literal[
    "SINGLE_TIMESERIES_2D",
    "MULTI_TIMESERIES_2D",
    "MAPPING_2D",
    "POINT_CLOUD_3D",
]

# 各 type 期望的列数:(下限, 上限);上限为 None 表示仅约束下限
_EXPECTED_COLUMNS: dict[str, tuple[int, int | None]] = {
    "SINGLE_TIMESERIES_2D": (2, 2),     # 恰好 2 列:时间 + 参数
    "MULTI_TIMESERIES_2D": (3, None),   # 至少 3 列:时间 + 多个参数
    "MAPPING_2D": (2, 2),               # 恰好 2 列:x + y
    "POINT_CLOUD_3D": (3, 3),           # 恰好 3 列:x + y + z
}


# ── 请求 / 响应模型 ───────────────────────────────────────────────────
class DisplayRequest(BaseModel):
    """POST /api/display/raw-data 请求体。

    本接口向外部 CSV 模块发起 SQL 查询,并将其行式返回值按 `type` 转换为
    前端约定的系列式图表数据。
    """

    data: str = Field(..., description="数据来源标识,对应 SQL 中的 csv_{data} 表名部分;已带 csv_ 前缀时容忍不重复拼接")
    columns: list[str] = Field(
        ...,
        description="参与展示的列名列表,列数须与 type 约定一致;原样加引号拼入 SELECT,须为 /csv/overview 下发的实际列名",
    )
    limit: int = Field(0, ge=0, description="返回数据点数量上限;0 表示不限制(不生成 LIMIT 子句)")
    type: DisplayType = Field(..., description="图表类型,决定列数约束与转换规则")


class DimensionObject(BaseModel):
    """单个坐标轴 / 维度定义。时序轴 unit 标为 `time`,其余默认空串。"""

    name: str = Field(..., description="维度名称,取自查询结果的列名")
    unit: str = Field("", description="数据单位;时序轴为 time,其余默认空串")


class SeriesObject(BaseModel):
    """单个数据系列。data 为二维数组,内层点元素顺序与 dimensions 一致。"""

    parameter: str = Field(..., description="参数名称,与 parameter 列表中的元素对应")
    color: str | None = Field(None, description="系列颜色(可选),由前端分配")
    data: list[list[Any]] = Field(..., description="数据点集合")


class DisplayResponse(BaseModel):
    """POST /api/display/raw-data 响应体。"""

    dimensions: list[DimensionObject] = Field(..., description="图表维度定义,长度决定坐标轴数量")
    parameter: list[str] = Field(..., description="参数名称列表,每个元素对应 data 中一个数据系列")
    data: list[SeriesObject] = Field(..., description="数据系列集合,长度与 parameter 列表一致")


# ── 工具函数 ──────────────────────────────────────────────────────────
def _coerce_value(v: Any) -> Any:
    """将上游返回的字符串数值转为数值类型,无法解析则原样返回。

    上游 CSV 模块对所有列值统一返回字符串(如 "3.708842"),图表数据点期望
    数值类型;非数值列(时间标签、标识、描述)保持字符串不变。
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s == "":
        return v
    try:
        return float(s)
    except ValueError:
        return v


def _quote_identifier(name: str) -> str:
    """把列名包装为 SQL 引号标识符;内嵌双引号按 SQL 约定转义("→"")。"""
    return '"' + name.replace('"', '""') + '"'


def _validate_columns(type_: str, n: int) -> None:
    """按 type 校验列数,不符则抛 422。"""
    lo, hi = _EXPECTED_COLUMNS[type_]
    if hi is None:
        if n < lo:
            raise HTTPException(
                status_code=422,
                detail=f"{type_} requires at least {lo} columns, got {n}",
            )
    elif n != hi:
        raise HTTPException(
            status_code=422,
            detail=f"{type_} requires exactly {hi} columns, got {n}",
        )


def _build_series(rows: list[dict[str, Any]], axis: list[str], params: list[str]) -> list[SeriesObject]:
    """为每个参数生成一个数据系列。

    每个数据点 = [各 axis 列的行值..., 该参数的行值],字符串数值会被转为数值类型。
    - axis 为轴列(时间 / x / y),对所有系列共用;
    - params 为参数列,每个参数产出一个系列。
    """
    series_list: list[SeriesObject] = []
    for p in params:
        points: list[list[Any]] = []
        for row in rows:
            point = [_coerce_value(row.get(ac)) for ac in axis]
            point.append(_coerce_value(row.get(p)))
            points.append(point)
        series_list.append(SeriesObject(parameter=p, data=points))
    return series_list


def _transform(type_: str, cols: list[str], rows: list[dict[str, Any]]) -> DisplayResponse:
    """按 type 把行式数据转换为系列式响应。"""
    if type_ == "SINGLE_TIMESERIES_2D":
        # col[0]=时间轴, col[1]=参数;单系列,点=[时间, 参数]
        dimensions = [
            DimensionObject(name=cols[0], unit=TIME_UNIT),
            DimensionObject(name=cols[1]),
        ]
        parameter = [cols[1]]
        data = _build_series(rows, axis=[cols[0]], params=[cols[1]])

    elif type_ == "MULTI_TIMESERIES_2D":
        # col[0]=时间轴, col[1:]=参数;dimensions 只取前两列(时间 + 首参数),
        # 但每个参数系列各自配对自己的值,点=[时间, 该参数]
        dimensions = [
            DimensionObject(name=cols[0], unit=TIME_UNIT),
            DimensionObject(name=cols[1]),
        ]
        parameter = list(cols[1:])
        data = _build_series(rows, axis=[cols[0]], params=cols[1:])

    elif type_ == "MAPPING_2D":
        # col[0]=x, col[1]=y;单系列,点=[x, y]
        dimensions = [
            DimensionObject(name=cols[0]),
            DimensionObject(name=cols[1]),
        ]
        parameter = [cols[1]]
        data = _build_series(rows, axis=[cols[0]], params=[cols[1]])

    else:  # POINT_CLOUD_3D
        # col[0]=x, col[1]=y, col[2]=z;单系列,点=[x, y, z]
        dimensions = [
            DimensionObject(name=cols[0]),
            DimensionObject(name=cols[1]),
            DimensionObject(name=cols[2]),
        ]
        parameter = [cols[2]]
        data = _build_series(rows, axis=[cols[0], cols[1]], params=[cols[2]])

    return DisplayResponse(dimensions=dimensions, parameter=parameter, data=data)


# ── 接口 ──────────────────────────────────────────────────────────────
@router.post("/display/raw-data", response_model=DisplayResponse, response_model_exclude_none=True)
async def display(req: DisplayRequest):
    """根据 data / columns / limit / type 拼装 SQL 查询外部 CSV 模块,并按 type
    把行式返回值转换为前端约定的系列式图表数据。

    SQL 形如:`SELECT "{col1}", "{col2}" FROM csv_{data} [LIMIT {limit}]`
    (列名引号原样引用,见表名/列名拼接处注释)。
    转换规则见 `_transform`。
    """
    # ── 1. 校验列数 ──────────────────────────────────────────────────
    _validate_columns(req.type, len(req.columns))

    # ── 2. 拼装 SQL ──────────────────────────────────────────────────
    # 列名加引号并保持原样大小写:CSV 模块建表时以引号标识符保留列名原始大小写
    # (通常为小写),达梦大小写敏感,未加引号的标识符会被折叠为大写而查不到列。
    columns_sql = ", ".join(_quote_identifier(c) for c in req.columns)
    # 表名则不加引号(建表时未加引号,达梦中引号形态反而查不到表);容忍 data 已带 csv_ 前缀
    table = req.data[4:] if req.data.lower().startswith("csv_") else req.data
    sql = f"SELECT {columns_sql} FROM csv_{table}"
    print(f"[display] SQL: {sql} (limit={req.limit})")
    if req.limit > 0:
        sql += f" LIMIT {req.limit}"

    # ── 3. 向外部 CSV 模块发起请求(复用共享 _http_client)────────────
    try:
        # 手动序列化并指定 ensure_ascii=False,
        # 避免 httpx 默认 json= 将中文转义为 \uXXXX
        payload = json.dumps({"sql": sql}, ensure_ascii=False)
        resp = await _http_client.post(
            SQL_ENDPOINT,
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="Cannot connect to CSV service")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="CSV service timed out")
    except httpx.HTTPStatusError as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail=f"CSV service returned {e.response.status_code}: {e.response.text[:500]}",
        )

    upstream = resp.json()

    # ── 4. 校验上游返回 ─────────────────────────────────────────────
    if not upstream.get("success", False):
        raise HTTPException(
            status_code=502,
            detail=f"CSV service reported failure: {upstream}",
        )

    rows: list[dict[str, Any]] = upstream.get("data", []) or []
    # 列顺序以请求为准:rows 是按列名索引的 dict,_build_series 经 row.get(key)
    # 取值,点结构完全由 cols 顺序决定,不受上游 columns 返回顺序影响。
    # 行的键即请求列名的原样大小写(与拼 SQL 的引号列名一致),不再统一大写。
    cols: list[str] = list(req.columns)

    # ── 5. 行式 → 系列式转换 ───────────────────────────────────────
    result = _transform(req.type, cols, rows)
    return result


# ── 画布快照持久化(opaque blob store)──────────────────────────────
# 数据展示页(MonitorView)的画布状态序列化为 JSON,后端原样落盘、原样取回。
# 硬约束:canvas 是「不透明 blob」,只逐字段保真存取——不解析、不裁剪、
# 不强转类型、不重排字段(见 plan.md §1 / §4.1)。因此本接口不使用 Pydantic
# 解析请求体,而是直接读取原始 body 经 json.loads 处理:Python json 模块对
# int/float/bool/None 与字典插入顺序均逐字段保真,足以满足契约。
_CANVAS_DIR = Path(DISPLAY_CANVAS_DIR)

# 保留策略(惰性清理,见 cleanup_canvas_store):最后访问(save/load)距今超过
# TTL 即过期;数量超过 MAX 时按最久未访问优先淘汰。
_CANVAS_TTL_SECONDS = DISPLAY_CANVAS_TTL_SECONDS
_CANVAS_MAX_COUNT = DISPLAY_CANVAS_MAX_COUNT

# key 直接用作落盘文件名,必须做路径穿越防护:仅允许白名单字符且限长 64,
# 拒绝空串 / ".." / "/" 等,避免写出到存储目录之外。
_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_MAX_KEY_LENGTH = 64


def _validate_key(key: Any) -> str:
    """校验画布 key,通过则返回其值;非法 key 抛 400。"""
    if not isinstance(key, str) or not key:
        raise HTTPException(status_code=400, detail="key must be a non-empty string")
    if len(key) > _MAX_KEY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"key too long (max {_MAX_KEY_LENGTH} chars)",
        )
    if not _KEY_PATTERN.fullmatch(key):
        raise HTTPException(
            status_code=400,
            detail="key may only contain letters, digits, '_' and '-'",
        )
    return key


def _canvas_path(key: str) -> Path:
    """返回 key 对应的落盘文件路径:<DIR>/<key>.json。"""
    return _CANVAS_DIR / f"{key}.json"


def _safe_unlink(path: Path) -> bool:
    """删除文件,失败返回 False 而不抛出(best-effort)。"""
    try:
        path.unlink()
        return True
    except OSError:
        return False


def cleanup_canvas_store() -> dict[str, int]:
    """惰性清理画布快照目录(best-effort,任何异常仅告警、不抛出)。

    规则:
    1. 过期:文件 mtime(最后访问)距今超过 ``_CANVAS_TTL_SECONDS`` → 删除;
    2. 总量:剩余数量超过 ``_CANVAS_MAX_COUNT`` 时,按 mtime 升序(最久未访问
       优先)淘汰至不超过上限。

    「访问时间」取文件 mtime——save 写入、load 的 touch 均会刷新。由 save 与
    进程启动(main.py lifespan)触发。
    """
    stats = {"expired": 0, "evicted": 0, "remaining": 0}
    try:
        if not _CANVAS_DIR.is_dir():
            return stats
        now = time.time()
        live: list[tuple[float, Path]] = []
        for p in _CANVAS_DIR.iterdir():
            # 仅处理正式快照,跳过 .tmp 等中间文件
            if p.suffix != ".json" or not p.is_file():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if now - mtime > _CANVAS_TTL_SECONDS:
                if _safe_unlink(p):
                    stats["expired"] += 1
                continue
            live.append((mtime, p))

        # 总量上限:最久未访问(mtime 最小)优先淘汰
        live.sort(key=lambda t: t[0])
        excess = max(0, len(live) - _CANVAS_MAX_COUNT)
        for _, p in live[:excess]:
            if _safe_unlink(p):
                stats["evicted"] += 1
        stats["remaining"] = max(0, len(live) - stats["evicted"])
        if stats["expired"] or stats["evicted"]:
            print(f"[display] canvas cleanup: {stats}")
        return stats
    except OSError as e:
        print(f"[display] canvas cleanup failed: {e}")
        return stats


@router.post("/display/save")
async def save_canvas(request: Request):
    """保存(覆盖)当前画布快照。

    请求体即「存储信封」``{ key, canvas, timestamp }``:后端原样持久化整个
    请求体并附加服务端落盘时刻 ``savedAt``。``canvas`` 当作不透明 blob 逐字段
    保真存储(见 plan.md §3.1 / §4.1),同 key 再次保存即覆盖(last-write-wins)。

    成功返回 ``{ key, savedAt }``(见 plan.md §3.1)。
    """
    # ── 1. 读取原始请求体并解析(不经 Pydantic,保证 canvas 保真)────
    raw = await request.body()
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="request body is not valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be a JSON object")

    # ── 2. 校验信封字段:key / canvas 必备 ─────────────────────────
    key = _validate_key(body.get("key"))
    if body.get("canvas") is None:
        raise HTTPException(status_code=400, detail="missing 'canvas' in request body")

    # ── 3. 附加服务端落盘时刻(savedAt),原样落盘整个信封 ───────────
    # canvas 未被触碰;ensure_ascii=False 仅影响存储形式,json 往返无损。
    saved_at = datetime.now(timezone.utc).isoformat()
    body["savedAt"] = saved_at
    payload = json.dumps(body, ensure_ascii=False)

    _CANVAS_DIR.mkdir(parents=True, exist_ok=True)
    path = _canvas_path(key)
    # 写临时文件再原子替换,避免并发写或写中途崩溃损坏快照。
    tmp_path = path.with_name(f".{key}.json.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    os.replace(tmp_path, path)

    # 惰性清理:过期快照 + 超量淘汰(刚保存的 mtime 最新,不会被误删)。
    cleanup_canvas_store()

    return {"key": key, "savedAt": saved_at}


@router.get("/display/load")
async def load_canvas(key: str = Query(..., description="画布标识,用作快照文件名")):
    """读取指定 key 的画布快照并原样回传。

    成功返回 ``{ key, canvas, savedAt }``(见 plan.md §3.6);不存在返回 404。
    ``canvas`` 为落盘时的原始内容,逐字段保真。
    """
    # ── 1. 校验 key(同样做路径穿越防护)─────────────────────────────
    _validate_key(key)

    path = _canvas_path(key)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"no saved canvas for key: {key}",
        )

    # ── 2. 原样读回,取信封层字段(canvas 原样透传)──────────────────
    body = json.loads(path.read_text(encoding="utf-8"))

    # 刷新访问时间(仅文件时间戳,不改内容与 savedAt),用于过期判定。
    try:
        os.utime(path)
    except OSError:
        pass

    return {
        "key": body.get("key", key),
        "canvas": body.get("canvas"),
        "savedAt": body.get("savedAt"),
    }
