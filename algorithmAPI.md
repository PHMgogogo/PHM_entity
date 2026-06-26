# API 接口文档

Base URL: `http://<host>:<port>`

---

## 1. POST /train

启动模型训练任务。

### Request Body (JSON)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `dataset` | `DatasetRequest` | ✅ | — | 训练数据集配置 |
| `args` | `TrainArgs` | ✅ | — | 训练参数 |
| `detach` | `bool` | ❌ | `false` | 是否异步执行（`true` 立即返回 `[]`，训练在后台运行） |

#### DatasetRequest

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `content_type` | `"path_csv"` \| `"json_csv"` \| `"text_csv"` | ✅ | — | 数据内容类型 |
| `content` | `str` \| `JsonCSV` \| `str` | ✅ | — | 视 `content_type` 而定（见下方说明） |
| `data_cols` | `list[str]` | ✅ | — | 作为模型输入的列名 |
| `label_cols` | `list[str]` \| `null` | ❌ | `null` | 作为标签的列名；为 `null` 时标签等于输入数据 |

**`content_type` 与 `content` 说明：**

| content_type | content 格式 | 说明 |
|---|---|---|
| `"path_csv"` | `"./data.csv"` | CSV 文件路径（服务端可访问） |
| `"json_csv"` | `{"rows": [[col1, col2, ...], ...]}` | JSON 二维数组，自动写入临时 CSV |
| `"text_csv"` | `"col1,col2\n1,2\n3,4"` | CSV 文本字符串，自动写入临时文件 |

#### TrainArgs

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `epoch` | `int` | ❌ | `1` | 训练轮数 |
| `batch_size` | `int` | ❌ | `1` | 批次大小 |
| `learning_rate` | `float` | ❌ | `1e-3` | 学习率 |
| `device` | `"cpu"` \| `"cuda"` \| `str` | ❌ | `"cpu"` | 计算设备 |
| `progress` | `bool` | ❌ | `false` | 是否输出进度日志 |
| `shuffle` | `bool` | ❌ | `true` | 是否打乱数据 |

### Response `200 OK`

```json
[
  {
    "loss": 0.023,
    "outputs": [[0.12], [0.34], [0.56]],
    "ids": [0, 1, 2]
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `loss` | `float` | 该 epoch 的平均损失 |
| `outputs` | `list[list[float]]` | 每个样本的模型输出 |
| `ids` | `list[int]` | 对应样本在数据集中的索引 |

- 每个 epoch 产生一个 `ModelResult` 元素，共 `epoch` 个
- `detach: true` 时立即返回 `[]`，训练结果通过 `/state` 轮询获取

### 错误响应

| 状态码 | 内容 | 说明 |
|--------|------|------|
| `500` | `{"detail": "Cannot start training from state ...", "type": "RuntimeError"}` | 模型未加载（处于 UNLOADED / TRAINING / INFERRING 状态） |

### 示例

```bash
curl -X POST "http://localhost:8000/train" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": {
      "content_type": "path_csv",
      "content": "./train_data.csv",
      "data_cols": ["x"],
      "label_cols": ["y"]
    },
    "args": {
      "epoch": 10,
      "batch_size": 4,
      "learning_rate": 0.001,
      "device": "cpu"
    },
    "detach": false
  }'
```

---

## 2. POST /infer

执行模型推理（评估）任务。

### Request Body (JSON)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `dataset` | `DatasetRequest` | ✅ | — | 推理数据集配置（同 `/train`） |
| `args` | `EvalArgs` | ❌ | `{}` | 推理参数 |
| `detach` | `bool` | ❌ | `false` | 是否异步执行（`true` 立即返回 `[]`，推理在后台运行） |

#### EvalArgs

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `batch_size` | `int` | ❌ | `1` | 批次大小 |
| `device` | `"cpu"` \| `"cuda"` \| `str` | ❌ | `"cpu"` | 计算设备 |
| `progress` | `bool` | ❌ | `false` | 是否输出进度日志 |
| `shuffle` | `bool` | ❌ | `false` | 是否打乱数据（推理时不建议打乱） |

### Response `200 OK`

```json
[
  {
    "loss": 0.015,
    "outputs": [[0.98], [1.02], [2.15]],
    "ids": [0, 1, 2]
  }
]
```

> 推理固定执行 1 个 epoch，返回单元素数组。

### 示例

```bash
curl -X POST "http://localhost:8000/infer" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": {
      "content_type": "text_csv",
      "content": "x\n0.5\n1.0\n1.5",
      "data_cols": ["x"]
    },
    "args": {
      "batch_size": 2,
      "device": "cpu"
    }
  }'
```

---

## 3. 辅助接口

### GET /

返回内置的前端页面 `index.html`。

### POST /save

保存当前模型。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | `str` \| `null` | ❌ | `"./model.pth"` | 保存路径 |

```bash
curl -X POST "http://localhost:8000/save" \
  -H "Content-Type: application/json" \
  -d '{"path": "./my_model.pth"}'
```

### POST /load

加载模型。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | `str` \| `null` | ❌ | `null`（随机初始化） | 模型权重文件路径 |

```bash
curl -X POST "http://localhost:8000/load" \
  -H "Content-Type: application/json" \
  -d '{"path": "./my_model.pth"}'
```

### POST /unload

卸载模型并释放 GPU 显存。

```bash
curl -X POST "http://localhost:8000/unload"
```

### GET /state/{n}

查询当前状态及最近 n 条结果。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `n` | `int` (路径参数) | `1` | 返回最近 n 条 `ModelResult` |

```json
{
  "state": "TRAINING",
  "epoch_progress": {"n": 3, "total": 10, "elapsed": 1.5, "rate": 2.0, ...},
  "batch_progress": {"n": 16, "total": 100, ...},
  "result": [{"loss": 0.023, "outputs": [[...]], "ids": [...]}]
}
```

**`state` 可能的值：** `UNLOADED` | `LOADED` | `TRAINING` | `INFERRING`

### GET /wait

阻塞等待当前异步任务（train/infer 以 `detach: true` 启动的任务）完成。

```bash
curl "http://localhost:8000/wait"
```

### GET /stop

中断正在运行的训练或推理任务。

```bash
curl "http://localhost:8000/stop"
```

---

## 4. 状态机

```
UNLOADED ──load()──▶ LOADED ──train()──▶ TRAINING ──完成/stop──▶ LOADED
                        │                                        │
                        └──infer()──▶ INFERRING ──完成/stop──▶ LOADED
                        │
                        └──unload()──▶ UNLOADED
```

- 只能在 **LOADED** 状态下调用 `/train` 或 `/infer`
- 训练/推理期间可通过 `/stop` 中断
- 中断后状态回到 **LOADED**，可再次启动任务
