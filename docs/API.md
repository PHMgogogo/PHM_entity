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
  - [9. 图表数据查询(展示代理)](#9-图表数据查询展示代理)
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
| 9 | `POST`   | `/api/display/raw-data`                       | 图表数据查询(展示代理)          | 200       |

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

### 9. 图表数据查询(展示代理)

根据 `data` / `columns` / `limit` / `type` 拼装 SQL,向外部 CSV 模块(`SQL_ENDPOINT`,见 `app.config`)发起查询,并按 `type` 将上游的行式返回值转换为前端约定的系列式图表数据后返回。本接口为透传代理,不直接读写本地数据库。

> 前端约定的输出结构见下方 [响应模型](#响应模型-displayresponse)。`type` 仅决定后端的列数约束与转换规则,前端按各自图表类型渲染。

```http
POST /api/display/raw-data
Content-Type: application/json

{
    "data": "多维数据",
    "columns": ["AGE", "RANGE"],
    "limit": 10,
    "type": "MAPPING_2D"
}
```

#### 请求参数

| 字段       | 类型            | 必填 | 默认值 | 说明                                                              |
|------------|-----------------|------|--------|-------------------------------------------------------------------|
| `data`     | string          | 是   | —      | 数据来源标识,对应 SQL 中的 `csv_{data}` 表名部分                  |
| `columns`  | Array[string]   | 是   | —      | 参与展示的列名列表,列数须与 `type` 约定一致;将转大写后拼入 SELECT |
| `limit`    | integer         | 否   | `0`    | 返回数据点数量上限;`0` 表示不限制(不生成 LIMIT 子句)            |
| `type`     | string(枚举)   | 是   | —      | 图表类型,见 [type 枚举](#type-枚举)                              |

##### type 枚举

| 值                     | 说明             | 列数约束 | 轴列(共用)         | parameter(每列一系) | dimensions 长度 |
|------------------------|------------------|----------|---------------------|----------------------|-----------------|
| `SINGLE_TIMESERIES_2D` | 二维单参数时序图 | 恰好 2   | `columns[0]`(时间) | `[columns[1]]`       | 2               |
| `MULTI_TIMESERIES_2D`  | 二维多参数时序图 | ≥ 3      | `columns[0]`(时间) | `columns[1:]`        | 2               |
| `MAPPING_2D`           | 二维双参数映射图 | 恰好 2   | `columns[0]`(x)     | `[columns[1]]`       | 2               |
| `POINT_CLOUD_3D`       | 三维点云图       | 恰好 3   | `columns[0], columns[1]`(x,y) | `[columns[2]]` | 3               |

> 各类型的数据点构造见 [转换规则](#转换规则)。时序类型(`SINGLE_TIMESERIES_2D` / `MULTI_TIMESERIES_2D`)的首轴 `unit` 固定为 `"time"`,其余维度 `unit` 默认空串。

#### 成功响应 (200 OK)

```json
{
    "dimensions": [
        { "name": "AGE", "unit": "" },
        { "name": "RANGE", "unit": "" }
    ],
    "parameter": ["RANGE"],
    "data": [
        {
            "parameter": "RANGE",
            "data": [
                [3.708842, 19.6118242],
                [1.712816, 19.6118242],
                [0.907223, 19.46265851]
            ]
        }
    ]
}
```

> `color` 为可选字段,值为 `null` 时不出现在响应中。数据点中的字符串数值(如 `"3.708842"`)会被转为数值类型;时间标签、标识等非数值列保持字符串。

#### 响应模型 DisplayResponse

| 字段          | 类型                  | 必填 | 说明                                                        |
|---------------|-----------------------|------|-------------------------------------------------------------|
| `dimensions`  | Array[DimensionObject]| 是   | 图表维度定义,长度决定坐标轴数量(1/2/3)                    |
| `parameter`   | Array[string]         | 是   | 参数名称列表,每个元素对应 `data` 中一个数据系列            |
| `data`        | Array[SeriesObject]   | 是   | 数据系列集合,长度与 `parameter` 列表一致                   |

**DimensionObject**

| 字段   | 类型   | 必填 | 默认值 | 说明                                          |
|--------|--------|------|--------|-----------------------------------------------|
| `name` | string | 是   | —      | 维度名称,取自查询结果的列名                  |
| `unit` | string | 是   | `""`   | 数据单位;时序轴为 `time`,其余默认空串        |

**SeriesObject**

| 字段        | 类型            | 必填 | 说明                                                          |
|-------------|-----------------|------|---------------------------------------------------------------|
| `parameter` | string          | 是   | 参数名称,与 `parameter` 列表中的元素对应                      |
| `color`     | string          | 否   | 系列颜色(如 `#FF0000`),由前端分配;为空时不输出             |
| `data`      | Array[Array]    | 是   | 数据点集合;每个内层数组的元素顺序与 `dimensions` 一致        |

#### 转换规则

上游 CSV 模块返回行式结构(`{success, data:[{col:val}], columns, totalRows}`),后端按 `type` 转换为系列式结构。每个系列的数据点 = `[各轴列的行值..., 该参数的行值]`,元素顺序与 `dimensions` 一致:

- **SINGLE_TIMESERIES_2D**:`axis=[col0]`, `params=[col1]` → 单系列,点 `[t, v]`
- **MULTI_TIMESERIES_2D**:`axis=[col0]`, `params=col1...` → 多系列,各点 `[t, v_i]`;`dimensions` 仅取 `[col0, col1]` 前两列
- **MAPPING_2D**:`axis=[col0]`, `params=[col1]` → 单系列,点 `[x, y]`
- **POINT_CLOUD_3D**:`axis=[col0, col1]`, `params=[col2]` → 单系列,点 `[x, y, z]`

> MULTI 类型的 `dimensions` 只取前两列(时间 + 首参数):前端画二维图,多参数共享同一时间 x 轴,各参数一条 y 曲线。

##### MULTI_TIMESERIES_2D 示例

请求 `columns = ["Time", "Temperature", "Humidity"]`,`type = "MULTI_TIMESERIES_2D"`:

```json
{
    "dimensions": [
        { "name": "Time", "unit": "time" },
        { "name": "Temperature", "unit": "" }
    ],
    "parameter": ["Temperature", "Humidity"],
    "data": [
        {
            "parameter": "Temperature",
            "data": [["11:30", 100], ["12:00", 110], ["13:00", 115]]
        },
        {
            "parameter": "Humidity",
            "data": [["11:30", 45], ["12:00", 48], ["13:00", 46]]
        }
    ]
}
```

#### 错误响应

除通用的 `422`(请求体校验失败)外,本接口额外可能返回:

| 状态码 | 触发场景                                                                |
|--------|-------------------------------------------------------------------------|
| `422`  | `columns` 列数与 `type` 约定不符(见 [type 枚举](#type-枚举))          |
| `502`  | 无法连接外部 CSV 模块、上游返回非 2xx、或上游 `success: false`          |
| `504`  | 外部 CSV 模块请求超时                                                    |

#### curl 示例

```bash
curl -X POST http://127.0.0.1:8000/api/display/raw-data \
  -H "Content-Type: application/json" \
  -d '{
    "data": "多维数据",
    "columns": ["AGE", "RANGE"],
    "limit": 10,
    "type": "MAPPING_2D"
  }'
```

---

## 路由匹配顺序说明

`/api/tasks` 下的路由存在静态路径(`/`、`/search`、`/aircraft/{aircraft_id}`)与动态路径(`/{task_id}`)。FastAPI 按**路由定义顺序**匹配,因此代码中 `/{task_id}` 被放在最后(见 [app/routers/tasks.py](../app/routers/tasks.py))。

> 若 `/{task_id}` 定义在前,`GET /api/tasks/search` 会被尝试解析为 `task_id="search"`,因 `task_id` 为 `int` 而返回 `422`。当前实现已规避此问题:静态路由优先,`/{task_id}` 兜底。
