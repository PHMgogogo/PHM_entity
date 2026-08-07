# 数据展示画布持久化 · 后端接口契约 v1

> 本文档是交给**后端开发**的接口契约。前端等后端完成后接入。核心是「前端要什么数据」。
> 前端只读不改后端代码；后端实现完成后，前端按本契约在 `src/api/display.ts` 增加两个调用、在 `MonitorView.vue` 加「保存/加载」按钮即可联调。

---

## 0. 背景与目标

- **现状**：数据展示页（`MonitorView.vue`）的所有图表只活在内存里（`DashboardContainer` 的 `layout` ref）。刷新页面 / 离开路由即全部销毁、不可恢复（见 `REVIEW/REVIEW.md:342`）。
- **目标**：把「当前画布的完整状态」序列化成一份 JSON 发给后端，后端落盘成文件；下次进入页面时取回 JSON 原样还原画布。
- **本期范围（已与产品确认）**：
  1. **单份快照**：每个 `key` 只保留一份，保存即覆盖（不做多份命名仪表盘）。
  2. **快照式恢复**：JSON 里直接带每张图完整的 ECharts `option`（含数值数据），加载时前端**直接渲染**，不重新查询。后端无需关心数据时效。
  3. **手动保存**：用户点「保存」按钮触发；不做自动保存。

---

## 1. 关键约定: 后端是「不透明存储（opaque blob store）」——禁止解析/改写画布内容

画布里的 `option` 是**完整的 ECharts 配置对象**，schema 庞大、随版本演进、还含函数式 formatter 字符串等。`config` 是前端表单快照，字段会随迭代增减。

- 后端**只需把 `canvas` 字段原样存、原样取**（逐字段保真：不重命名、不删空值、不强转数字、不重排、不「修正」结构）。
- 后端**不得**对 `option` / `config` / `layout` 做任何业务校验或字段裁剪。任何改动都会导致前端渲染异常。
- 后端只拥有**信封层**（`key`、`savedAt`、可选 `version`），其余当作黑盒字节流。


---

## 2. 接口清单

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/display/save` | 保存（覆盖）当前画布快照 |
| `GET`  | `/api/display/load?key=<key>` | 读取指定 key 的快照；不存在返回 **404** |

> Content-Type 统一 `application/json`（前端 `client.post` 会自动设置）。

---

## 3. 数据结构（核心：前端要什么数据）

### 3.1 `POST /api/display/save` 请求体（= 落盘内容）

整体即「存储信封」。后端**按原样持久化整个请求体**，加载时再把 `canvas` 原样回传。

```jsonc
{
  "key": "default",                 // string，画布标识。见 §5（前端给定，后端按不透明字符串处理）
  "canvas": {                       // ★ 不透明 blob，后端原样存取
    "version": 1,                   // 前端自定义的快照格式版本号，便于以后升级做兼容
    "config": { /* 画布级配置，见 3.2 */ },
    "layout": [ /* 图表项数组，每项 = 一张图，见 3.3 */ ]
  },
  "timestamp": "2026-08-06T10:00:00.000Z"  // string(ISO8601)，前端生成的保存时刻
}
```

**`POST /api/display/save` 成功响应（200）：**
```jsonc
{ "key": "default", "savedAt": "2026-08-06T10:00:01.000Z" }  // savedAt 为服务端落盘时刻
```

### 3.2 `canvas.config` —— 画布级配置

来自 `MonitorView.vue` 的 `dashboardConfig`（栅格/尺寸预设）。后端不透明存取即可。示例字段：

```jsonc
{
  "chartTypes": [ { "value": "SINGLE_TIMESERIES_2D", "label": "单参数时序" } /* ... */ ],
  "sizes": [
    { "value": "small",  "label": "小", "w": 3, "h": 10 },
    { "value": "medium", "label": "中", "w": 6, "h": 10 },
    { "value": "large",  "label": "大", "w": 9, "h": 10 }
  ],
  "layout": { "cols": 12, "totalRows": 30, "margin": [12, 12], "containerPadding": [16, 16] }
}
```

### 3.3 `canvas.layout[]` —— 单张图表项

每个元素结构（对应 `DashboardContainer` 的 layout item，字段名固定）：

```jsonc
{
  "i": "lq3a2f-abc",                // string，图表唯一 id（前端 generateId() 生成，全局唯一）
  "x": 0, "y": 0,                   // number，栅格坐标
  "w": 6, "h": 10,                  // number，栅格尺寸
  "type": "display",                // string，固定 "display"
  "category": "",                   // string，预留分类，当前空串
  "title": "温度",                  // string，图表标题
  "static": false,                  // boolean，是否锁定
  "config": { /* 该图表查询配置快照，见 3.4 — 不透明 */ },
  "option": { /* 完整 ECharts option，见 3.5 — 不透明，体积大 */ }
}
```

> 还原时前端按 `i` 作为组件 key、用 `option` 直接 `setOption` 渲染、用 `config` 回填右侧编辑面板。三项缺一会影响还原体验。

### 3.4 `item.config` —— 该图表的查询配置快照（不透明）

字段会随迭代变化，后端不要绑定具体字段。当前示例内容：

```jsonc
{
  "data": "flight_001",             // 数据源标识
  "columns": ["time", "temperature"],
  "limit": 0,
  "type": "SINGLE_TIMESERIES_2D",
  "size": "medium",
  "style": "LINE",
  "title": "温度",
  "aircraftNumber": "...", "sortieId": "...",
  "mappingId": "...", "csvTableName": "...",
  "columnCandidates": [ /* ... */ ],
  "x": "time", "y": "temperature", "yMulti": [], "z": null,
  "keepSize": false
}
```

### 3.5 `item.option` —— 完整 ECharts option（不透明，体积大）

含已嵌入的数值数据（`series[].data` 是具体数值数组，**不再需要重新查询**）。后端不要解析。简化的真实示例：

```jsonc
{
  "tooltip": { "trigger": "axis" },
  "legend":  { "show": false },
  "grid":    { /* ... */ },
  "xAxis": { "type": "category", "data": ["00:00", "00:01", "00:02"] },
  "yAxis": { "type": "value" },
  "series": [
    { "name": "temperature", "type": "line", "data": [36.5, 36.6, 36.7], "lineStyle": { "width": 2 } }
  ],
  "color": ["#5470c6", "#91cc75"]
}
```

### 3.6 `GET /api/display/load?key=<key>` 响应

**存在（200）：** 把保存时的 `canvas` **原样**回传：
```jsonc
{
  "key": "default",
  "canvas": { "version": 1, "config": { /* ... */ }, "layout": [ /* ... */ ] },
  "savedAt": "2026-08-06T10:00:01.000Z"
}
```

**不存在（404）：**
```jsonc
{ "detail": "no saved canvas for key: default" }
```
> 前端把 404 视作「无已保存画布」，正常提示、不报错。

---

## 4. 后端实现要求（NFR）

1. **不透明保真**：`canvas` 必须逐字段原样存取（见 §1.2）。这是最高优先级硬约束。
2. **落盘**：存为本地 JSON 文件，例如 `<存储目录>/<safe(key)>.json`。
3. **路径安全**：`key` 来自客户端，**必须做路径穿越防护**（拒绝 `/`、`..`、空字符串等；建议白名单字符 `[A-Za-z0-9_-]`，限长如 ≤64）。非法 `key` → 400。
4. **覆盖语义**：同 `key` 再次 `save` 即覆盖（last-write-wins，不做合并）。
5. **体积上限**：一张画布多图 + 内嵌数值时可达 **数百 KB ~ 数 MB**。请允许至少 **10 MB** 请求体，不要用默认的小 body 限制截断。
6. **错误格式**：沿用 FastAPI 风格 `HTTP status + { "detail": string }`（前端 `client.ts` 对非 2xx 会抛 `ApiError(status, data)`）。
7. **幂等性**：`save` 多次同体应等价；`load` 只读、无副作用。
8. **并发**：内部工具场景，简单 last-write-wins 即可，无需加锁合并。

---

## 5. 开放点 / 待确认

- **`key` 的取值（不阻塞后端契约）**：前端目前所在页面无用户/机型上下文，`key` 的具体值由前端阶段决定（候选：固定 `"default"` / 前端生成 uuid 存 localStorage / 按机型 task_id）。
  - 对后端的要求**已经确定**：把 `key` 当作任意不透明字符串（满足 §4.3 字符白名单即可）用作文件名。**后端无需等待此决定即可开工**，因为契约层面 `key` 只是一个 string。
  - 隔离风险提示：无用户体系下，同 `key` 会被不同浏览器互相覆盖。内部 LAN 工具通常可接受；若需隔离，等前端把 `key` 与用户/机型挂钩后再说，后端逻辑不变。
- **未来扩展（本期不做）**：多份命名仪表盘会额外需要 `GET /api/display/list`、`DELETE /api/display/delete?key=`。本契约预留接口组 `/api/display/*` 命名空间，便于后续增量。

---

## 6. 验证（后端自测，curl 示例）

```bash
# 保存（覆盖）
curl -i -X POST http://192.168.31.178:8001/api/display/save \
  -H 'Content-Type: application/json' \
  --data-binary @canvas.json
# 期望：200  { "key": "...", "savedAt": "..." }

# 加载（存在）
curl -i 'http://192.168.31.178:8001/api/display/load?key=default'
# 期望：200  { "key": "default", "canvas": {...}, "savedAt": "..." }

# 加载（不存在）
curl -i 'http://192.168.31.178:8001/api/display/load?key=never'
# 期望：404  { "detail": "..." }

# 路径穿越应被拒
curl -i 'http://192.168.31.178:8001/api/display/load?key=../../etc/passwd'
# 期望：400

# 保真自测：保存后立即加载，比对响应 body 中的 canvas 与请求 body 中的 canvas 是否逐字段一致
```

最小可用的 `canvas.json`（直接拿去存 → 取 → 还原）：

```json
{
  "key": "default",
  "canvas": {
    "version": 1,
    "config": {
      "sizes": [ { "value": "medium", "label": "中", "w": 6, "h": 10 } ],
      "layout": { "cols": 12, "totalRows": 30, "margin": [12, 12], "containerPadding": [16, 16] }
    },
    "layout": [
      {
        "i": "demo-1", "x": 0, "y": 0, "w": 6, "h": 10,
        "type": "display", "category": "", "title": "温度", "static": false,
        "config": { "data": "flight_001", "columns": ["time", "temperature"], "limit": 0, "type": "SINGLE_TIMESERIES_2D", "size": "medium", "style": "LINE", "keepSize": false },
        "option": {
          "tooltip": { "trigger": "axis" },
          "xAxis": { "type": "category", "data": ["00:00", "00:01", "00:02"] },
          "yAxis": { "type": "value" },
          "series": [ { "name": "temperature", "type": "line", "data": [36.5, 36.6, 36.7] } ]
        }
      }
    ]
  },
  "timestamp": "2026-08-06T10:00:00.000Z"
}
```

---

## 7. 后端就绪后，前端将做什么（仅供后端了解联调预期）

1. `src/api/display.ts`：复用现有 `client`（`createClient({ baseURL: API_PREFIX.TASK })`），新增
   - `saveDisplay(req)` → `client.post('/display/save', req)`
   - `loadDisplay(key)` → `client.get('/display/load', { key })`
   并加对应 TS 类型。
2. 序列化复用现成的 `DashboardContainer.exportLayout()` 信封（`{ config, layout, timestamp }`，见 `DashboardContainer.vue:292-306`），外加 `key` 与 `version` 即为本契约的请求体。还原复用已暴露的 `setLayout` / `getLayout`（`DashboardContainer.vue:314-315`）与 `initialLayout` watcher——加载拿到的 `layout` 直接喂进去，各 item 自带 `option`，`ChartWidget` 按 `i` 重建实例并 `setOption`，**无需重新查询**。
3. `MonitorView.vue` 顶栏 `.header-right` 加「保存」「加载」两个按钮与 handler；404 提示「无已保存画布」，成功加载后清空 `selectedId`/`editTarget` 并刷新画布。

> 以上前端改动在后端接口可用后再进行，本期不在前端动代码。
