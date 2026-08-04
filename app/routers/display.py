import json
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from app.config import SQL_ENDPOINT

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

    data: str = Field(..., description="数据来源标识,对应 SQL 中的 csv_{data} 表名部分")
    columns: list[str] = Field(
        ...,
        description="参与展示的列名列表,列数须与 type 约定一致;将转大写后拼入 SELECT",
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

    SQL 形如:`SELECT uppercase{columns} FROM csv_{data} [LIMIT {limit}]`
    转换规则见 `_transform`。
    """
    # ── 1. 校验列数 ──────────────────────────────────────────────────
    _validate_columns(req.type, len(req.columns))

    # ── 2. 拼装 SQL ──────────────────────────────────────────────────
    columns_sql = ", ".join(c.upper() for c in req.columns)
    sql = f"SELECT {columns_sql} FROM csv_{req.data}"
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
    cols: list[str] = [c.upper() for c in req.columns]

    # ── 5. 行式 → 系列式转换 ───────────────────────────────────────
    result = _transform(req.type, cols, rows)
    return result
