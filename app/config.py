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
CSV_TIMESERIES_PATH = "/api/csv/query-timeseries"  # 时序数据统一查询路由

# ── 算法服务节点(与 CSV 服务不同节点)──────────────────────────────
ALGO_HOST = "http://127.0.0.1:8001"  # 主机:端口
# 路由前缀;实际请求路径为 {ALGO_HOST}{ALGO_PATH}/{instance_id}/{train|infer}
ALGO_PATH = ""

# ── 完整 endpoint(供 router 直接引用)───────────────────────────────
SQL_ENDPOINT = f"{CSV_HOST}{CSV_SQL_PATH}"
CSV_UPSTREAM = f"{CSV_HOST}{CSV_EXPORT_PATH}"
CSV_TIMESERIES_ENDPOINT = f"{CSV_HOST}{CSV_TIMESERIES_PATH}"
ALGO_BASE = f"{ALGO_HOST}{ALGO_PATH}"

# ── 实例服务节点(判定 instance_id 是否存活)───────────────────────
# 任务对账(reconcile)以此服务返回的实例列表为准:实例仍在列表中(任意 status)
# 即视为存活,否则该任务视为失效并清理。注意返回列表项的实例标识字段名为
# ``id``(非 ``instance_id``)。
INSTANCE_HOST = "http://127.0.0.1:8001"  # 主机:端口
INSTANCE_LIST_PATH = "/api/pmgr/instances"  # 列出当前全部实例的实例标识

# ── OpenCode 服务(删除失效任务残留的 session)──────────────────────
# 失效任务若带有 session_id,对账时先尽力删除其 OpenCode 会话,再删本地记录。
# OpenCode 不直连其原生端口(4096),而是经网关代理访问:网关按 PREFIX 规则
# 把 ``/opencode`` 转发到 ``127.0.0.1:4096``(见
# algo/algorithms/opencode/.instance.info.json 的 rules)。因此与 CSV / 实例
# 服务一样,统一以网关为入口。
OPENCODE_HOST = "http://127.0.0.1:8001"  # 网关主机:端口
OPENCODE_PATH = "/opencode"  # 网关上的 OpenCode 路由前缀
# OpenCode(v2) 认证:opencode2 serve 不提供 --password 参数,服务端密码经环境变量
# OPENCODE_PASSWORD 指定(见 algo/algorithms/opencode/start.bash),用户名固定为
# opencode,认证方式为 HTTP Basic。若服务端未设置密码(每次启动随机生成),请将
# 下方 OPENCODE_PASSWORD 置空。
OPENCODE_USER = "opencode"
OPENCODE_PASSWORD = "phm-opencode-2024"

# ── 完整 endpoint(供 service 直接引用)─────────────────────────────
INSTANCE_LIST_ENDPOINT = f"{INSTANCE_HOST}{INSTANCE_LIST_PATH}"
OPENCODE_BASE = f"{OPENCODE_HOST}{OPENCODE_PATH}"

# ── 本地文件存储(display 画布快照)──────────────────────────────────
# 数据展示页画布状态的持久化目录:POST /api/display/save 把前端发来的完整
# 画布快照以 JSON 文件落盘至此(每个 key 一份,覆盖写);GET /api/display/load
# 按 <key>.json 读取。相对路径基于进程工作目录(与 phm_entity.db 同级)。
DISPLAY_CANVAS_DIR = "data/display_canvases"
# 画布快照保留策略(惰性清理,见 app.routers.display.cleanup_canvas_store):
#   TTL :最后访问(save/load)距今超过此秒数即视为过期并删除;
#   MAX :目录内快照数超过此值时,按最久未访问优先淘汰。
DISPLAY_CANVAS_TTL_SECONDS = 30 * 24 * 3600  # 30 天
DISPLAY_CANVAS_MAX_COUNT = 100

# ── 本地模型文件存储(analysis_model 上传)──────────────────────────
# 模型文件的物理存储根目录(相对进程工作目录);数据库 path 字段存逻辑路径
# ``analysis_models/instance_id/<model_id>/<filename>``,物理位置即
# ``{ANALYSIS_MODELS_DIR}/instance_id/<model_id>/<filename>``。
ANALYSIS_MODELS_DIR = "data/analysis_models"

# ── 本地分析结果存储(analysis_result)──────────────────────────────
# 结果 CSV 的物理存储根目录(相对进程工作目录);数据库 csv_path 字段存逻辑
# 路径 ``analysis_results/instance_id/<result_id>/<filename>``,物理位置即
# ``{ANALYSIS_RESULTS_DIR}/instance_id/<result_id>/<filename>``。
ANALYSIS_RESULTS_DIR = "data/analysis_results"
