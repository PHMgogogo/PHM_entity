# PHM Entity API

FastAPI 后端服务,使用 SQLite 数据库,提供对 `task` 实体的完整增删改查(CRUD)操作。

> 📖 完整接口文档见 [docs/API.md](docs/API.md)。服务启动后也可访问自动生成的交互式文档:
> - Swagger UI: <http://127.0.0.1:8000/docs>
> - ReDoc: <http://127.0.0.1:8000/redoc>

## 项目结构

```
PHM_entity/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI 入口,应用启动 & 路由注册
│   ├── database.py        # SQLite 数据库连接与会话管理
│   ├── models.py          # SQLAlchemy ORM 模型 (Task)
│   ├── schemas.py         # Pydantic 请求/响应模型
│   ├── crud.py            # 数据库 CRUD 操作
│   └── routers/
│       ├── __init__.py
│       └── tasks.py       # Task 路由(接口定义)
├── docs/
│   └── API.md             # API 接口文档
├── requirements.txt
└── README.md
```

## 环境要求

- Python 3.10+
- pip

## 安装与运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务(默认端口 8000)
uvicorn app.main:app --reload

# 启动后访问:
# - Swagger 文档: http://127.0.0.1:8000/docs
# - ReDoc 文档:   http://127.0.0.1:8000/redoc
```

数据库文件 `phm_entity.db` 会在首次启动时自动创建在项目根目录。

## Task 实体属性

对应数据库表 `tasks`。

| 属性           | 类型    | 约束                                    | 说明                                       |
|----------------|---------|-----------------------------------------|--------------------------------------------|
| `task_id`      | INTEGER | PRIMARY KEY, AUTOINCREMENT              | ORM 维护的自增主键                          |
| `name`         | VARCHAR | NOT NULL, 长度 1–255                    | 短文本名称                                  |
| `description`  | TEXT    | NOT NULL                                | 长文本描述                                  |
| `session_id`   | VARCHAR | NOT NULL                                | 由字母、数字、`-`、`_` 连接的字符串         |
| `aircraft_id`  | VARCHAR | NOT NULL                                | 飞机标识,约束同 session_id                 |
| `instance_id`  | VARCHAR | NOT NULL                                | 实例标识,约束同 session_id                 |
| `model_code`   | VARCHAR | NOT NULL, default `""`                  | 机型                                        |
| `work_dir`     | TEXT    | NOT NULL                                | 跨平台文件系统路径                          |
| `is_global`    | BOOLEAN | NOT NULL, default false                 | 是否为全局任务(数据库列名为 `global`)     |

> 注:`is_global` 在 API 层命名为 `is_global`,在数据库表中映射为列名 `global`(因 `global` 是 Python 关键字)。对外接口一律使用 `is_global`。

## API 接口

所有 Task 接口统一在 `/api/tasks` 前缀下。完整字段说明、错误码、curl 示例见 [docs/API.md](docs/API.md)。

| 方法     | 路径                                 | 说明                            | 成功状态码 |
|----------|--------------------------------------|---------------------------------|-----------|
| `GET`    | `/`                                  | 健康检查                        | 200       |
| `POST`   | `/api/tasks/`                        | 创建 Task                       | 201       |
| `GET`    | `/api/tasks/`                        | 列出全部 Task                   | 200       |
| `GET`    | `/api/tasks/{task_id}`               | 获取单个 Task                   | 200       |
| `PUT`    | `/api/tasks/{task_id}`               | 更新 Task(部分更新)           | 200       |
| `DELETE` | `/api/tasks/{task_id}`               | 删除 Task                       | 200       |
| `GET`    | `/api/tasks/search?keyword=`         | 关键字搜索(name/description)   | 200       |
| `GET`    | `/api/tasks/aircraft/{aircraft_id}`  | 按飞机查询 Task(含全局任务并集) | 200       |

### 快速示例

**创建 Task**
```http
POST /api/tasks/
Content-Type: application/json

{
    "name": "示例任务",
    "description": "这是一段长文本描述...",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo"
}
```
响应 (201 Created):
```json
{ "task_id": 1 }
```

**查询 Task 列表**
```http
GET /api/tasks/
```
响应 (200 OK):
```json
[
    {
        "task_id": 1,
        "name": "示例任务",
        "description": "这是一段长文本描述...",
        "session_id": "abc-123_xyz",
        "aircraft_id": "ac-001",
        "instance_id": "inst-001_abc",
        "model_code": "C919",
        "work_dir": "/home/user/projects/demo",
        "is_global": false
    }
]
```

**更新 Task**(仅更新提供的字段)
```http
PUT /api/tasks/1
Content-Type: application/json

{ "description": "更新后的描述", "is_global": true }
```

**删除 Task**
```http
DELETE /api/tasks/1
```
成功响应 (200 OK):
```json
{ "detail": "Task 1 deleted successfully" }
```
失败响应 (404 Not Found):
```json
{ "detail": "Task with id 1 not found" }
```

**关键字筛选**(大小写不敏感,匹配 name 或 description)
```http
GET /api/tasks/search?keyword=示例
```
> 无匹配结果返回空列表 `[]`。

## 技术栈

- **Web 框架**: FastAPI
- **ORM**: SQLAlchemy 2.0
- **数据校验**: Pydantic v2
- **数据库**: SQLite
- **ASGI 服务器**: Uvicorn
