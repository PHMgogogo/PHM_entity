# PHM Entity API 文档

FastAPI 后端服务,基于 SQLite 存储,提供对 `task` 实体的完整 CRUD 操作。

> 交互式文档(服务启动后可用):
> - Swagger UI: <http://127.0.0.1:8000/docs>
> - ReDoc: <http://127.0.0.1:8000/redoc>
> - OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

---

## 目录

- [通用约定](#通用约定)
  - [基础信息](#基础信息)
  - [请求与响应格式](#请求与响应格式)
  - [错误响应](#错误响应)
- [数据模型](#数据模型)
  - [Task 实体](#task-实体)
  - [请求体模型 TaskCreate](#请求体模型-taskcreate)
  - [更新模型 TaskUpdate](#更新模型-taskupdate)
  - [响应模型 TaskResponse](#响应模型-taskresponse)
- [接口列表](#接口列表)
- [接口详情](#接口详情)
  - [1. 健康检查](#1-健康检查)
  - [2. 创建 Task](#2-创建-task)
  - [3. 列出全部 Task](#3-列出全部-task)
  - [4. 获取单个 Task](#4-获取单个-task)
  - [5. 更新 Task](#5-更新-task)
  - [6. 删除 Task](#6-删除-task)
  - [7. 关键字搜索 Task](#7-关键字搜索-task)
  - [8. 按飞机查询 Task](#8-按飞机查询-task)
- [路由匹配顺序说明](#路由匹配顺序说明)

---

## 通用约定

### 基础信息

| 项目     | 值                              |
|----------|--------------------------------|
| Base URL | `http://127.0.0.1:8000`        |
| 鉴权     | 无                              |
| 请求格式 | `application/json`             |
| 响应格式 | `application/json` (UTF-8)     |
| 路由前缀 | 所有 Task 接口统一在 `/api/tasks` 下 |

### 请求与响应格式

- 除 `GET` 请求外,带有请求体的接口需在 Header 中声明 `Content-Type: application/json`。
- 所有响应体均为 JSON。
- 时间相关字段:当前模型未包含时间戳字段。

### 错误响应

错误统一以如下结构返回:

```json
{
    "detail": "<错误描述>"
}
```

常见状态码:

| 状态码 | 含义                 | 触发场景                                         |
|--------|--------------------|------------------------------------------------|
| 200    | OK                 | 请求成功(查询、更新、删除)                         |
| 201    | Created            | 资源创建成功                                     |
| 404    | Not Found          | 指定 `task_id` 的资源不存在                       |
| 422    | Unprocessable Entity | 请求体未通过 Pydantic 校验(类型错误、长度越界等) |
| 500    | Internal Server Error | 服务端内部异常(未预期的数据库或运行时错误)     |

#### 422 校验错误示例

当请求体未通过校验时,FastAPI 返回结构化的字段级错误信息:

```json
{
    "detail": [
        {
            "type": "string_too_short",
            "loc": ["body", "name"],
            "msg": "String should have at least 1 character",
            "input": ""
        }
    ]
}
```

---

## 数据模型

### Task 实体

对应数据库表 `tasks`。

| 字段           | Python 类型 | DB 列名     | 约束                                  | 说明                                       |
|----------------|------------|-------------|---------------------------------------|--------------------------------------------|
| `task_id`      | int        | `task_id`   | PRIMARY KEY, AUTOINCREMENT, INDEX     | 自增主键,由数据库维护                          |
| `name`         | str        | `name`      | VARCHAR(255), NOT NULL, INDEX | 任务短名称                                   |
| `description`  | str        | `description` | TEXT, NOT NULL, default `""`        | 长文本描述                                   |
| `session_id`   | str        | `session_id`  | VARCHAR(255), NOT NULL, default `""`| 会话标识                                     |
| `aircraft_id`  | str        | `aircraft_id` | VARCHAR(255), NOT NULL, default `""`| 飞机标识                                     |
| `instance_id`  | str        | `instance_id` | VARCHAR(255), NOT NULL, default `""`| 实例标识                                     |
| `work_dir`     | str        | `work_dir`    | TEXT, NOT NULL, default `""`        | 跨平台文件系统路径                          |
| `is_global`    | bool       | `global`      | BOOLEAN, NOT NULL, default `False`  | 是否为全局任务(**数据库列名为 `global`**) |
| `default`      | bool       | `default`     | BOOLEAN, NOT NULL, default `False`  | 是否为对应飞机的默认任务                     |

> 注:`is_global` 在 Python / API 层命名为 `is_global`,在数据库表中映射为列名 `global`(因 `global` 是 Python 关键字)。对外接口一律使用 `is_global`。

### 请求体模型 TaskCreate

用于 `POST /api/tasks/`。

| 字段          | 类型   | 必填 | 默认值   | 约束                      |
|---------------|--------|------|---------|---------------------------|
| `name`        | string | 是   | —       | 长度 1–255                |
| `description` | string | 否   | `""`    | 任意长度                   |
| `session_id`  | string | 否   | `""`    | 显式提供时长度 1–255       |
| `aircraft_id` | string | 否   | `""`    | 显式提供时长度 1–255       |
| `instance_id` | string | 否   | `""`    | 显式提供时长度 1–255       |
| `work_dir`    | string | 否   | `""`    | 任意长度                   |
| `is_global`   | boolean | 否   | `false` | —                         |
| `default`     | boolean | 否   | `false` | —                         |

> 说明:`session_id` / `aircraft_id` / `instance_id` 在 schema 中带 `default=""` 且 `min_length=1`。若**省略**该字段,使用默认值 `""`(不触发校验);若**显式传入**空字符串 `""`,则触发 `422`。

### 更新模型 TaskUpdate

用于 `PUT /api/tasks/{task_id}`,**所有字段均为可选**,仅传入的字段会被更新(使用 `exclude_unset`)。

| 字段          | 类型           | 说明                          |
|---------------|----------------|-------------------------------|
| `name`        | string \| null | 长度 1–255                     |
| `description` | string \| null | 长文本描述                     |
| `session_id`  | string \| null | 显式提供时长度 1–255           |
| `aircraft_id` | string \| null | 显式提供时长度 1–255           |
| `instance_id` | string \| null | 显式提供时长度 1–255           |
| `work_dir`    | string \| null | 跨平台文件系统路径             |
| `is_global`   | boolean \| null | 是否为全局任务               |
| `default`     | boolean \| null | 是否为默认任务               |

### 响应模型 TaskResponse

`GET` / `PUT` 类接口返回的完整任务对象,包含全部 9 个字段:

```json
{
    "task_id": 1,
    "name": "示例任务",
    "description": "这是一段长文本描述...",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo",
    "is_global": false,
    "default": false
}
```

---

## 接口列表

| # | 方法     | 路径                            | 说明                          | 成功状态码 |
|---|----------|---------------------------------|-------------------------------|-----------|
| 1 | `GET`    | `/`                             | 健康检查 / 根路由             | 200       |
| 2 | `POST`   | `/api/tasks/`                   | 创建 Task                     | 201       |
| 3 | `GET`    | `/api/tasks/`                   | 列出全部 Task                 | 200       |
| 4 | `GET`    | `/api/tasks/{task_id}`          | 获取单个 Task                 | 200       |
| 5 | `PUT`    | `/api/tasks/{task_id}`          | 更新 Task(部分更新)         | 200       |
| 6 | `DELETE` | `/api/tasks/{task_id}`          | 删除 Task                     | 200       |
| 7 | `GET`    | `/api/tasks/search`             | 关键字搜索(name/description) | 200       |
| 8 | `GET`    | `/api/tasks/aircraft/{aircraft_id}` | 按飞机查询 Task(含全局任务并集) | 200       |

---

## 接口详情

### 1. 健康检查

确认服务是否正常运行。

```http
GET /
```

**响应** (200 OK):
```json
{
    "message": "PHM Entity API is running"
}
```

---

### 2. 创建 Task

创建一条新的 task 记录。

```http
POST /api/tasks/
Content-Type: application/json

{
    "name": "示例任务",
    "description": "这是一段长文本描述...",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo",
    "is_global": false,
    "default": false
}
```

其中 `description`、`session_id`、`aircraft_id`、`instance_id`、`work_dir`、`is_global`、`default` 均可省略,使用默认值。

**成功响应** (201 Created) — 仅返回主键:
```json
{
    "task_id": 1
}
```

**错误响应**:

- `422` — `name` 为空 / 缺失,或 `name` 长度超过 255。

**curl 示例**:
```bash
curl -X POST http://127.0.0.1:8000/api/tasks/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "示例任务",
    "description": "这是一段长文本描述...",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo"
  }'
```

---

### 3. 列出全部 Task

返回数据库中所有 task,按主键顺序。

```http
GET /api/tasks/
```

**响应** (200 OK) — `TaskResponse` 数组:
```json
[
    {
        "task_id": 1,
        "name": "示例任务",
        "description": "这是一段长文本描述...",
        "session_id": "abc-123_xyz",
        "aircraft_id": "ac-001",
        "instance_id": "inst-001_abc",
        "work_dir": "/home/user/projects/demo",
        "is_global": false,
        "default": false
    }
]
```

> 无数据时返回空数组 `[]`。

---

### 4. 获取单个 Task

按主键获取单条 task。

```http
GET /api/tasks/1
```

**路径参数**:

| 参数       | 类型 | 说明           |
|------------|------|----------------|
| `task_id`  | int  | 任务主键,必填 |

**成功响应** (200 OK) — 单个 `TaskResponse`:
```json
{
    "task_id": 1,
    "name": "示例任务",
    "description": "这是一段长文本描述...",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo",
    "is_global": false,
    "default": false
}
```

**错误响应**:

- `404` — `{"detail": "Task with id 1 not found"}`
- `422` — `task_id` 不是整数。

---

### 5. 更新 Task

按主键更新 task,**仅更新请求体中提供的字段**(部分更新,`PATCH` 语义)。

```http
PUT /api/tasks/1
Content-Type: application/json

{
    "description": "更新后的描述",
    "is_global": true
}
```

**路径参数**:同 [获取单个 Task](#4-获取单个-task)。

**请求体**:`TaskUpdate`(所有字段可选,见 [更新模型 TaskUpdate](#更新模型-taskupdate))。

**成功响应** (200 OK) — 返回更新后的完整 `TaskResponse`:
```json
{
    "task_id": 1,
    "name": "示例任务",
    "description": "更新后的描述",
    "session_id": "abc-123_xyz",
    "aircraft_id": "ac-001",
    "instance_id": "inst-001_abc",
    "work_dir": "/home/user/projects/demo",
    "is_global": true,
    "default": false
}
```

**错误响应**:

- `404` — 指定 `task_id` 不存在。
- `422` — 字段校验失败(如显式传入空 `name`)。

**curl 示例**:
```bash
curl -X PUT http://127.0.0.1:8000/api/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{"description": "更新后的描述", "is_global": true}'
```

---

### 6. 删除 Task

按主键删除 task。

```http
DELETE /api/tasks/1
```

**路径参数**:同 [获取单个 Task](#4-获取单个-task)。

**成功响应** (200 OK):
```json
{
    "detail": "Task 1 deleted successfully"
}
```

**错误响应**:

- `404` — `{"detail": "Task with id 1 not found"}`
- `422` — `task_id` 不是整数。

---

### 7. 关键字搜索 Task

对 `name` 和 `description` 做大小写不敏感的模糊匹配(`ILIKE %keyword%`),返回命中记录。

```http
GET /api/tasks/search?keyword=示例
```

**查询参数**:

| 参数       | 类型   | 必填 | 约束         | 说明                          |
|------------|--------|------|--------------|-------------------------------|
| `keyword`  | string | 是   | 最少 1 个字符 | 在 name/description 中匹配的关键字 |

**成功响应** (200 OK) — `TaskResponse` 数组,结构与 [列出全部 Task](#3-列出全部-task) 一致。

> 无匹配结果时返回空数组 `[]`。

**curl 示例**:
```bash
curl "http://127.0.0.1:8000/api/tasks/search?keyword=示例"
```

---

### 8. 按飞机查询 Task

按 `aircraft_id` **精确匹配**,返回该飞机下的全部 task 与**所有 `is_global` 为 true 的 task** 的并集。响应体额外包含 `initialization_required` 字段:当请求的 `aircraft_id` 下**没有任何 task** 时为 `true`,否则为 `false`。注意:即使 `initialization_required` 为 `true`(该飞机无专属任务),返回的 `tasks` 也可能因全局任务而**非空**。

```http
GET /api/tasks/aircraft/ac-001
```

**路径参数**:

| 参数          | 类型   | 说明                |
|---------------|--------|---------------------|
| `aircraft_id` | string | 飞机标识,精确匹配   |

**成功响应** (200 OK) — 对象,包含 `initialization_required` 与 `tasks` 数组:

```json
{
    "initialization_required": false,
    "tasks": [
        {
            "task_id": 1,
            "name": "示例任务",
            "description": "这是一段长文本描述...",
            "session_id": "abc-123_xyz",
            "aircraft_id": "ac-001",
            "instance_id": "inst-001_abc",
            "work_dir": "/home/user/projects/demo",
            "is_global": false,
            "default": false
        }
    ]
}
```

| 字段                     | 类型             | 说明                                                                  |
|--------------------------|------------------|-----------------------------------------------------------------------|
| `initialization_required`| boolean          | 请求的 `aircraft_id` 下无任何 task 时为 `true`,否则 `false`           |
| `tasks`                  | `TaskResponse[]` | 该飞机专属任务与全部 `is_global=true` 任务的并集(按 `task_id` 去重)   |

> `tasks` 永远包含所有全局任务。当该飞机无专属任务、且系统中无任何全局任务时,`tasks` 才为空数组 `[]`(此时 `initialization_required` 为 `true`)。

**curl 示例**:
```bash
curl "http://127.0.0.1:8000/api/tasks/aircraft/ac-001"
```

---

## 路由匹配顺序说明

`/api/tasks` 下的路由存在静态路径(`/`、`/search`、`/aircraft/{aircraft_id}`)与动态路径(`/{task_id}`)。FastAPI 按**路由定义顺序**匹配,因此代码中 `/{task_id}` 被放在最后(见 [app/routers/tasks.py](../app/routers/tasks.py))。

> 若 `/{task_id}` 定义在前,`GET /api/tasks/search` 会被尝试解析为 `task_id="search"`,因 `task_id` 为 `int` 而返回 `422`。当前实现已规避此问题:静态路由优先,`/{task_id}` 兜底。
