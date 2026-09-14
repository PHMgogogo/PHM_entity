"""OpenCode 服务客户端:用于删除失效任务残留的会话。"""
import httpx

from app.config import OPENCODE_BASE, OPENCODE_PASSWORD, OPENCODE_USER

# 进程级共享客户端(同 instance_client)。
_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    trust_env=False,
)


def _auth() -> httpx.BasicAuth | None:
    """OpenCode(v2) 使用 HTTP Basic 认证;未配置密码时不做认证。"""
    if not OPENCODE_PASSWORD:
        return None
    return httpx.BasicAuth(OPENCODE_USER, OPENCODE_PASSWORD)


async def delete_session(session_id: str, work_dir: str | None = None) -> bool:
    """删除指定的 OpenCode 会话(best-effort)。

    opencode v2 通过 ``location[directory]`` 查询参数指明会话所属工作目录
    (旧版的 ``x-opencode-directory`` 请求头已失效),路由前缀为 ``/api``。
    删除成功返回 True;会话不存在(404)或服务不可达等异常均返回 False,
    不抛出——对账流程不应因会话清理失败而中断。
    """
    url = f"{OPENCODE_BASE}/api/session/{session_id}"
    params = {"location[directory]": work_dir or ""}
    try:
        resp = await _client.delete(url, params=params, auth=_auth())
    except httpx.HTTPError as e:
        print(f"[reconcile] delete opencode session {session_id} failed: {e}")
        return False

    if resp.status_code == 404:
        return False
    if resp.is_success:
        return True
    print(
        f"[reconcile] delete opencode session {session_id} "
        f"returned {resp.status_code}"
    )
    return False
