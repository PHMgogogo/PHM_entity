"""统一管理对外部模块的访问地址。

本项目访问两类外部服务,分别部署在不同节点:

- **CSV 服务节点**:提供行式 SQL 查询(`display` 用)与列导出(`csv_export` 用),
  两者属同一服务节点。
- **算法服务节点**:提供模型训练 / 推理,与 CSV 服务并非同一节点。

两类服务的「主机:端口」与「路由路径」均集中在此处维护,部署时按实际环境
调整即可;各 router 引用下方导出的完整 endpoint,避免地址散落多处。
"""

# ── CSV 服务节点 ─────────────────────────────────────────────────────
# display 的行式 SQL 查询 与 csv_export 的列导出同属此节点。
CSV_HOST = "http://127.0.0.1:8001"  # 主机:端口
CSV_SQL_PATH = "/api/csv/sql"  # display: 行式 SQL 查询路由
CSV_EXPORT_PATH = "/api/csv/export-columns"  # csv_export: 列导出路由

# ── 算法服务节点(与 CSV 服务不同节点)──────────────────────────────
ALGO_HOST = "http://127.0.0.1:8002"  # 主机:端口
# 路由前缀;实际请求路径为 {ALGO_HOST}{ALGO_PATH}/{instance_id}/{train|infer}
ALGO_PATH = ""

# ── 完整 endpoint(供 router 直接引用)───────────────────────────────
SQL_ENDPOINT = f"{CSV_HOST}{CSV_SQL_PATH}"
CSV_UPSTREAM = f"{CSV_HOST}{CSV_EXPORT_PATH}"
ALGO_BASE = f"{ALGO_HOST}{ALGO_PATH}"
