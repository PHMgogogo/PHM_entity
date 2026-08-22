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
ALGO_HOST = "http://127.0.0.1:8001"  # 主机:端口
# 路由前缀;实际请求路径为 {ALGO_HOST}{ALGO_PATH}/{instance_id}/{train|infer}
ALGO_PATH = ""

# ── 完整 endpoint(供 router 直接引用)───────────────────────────────
SQL_ENDPOINT = f"{CSV_HOST}{CSV_SQL_PATH}"
CSV_UPSTREAM = f"{CSV_HOST}{CSV_EXPORT_PATH}"
ALGO_BASE = f"{ALGO_HOST}{ALGO_PATH}"

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
