"""实例服务客户端:提供任务对账所需的「存活实例集合」查询。"""
import httpx

from app.config import INSTANCE_LIST_ENDPOINT

# 进程级共享客户端:复用连接池 + keep-alive。目标为 LAN http 地址,
# trust_env=False 避免走代理 / 读系统证书库(与 display.py 中的做法一致)。
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    trust_env=False,
)


async def fetch_alive_instance_ids() -> set[str] | None:
    """查询实例服务当前全部实例的标识集合。

    返回实例标识集合;若服务不可达或返回异常,返回 ``None``(表示对账不可用,
    调用方须降级为「不清理」以免误删任务)。
    """
    try:
        resp = await _client.get(INSTANCE_LIST_ENDPOINT)
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        print(f"[reconcile] instance list unavailable: {e}")
        return None

    if not isinstance(payload, list):
        print(f"[reconcile] unexpected instance list payload: {type(payload)}")
        return None

    # 列表项中实例标识字段名为 ``id``(非 ``instance_id``)。
    ids: set[str] = set()
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.add(item["id"])
    return ids
