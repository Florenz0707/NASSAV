# 接口文档（概要）

本文档为工程提供简明接口说明，包含新增的预览、缩略图、批量与条件请求支持，便于前端对接与自动化测试。

说明：所有 API 使用统一 envelope 响应格式：

```json
{ "code": <number>, "message": "...", "data": <any>, "pagination"?: {...} }
```

HTTP 状态码仍与语义保持一致（200/201/404/500 等），`code` 为项目内业务码（0/200 表示成功，其他为错误或非标准语义，组件应基于 `code` 与 `message` 做友好提示）。

---

## 访问与会话（P1）

目标为经同源 HTTPS 反向代理访问的单用户会话。`NASSAV_OPERATOR_USERNAME` 指定唯一可访问业务数据的 Django 账号（默认 `nassav`）；账号必须处于启用状态。浏览器先调用公开的会话接口取得 CSRF cookie，再以该账号登录。所有 `/nassav/api/` 业务端点统一要求此账号的有效 session；匿名请求返回 HTTP 401，其他账号返回 HTTP 403。跨站请求不开放 CORS。

| 访问级别 | 端点                                                                                             | 规则                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| 公开     | `GET /nassav/api/auth/session`                                                                   | 返回 `data.authenticated`、`data.username`（匿名时为 `null`），并签发 CSRF cookie；无敏感数据 |
| 公开写入 | `POST /nassav/api/auth/login`                                                                    | JSON `{"username":"…","password":"…"}`；需要 CSRF；仅配置的账号可登录业务应用                 |
| 登录写入 | `POST /nassav/api/auth/logout`                                                                   | 需要 operator session 与 CSRF；注销后旧 session 不能再读写或接收任务事件                      |
| 登录可读 | `/nassav/api/` 下所有业务 GET，包括 Cookie、设置、资源、推荐、下载及任务状态                     | 只允许 operator；抓取任务 `GET /resource/jobs/{task_id}` 仍额外要求 `X-Resource-Job-Token`    |
| 登录可写 | `/nassav/api/` 下所有业务 POST/PUT/PATCH/DELETE，包括 Cookie、设置、资源删除、推荐重置与任务提交 | 只允许 operator，并通过 Django SessionAuthentication 验证 CSRF                                |
| 登录实时 | `WS /nassav/ws/tasks/`                                                                           | 握手前验证合法 Host、同源 Origin 和 operator session；注销或过期后不再发送事件                |
| 仅内部   | `GET /healthz`                                                                                   | 仅 Compose 内部探针；网关不转发                                                               |

会话接口响应使用本页统一 envelope。登录错误为 401，CSRF 或 Origin 校验失败为 403。浏览器请求需带 session cookie，写请求需带 `X-CSRFToken`；前端 Axios 自动处理。WebSocket 使用页面的 `ws://` 或 `wss://` 同源地址，不能使用跨站 Origin。代理必须保留原始 Host（含非标准端口）并传入可信的 `X-Forwarded-Proto`；Django `ALLOWED_HOSTS` 只校验 Host，不替代身份验证。

---

## 内部健康检查

`GET /healthz` 检查当前配置的数据库连接与 Redis，返回 `{"status":"ok"}` 或 HTTP 503 的 `{"status":"unavailable"}`。此端点仅用于 Compose 内部就绪检查；网关不转发它，也不代表外部抓取源可用。

## OpenAPI 与契约快照

drf-spectacular 用于离线生成和消费者契约检查。当前 django_project/urls.py 和 nassav/urls.py 未注册 Swagger UI 或 Schema HTTP 路由，因此 /nassav/docs 与 /nassav/openapi 不是现有访问入口；历史版本说明不代表当前 URL 已启用。

从后端目录以专用无凭证设置生成临时文件：

```bash
DJANGO_SETTINGS_MODULE=django_project.refactoring_test_settings \
  uv run python manage.py spectacular --file /tmp/nassav-openapi.yaml
```

scripts/generate_openapi.py 是另一离线包装，默认使用实例配置并写 doc/openapi.yaml；运行前确认配置及输出目标。URL/OpenAPI 基线由 test_http_contracts.py 对照固定 paths/components，不因移动视图或生成器告警自动重建。若新增在线文档端点，需明确权限并单独更新路由与消费者契约。

2026-10-05 离线复验的 paths/components 与固定快照一致，生成结果为 53 条告警（42 条唯一）、0 错误。告警包括自定义会话认证缺少 Schema 扩展及兼容尾斜杠导致的 operationId 冲突；生成文件不能替代本文的权限约定。

---

## 获取用户设置

- 方法：GET
- 路径：`/nassav/api/setting`
- 功能：获取用户前端显示配置
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "enable_avatar": "true",
    "display_title": "source_title",
    "search_result_display_style": "grid",
    "default_external_search_source": "jable"
  }
}
```

**配置项说明**：

- `enable_avatar`: 是否显示演员头像（`"true"` 或 `"false"`）
- `display_title`: 前端显示哪个标题字段
  - `"original_title"`: 显示原始日语标题
  - `"source_title"`: 显示下载源标题（默认）
  - `"translated_title"`: 显示翻译后的中文标题
- `search_result_display_style`: 推荐页搜索结果展示样式
  - `"grid"`: 标准网格布局（默认）
  - `"masonry"`: 两列瀑布流布局

**配置文件自动重载**：

- 配置存储在当前登录用户的 `UserPreferences` 数据库行中；缺省值不读写文件。旧INI仅通过显式导入命令迁移。
- 系统会自动检测配置文件的修改时间
- 当检测到文件被外部修改时，会自动重新加载配置
- 这确保了即使手动编辑配置文件，API 也能返回最新的设置

---

## 更新用户设置

- 方法：PUT
- 路径：`/nassav/api/setting`
- 功能：更新用户前端显示配置
- 请求 Body（支持部分更新）：
  - `enable_avatar`: `"true"` 或 `"false"`（可选）
  - `display_title`: `"original_title"` | `"source_title"` | `"translated_title"`（可选）
  - `search_result_display_style`: `"grid"` | `"masonry"`（可选）

示例请求：

```json
PUT /nassav/api/setting
{
  "enable_avatar": "false",
  "display_title": "translated_title",
  "search_result_display_style": "masonry",
    "default_external_search_source": "missav"
}
```

返回示例：

```json
{
  "code": 200,
  "message": "设置已更新",
  "data": {
    "enable_avatar": "false",
    "display_title": "translated_title",
    "search_result_display_style": "masonry",
    "default_external_search_source": "missav"
  }
}
```

错误响应示例（无效值）：

```json
{
  "code": 400,
  "message": "参数验证失败",
  "data": {
    "display_title": ["display_title 必须是 original_title, source_title, translated_title 之一"]
  }
}
```

---

## 获取可用下载源列表

- 方法：GET
- 路径：`/nassav/api/source/list`
- 功能：返回所有可用的下载源名称列表
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": ["missav", "javbus", "javdb"]
}
```

---

## 获取源 Cookie 列表

- 方法：GET
- 路径：`/nassav/api/source/cookie`
- 功能：获取所有已设置的源 Cookie 配置列表
- 返回字段：
  - `source`: 源名称
  - `cookie`: Cookie 内容
  - `mtime`: 最后更新时间（ISO 8601 格式）

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "source": "missav",
      "cookie": "user_uuid=...; remember_web_...",
      "mtime": "2026-01-03T12:16:13.547333+08:00"
    },
    {
      "source": "jable",
      "cookie": "PHPSESSID=...",
      "mtime": "2026-01-02T20:52:00.122665+08:00"
    }
  ]
}
```

---

## 设置源 Cookie

- 方法：POST
- 路径：`/nassav/api/source/cookie`
- 功能：为指定源设置 Cookie（手动设置或自动获取）
- 请求 Body：
  - `source`: 源名称（必填）
  - `cookie`: 手动设置的 cookie 字符串（可选）
  - `auto`: 是否自动获取 cookie（boolean，可选）
  - `user_agent`: 人工 Cookie 配套的 UA（字符串，可选；省略则清除旧 UA）

示例请求：

```json
// 手动设置 Cookie
POST /nassav/api/source/cookie
{
  "source": "missav",
  "cookie": "your-cookie-string"
}

// 自动获取 Cookie
POST /nassav/api/source/cookie
{
  "source": "missav",
  "auto": true
}
```

返回示例：

```json
{
  "code": 200,
  "message": "Cookie 设置成功",
  "data": {
    "source": "missav",
    "cookie_set": true
  }
}
```

---

自动获取 MissAV Cookie 时，已启用的浏览器提供方先获取并校验首页，再保存适用于目标域名的 Cookie；无可用 Cookie 或页面无效时返回失败，已有值保持不变。P1 的会话字段是内部兼容扩展，旧 GET/POST/DELETE 请求及响应包络、旧字段保持兼容；手动设置未传 UA 时会清除历史配套 UA、到期时间和代理路线标识，DELETE 也会一并清空这些元数据。旧 Cookie 仍按默认 UA 尝试直连。Cookie 保存成功不代表已验证可直连，也不代表播放清单或媒体下载成功。

P2 的 MissAV/Jable 详情及 Jable 列表、搜索页面在 Byparr 页面通过同站点、非挑战和业务结构校验后，可筛选适用于该 URL 的 Cookie 与浏览器 UA，并在 3 秒内对同一目标页做独立直连验证。只有直连 HTTP 200 且再次通过页面校验时，才按数据库版本写入可复用会话；失败时仍可使用本次有效的浏览器页面。此内部行为保留 Cookie API 的旧字段，也不代表 `POST /api/source/cookie` 自动获取入口已接入 P3 的并发协调。

P3 将 `POST /api/source/cookie` 的 `auto=true` 与页面 403/挑战后的自动会话刷新接入相同的站点租约。已有更新正在进行时，该入口有限等待并复用新 Cookie；Redis 不可用、租约超时或自动结果晚于人工设置时不写回，并保留原有失败响应格式。人工 POST 与 DELETE 无需等待租约，立即更新数据库。

## 清除源 Cookie

- 方法：DELETE
- 路径：`/nassav/api/source/cookie`
- 参数：
  - `source`: 源名称（必填，Query 参数）
- 功能：清除指定源的 Cookie（设为空字符串）

示例请求：

```json
DELETE /nassav/api/source/cookie?source=missav
```

返回示例：

```json
{
  "code": 200,
  "message": "Cookie 已清除",
  "data": {
    "source": "missav",
    "cookie_set": false
  }
}
```

---

## 推荐系统接口

推荐系统的完整设计、分层职责与调用流程见：

- [`recommendation.md`](./recommendation.md)

当前推荐接口为 demo 级实现，主要基于本地库中高频演员/类别与 Jable 页面或搜索结果做轻量召回和排序。

### 获取推荐结果

- 方法：GET
- 路径：`/nassav/api/recommendations`
- 功能：统一推荐入口
- 支持 Query 参数：
  - `strategy`：推荐策略标识，默认 `local_preference`（当前仅此一项）
  - `type_preference`：种子类型偏好，`actor_heavy | balanced | genre_heavy`
  - `actor_preference`：演员偏好，`familiar | balanced | rare`
  - `genre_preference`：类别偏好，`familiar | balanced | rare`
  - `limit`：返回数量，默认 `12`
  - `per_seed_limit`：每个 seed 的召回上限，默认 `12`
  - `actor_seed_limit`：演员种子数量，默认 `5`
  - `genre_seed_limit`：类别种子数量，默认 `5`
  - `exclude_existing`：是否过滤本地已存在资源，默认 `true`
  - `avoid_recent_recommendations`：是否尽量避开最近同配置已经推荐过的结果，默认 `true`
  - `recent_snapshot_limit`：回看最近多少次同配置推荐，默认 `3`
  - `recent_item_limit`：最多读取多少条历史推荐 `avid`，默认 `36`
  - `include_hot_board`：是否将 Jable 热榜候选并入召回池，默认 `true`
  - `include_latest_updates`：是否将 Jable 最近更新候选并入召回池，默认 `true`
  - `discovery_limit`：热榜/最近更新总共最多补充多少条候选，默认 `12`
  - `detail_enrichment_limit`：每轮最多为多少个候选抓取详情页补充 actor/genre 元数据，默认 `24`；默认用于 discovery 候选，开启 seed 黑名单时也用于已命中 seed 的候选做详情级黑名单兜底
  - `force_refresh_external`：是否强制外部源跳过搜索缓存并重新抓取，默认 `false`

示例请求：

```json
GET /nassav/api/recommendations?strategy=local_preference&type_preference=balanced&actor_preference=rare&genre_preference=balanced&limit=12&exclude_existing=true
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "avid": "ABC-123",
        "title": "Result Title",
        "detail_url": "https://jable.tv/videos/abc-123/",
        "cover_url": "https://assets-cdn.jable.tv/...",
        "source": "Jable",
        "snapshot_id": 12,
        "score": 8.5,
        "reasons": ["命中高频actor: Alice"],
        "raw_metrics": {
          "views": 123456,
          "likes": 789,
          "duration": "01:55:12"
        }
      }
    ],
    "seeds": [
      {
        "seed_type": "actor",
        "value": "Alice",
        "weight": 5.0,
        "source": "local_top_actor",
        "resource_count": 12
      }
    ],
    "summary": {
      "seed_count": 1,
      "item_count": 1
    },
    "meta": {
      "recommender": "jable_page_lookup",
      "strategy": "local_preference",
      "snapshot_id": 12,
      "request_fingerprint": "e6fd...",
      "recommender_detail": {
        "id": "jable_page_lookup",
        "name": "Jable Page Lookup",
        "description": "优先通过 Jable actor/genre 映射页召回，回退到搜索页。"
      },
      "strategy_detail": {
        "id": "local_preference",
        "name": "Local Preference",
        "description": "基于本地高频演员与类别的 Jable 搜索推荐 demo。",
        "parameter_profile": [
          {
            "title": "新鲜感控制",
            "items": [
              {
                "key": "fresh_bonus",
                "value": 0.7,
                "meaning": "近期历史未出现的候选加分。"
              }
            ]
          }
        ]
      },
      "effective_request": {
        "limit": 12,
        "per_seed_limit": 12,
        "actor_seed_limit": 5,
        "genre_seed_limit": 5,
        "seed_types": ["actor", "genre"],
        "exclude_existing": true,
        "random_seed": 123456789,
        "avoid_recent_recommendations": true,
        "recent_snapshot_limit": 3,
        "recent_item_limit": 36,
        "include_hot_board": true,
        "include_latest_updates": true,
        "discovery_limit": 12,
        "detail_enrichment_limit": 24,
        "type_preference": "balanced",
        "actor_preference": "rare",
        "genre_preference": "balanced",
        "force_refresh_external": false
      },
      "history_context": {
        "recently_recommended_count": 12,
        "recent_history_candidate_count": 18,
        "filtered_history_count": 4
      },
      "learning_context": { "feedback_count": 6, "learned_avid_count": 0, "learned_seed_count": 0 }
    }
  }
}
```

### 获取推荐器与策略选项

- 方法：GET
- 路径：`/nassav/api/recommendations/options`
- 功能：返回可用推荐器、策略和默认值，供前端动态渲染选择区

补充说明：

- 当最近推荐过滤后剩余候选少于请求 `limit` 时，系统会用近期已推荐过但得分较低的候选补齐返回数量，避免第三次、第四次连续刷新时结果明显缩水。
- 如果当前高位演员/类别种子召回到的候选不足，或者这些候选大多已在近期推荐中出现，系统会自动继续下探到排名更靠后的演员/类别种子补召回。
- 演员种子会自动展开常见别名（例如括号内别名），用于提升 Jable 搜索召回率。
- `include_hot_board=true` 时会把 Jable 热榜 async block 的今日 / 本周 / 本月 / 全部四档榜单作为 discovery 候选源；`include_latest_updates=true` 时会把 `/latest-updates/` 作为 discovery 候选源，两者都会带上来源标签参与轻量加分排序。
- discovery 候选会在 `detail_enrichment_limit` 范围内尝试抓取详情页 actor/genre 元数据；若详情命中本轮种子，会补充 `matched_seeds` 并参与 seed 加分。开启 seed 黑名单时，已命中 seed 的候选也会在该限制内补详情，用于按 Jable 详情页中的 tag/category slug 做兜底过滤。
- `like` / `dislike` 是偏好反馈，只影响 actor/genre seed 的后续排序；AVID 级过滤由资源黑名单接口负责。
- `strategy_detail.parameter_profile` 会返回每个策略参数的实际值和参数含义，前端可直接用于“策略参数说明”展示。

### 获取推荐效果概览

- 方法：GET
- 路径：`/nassav/api/recommendations/metrics`
- 功能：返回当前推荐历史、重复率、反馈计数和黑名单数量等概览，用于调参和验证推荐效果。

### 提交推荐反馈

- 方法：POST
- 路径：`/nassav/api/recommendations/feedback`
- 功能：记录推荐项反馈
- 请求体：
  - `snapshot_id`：该推荐项所属快照 ID
  - `avid`：推荐项资源编号
  - `feedback`：`like | dislike | clear`

示例请求：

```json
POST /nassav/api/recommendations/feedback
{
  "snapshot_id": 12,
  "avid": "ABC-123",
  "feedback": "like"
}
```

说明：

- `like` 会累计到命中的 actor / genre seed，作为后续排序的正反馈。
- `dislike` 会累计到命中的 actor / genre seed，作为后续排序的负反馈。
- `clear` 会取消该推荐项现有反馈，并按差异回退 actor / genre seed 的反馈计数。
- 若需要后续直接过滤某个 AVID，应同时调用资源黑名单接口。

### 管理推荐黑名单

#### 演员 / 类别黑名单

- 方法：POST / DELETE
- 路径：`/nassav/api/recommendations/seed-block`
- 功能：手动屏蔽或取消屏蔽库内 actor / genre

示例请求：

```json
POST /nassav/api/recommendations/seed-block
{
  "seed_type": "actor",
  "id": 12,
  "reason": "manual"
}
```

```json
DELETE /nassav/api/recommendations/seed-block
{
  "seed_type": "genre",
  "id": 5
}
```

#### 资源黑名单

- 方法：GET / POST / DELETE
- 路径：`/nassav/api/recommendations/avid-blocklist`
- 功能：查看、添加、删除 AVID 级资源黑名单

`GET` Query 参数：

- `page`
- `page_size`
- `search`：按 `avid` 过滤

示例请求：

```json
POST /nassav/api/recommendations/avid-blocklist
{
  "avid": "ABC-123",
  "reason": "manual"
}
```

```json
DELETE /nassav/api/recommendations/avid-blocklist
{
  "avid": "ABC-123"
}
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "snapshot_id": 12,
    "avid": "ABC-123",
    "feedback": "dislike",
    "feedback_value": -1
  }
}
```

### 清空推荐状态

- 方法：POST
- 路径：`/nassav/api/recommendations/reset`
- 功能：清空推荐快照、推荐项和反馈记录；默认保留 AVID 黑名单与手动 seed 屏蔽。
- 请求体：
  - `preserve_blocklist`：是否保留黑名单，默认 `true`；传 `false` 时同时清空 AVID 黑名单和 seed 屏蔽画像。

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "preserve_blocklist": true,
    "snapshot_count": 12,
    "item_count": 144,
    "feedback_count": 8
  }
}
```

### 获取推荐封面代理缓存

- 方法：GET
- 路径：`/nassav/api/recommendations/cover`
- Query 参数：
  - `url`：原始推荐封面地址
- 功能：后端代理并缓存推荐封面，避免前端直接访问受限站点资源

### 兼容 demo 接口

- 方法：GET
- 路径：`/nassav/api/recommendations/demo`
- 功能：兼容旧的 demo 调用方式，当前内部仍走统一 `RecommenderManager`

---

## 资源列表（服务端过滤/搜索/排序/分页）

- 方法：GET
- 路径：`/nassav/api/resources`
- 支持 Query 参数：
  - `status`：`downloaded|pending|all`（等同于 file_exists）
  - `watched`：`true|false`（按观看状态过滤）
  - `is_favorite`：`true|false`（按收藏状态过滤）
  - `sort_by`：`avid|metadata_create_time|metadata_update_time|video_create_time|source`
  - `order`：`asc|desc`
  - `page`、`page_size`
  - `source`：逗号分隔的源列表
  - `actor`：按演员过滤，可传演员 ID（精确匹配）或名称（模糊匹配）
  - `genre`：按类别过滤，可传类别 ID（精确匹配）或名称（模糊匹配）

示例请求：

```json
GET /nassav/api/resources?status=pending&sort_by=metadata_create_time&order=desc&page=1&page_size=18
GET /nassav/api/resources?watched=true                       # 已观看的资源
GET /nassav/api/resources?is_favorite=true                   # 已收藏的资源
GET /nassav/api/resources?actor=1                           # 按演员 ID 过滤
GET /nassav/api/resources?actor=桥本                         # 按演员名称模糊匹配
GET /nassav/api/resources?genre=中文字幕                      # 按类别名称模糊匹配
GET /nassav/api/resources?actor=1&genre=2&status=downloaded  # 组合过滤
```

返回：`data` 为数组（资源摘要），响应内含 `pagination` 字段：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "avid": "ABC-123",
      "original_title": "日语原标题",
      "source_title": "下载源标题",
      "translated_title": "中文翻译标题",
      "source": "missav",
      "release_date": "2025-01-01",
      "has_video": true,
      "watched": false,
      "is_favorite": true,
      "metadata_create_time": 1704067200,
      "metadata_update_time": 1704070800,
      "video_create_time": 1704070800,
      "genres": ["类别1", "类别2"],
      "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=medium&v=1704067200"
    }
  ],
  "pagination": { "total": 120, "page": 1, "page_size": 18, "pages": 7 }
}
```

**标题字段说明**：

- `original_title`: Scraper（Javbus）获取的原始标题，通常为日语
- `source_title`: 下载源（MissAV/Jable 等）提供的标题
- `translated_title`: 由翻译器生成的中文标题
- 前端可根据需要选择显示哪个标题，或按优先级回退

---

## 演员列表（聚合统计）

- 方法：GET
- 路径：`/nassav/api/actors`
- 功能：返回所有演员及其作品数统计，支持分页、搜索和排序（包含头像信息）
- 支持 Query 参数：
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `order_by`：排序字段，`count`（作品数）或 `name`（演员名称），默认 `count`
  - `order`：排序方向，`asc`（升序）或 `desc`（降序），默认 `desc`
  - `search`：搜索关键词，模糊匹配演员名称
  - `id`：演员 ID，精确查询单个演员信息

示例请求：

```json
GET /nassav/api/actors?page=1&page_size=20&order_by=count&order=desc
GET /nassav/api/actors?search=桥本
GET /nassav/api/actors?id=1
GET /nassav/api/actors?order_by=name&order=asc
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "桥本有菜",
      "resource_count": 85,
      "avatar_url": "https://www.javbus.com/pics/actress/abc_a.jpg",
      "avatar_filename": "abc_a.jpg",
      "is_blocked": false,
      "source_mapping": {
        "source_name": "jable",
        "source_seed_name": "桥本有菜",
        "source_seed_slug": "arina-hashimoto",
        "source_seed_url": "https://jable.tv/models/arina-hashimoto/",
        "aliases": ["Arina Hashimoto"]
      }
    },
    {
      "id": 2,
      "name": "三上悠亚",
      "resource_count": 72,
      "avatar_url": "https://www.javbus.com/pics/actress/xyz_a.jpg",
      "avatar_filename": "xyz_a.jpg",
      "is_blocked": true,
      "source_mapping": null
    }
  ],
  "pagination": {
    "total": 200,
    "page": 1,
    "page_size": 20,
    "pages": 10
  }
}
```

**说明**：

- `avatar_url`：演员头像原始URL（来自Javbus）
- `avatar_filename`：头像文件名（仅文件名，不含路径）
- 头像URL和文件名可能为 `null`（演员无头像或尚未刮削）
- `is_blocked`：是否已被加入推荐种子黑名单
- `source_mapping`：演员在外部源（当前为 jable）中的映射信息；没有映射时为 `null`

---

## 演员头像图片

- 方法：GET
- 路径：`/nassav/api/actors/<actor_id>/avatar`
- 功能：直接返回演员头像图片（JPEG格式）
- 路径参数：
  - `actor_id`：演员ID（整数）

示例请求：

```json
GET /nassav/api/actors/1/avatar
```

返回：

- HTTP 200：返回图片文件（Content-Type: image/jpeg）
- HTTP 404：演员不存在或无头像

使用示例：

```html
<img src="/nassav/api/actors/1/avatar" alt="演员头像" />
```

---

## 演员详情（含外部源搜索）

- 方法：GET
- 路径：`/nassav/api/actors/<actor_id>/detail`
- 功能：返回演员详情与外部源搜索结果（Jable/MissAV 已实现，实际可用项由搜索能力接口提供）
- 路径参数：
  - `actor_id`：演员 ID（整数）
- 支持 Query 参数：
  - `source`：外部源名称，默认 `jable`
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `ordering`：排序字段，支持 `-views`（默认）、`views`、`-likes`、`likes`、`avid`、`-avid`、`source_title`、`-source_title`
  - `force_refresh`：是否强制跳过外部搜索缓存并重新抓取，默认 `false`

示例请求：

```json
GET /nassav/api/actors/1/detail?source=jable&page=1&page_size=20&ordering=-views
GET /nassav/api/actors/1/detail?source=jable&page=1&page_size=20&ordering=-views&force_refresh=true
GET /nassav/api/actors/1/detail?source=missav&page=1&page_size=20
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "detail": {
      "id": 1,
      "name": "桥本有菜",
      "resource_count": 85,
      "avatar_url": "https://...",
      "avatar_filename": "abc_a.jpg"
    },
    "external_source": "jable",
    "external_meta": {
      "implemented": true,
      "message": "success",
      "ordering": "-views",
      "fetch_pages": 5,
      "cache": { "enabled": false, "hit": false, "force_refresh": false },
      "supported_sources": []
    },
    "external_results": [
      {
        "avid": "ABP-123",
        "source_title": "ABP-123 ...",
        "source": "Jable",
        "thumbnail_url": "https://...",
        "detail_url": "https://...",
        "metrics": { "views": 12345, "likes": 123 }
      }
    ]
  },
  "pagination": {
    "total": 20,
    "page": 1,
    "page_size": 20,
    "pages": 1
  }
}
```

说明：

- 当前采用用时获取（实时抓取）作为 Demo。
- 已预留缓存策略，后续可通过配置开启查询结果缓存。
- 对于未实现的源（如 `missav`、`memo`），接口返回 `implemented=false` 且 `external_results=[]`，不会影响详情页主信息。

---

## 类别列表（聚合统计）

- 方法：GET
- 路径：`/nassav/api/genres`
- 功能：返回所有类别及其作品数统计，支持分页、搜索和排序
- 支持 Query 参数：
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `order_by`：排序字段，`count`（作品数）或 `name`（类别名称），默认 `count`
  - `order`：排序方向，`asc`（升序）或 `desc`（降序），默认 `desc`
  - `search`：搜索关键词，模糊匹配类别名称
  - `id`：类别 ID，精确查询单个类别信息

示例请求：

```json
GET /nassav/api/genres?page=1&page_size=20&order_by=count&order=desc
GET /nassav/api/genres?search=中文
GET /nassav/api/genres?id=1
GET /nassav/api/genres?order_by=name&order=asc
```

返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "id": 1,
      "name": "中文字幕",
      "resource_count": 150,
      "is_blocked": false,
      "source_mapping": {
        "source_name": "jable",
        "source_seed_name": "中文字幕",
        "source_seed_slug": "chinese-subtitle",
        "source_seed_url": "https://jable.tv/tags/chinese-subtitle/",
        "aliases": ["Chinese Subtitle"]
      }
    },
    {
      "id": 2,
      "name": "人妻",
      "resource_count": 120,
      "is_blocked": true,
      "source_mapping": null
    }
  ],
  "pagination": {
    "total": 50,
    "page": 1,
    "page_size": 20,
    "pages": 3
  }
}
```

说明：

- `is_blocked`：是否已被加入推荐种子黑名单
- `source_mapping`：类别在外部源（当前为 jable）中的映射信息；没有映射时为 `null`

---

## 类别详情（含外部源搜索）

- 方法：GET
- 路径：`/nassav/api/genres/<genre_id>/detail`
- 功能：返回类别详情与外部源搜索结果（Jable/MissAV 已实现，实际可用项由搜索能力接口提供）
- 路径参数：
  - `genre_id`：类别 ID（整数）
- 支持 Query 参数：
  - `source`：外部源名称，默认 `jable`
  - `page`、`page_size`：分页参数（默认 page=1, page_size=20）
  - `ordering`：排序字段，支持 `-views`（默认）、`views`、`-likes`、`likes`、`avid`、`-avid`、`source_title`、`-source_title`
  - `force_refresh`：是否强制跳过外部搜索缓存并重新抓取，默认 `false`

示例请求：

```json
GET /nassav/api/genres/1/detail?source=jable&page=1&page_size=20&ordering=-views
GET /nassav/api/genres/1/detail?source=jable&page=1&page_size=20&ordering=-views&force_refresh=true
```

返回结构与演员详情接口一致，`data.detail` 对象改为类别信息（`id`、`name`、`resource_count`）。

---

## 资源详情预览（首屏）

- 方法：GET
- 路径：`/nassav/api/resource/{avid}/preview`
- 返回：`{ metadata, thumbnail_url }`，用于详情页首屏快速渲染。

示例：

```json
GET /nassav/api/resource/ABC-123/preview
```

返回（示例）：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "metadata": {
      "avid": "ABC-123",
      "original_title": "日语原标题",
      "source_title": "下载源标题",
      "translated_title": "中文翻译标题",
      "source": "missav",
      ...
    },
    "thumbnail_url": "/nassav/api/resource/cover?avid=ABC-123&size=small&v=1681234567"
  }
}
```

- 备注：`v` 参数为封面文件的 mtime（用于强缓存失效），前端可直接将 `thumbnail_url` 作为 `<img src>`。

---

## 资源元数据详情

- 方法：GET
- 路径：`/nassav/api/resource/metadata?avid=<AVID>`
- 功能：获取资源完整元数据（演员、类别、时长等）
- 说明：
  - 返回三个标题字段：`original_title`（日语）、`source_title`（下载源）、`translated_title`（中文）
  - 若需要 m3u8 链接，请使用刷新接口获取
- 支持条件请求（ETag/Last-Modified），返回 304 节省带宽

返回字段：`avid`, `original_title`, `source_title`, `translated_title`, `source`, `release_date`, `duration`, `director`, `studio`, `label`, `series`, `actors[]`, `genres[]`, `file_exists`, `file_size`, `watched`, `is_favorite`, `notes`, `state_version`

---

## 封面与缩略图

- 方法：GET
- 路径：`/nassav/api/resource/cover?avid=<AVID>[&size=small|medium|large][&v=hash]`

行为：

- 无 `size` 时返回原始封面文件（若存在）；有 `size` 时返回对应尺寸的缩略图，路径为 `resource/cover/thumbnails/{size}/{AVID}.jpg`。
- 若缩略图不存在，后端会按需生成并返回（best-effort）。
- 响应包含 `Cache-Control: public, max-age=31536000` 及 `ETag` 与 `Last-Modified`，支持条件请求头返回 `304`。

示例：

```json
<img src="/nassav/api/resource/cover?avid=ABC-123&size=small" />
```

条件请求示例：

```json
If-None-Match: "etag-value"
If-Modified-Since: Wed, 21 Oct 2015 07:28:00 GMT
```

若匹配，后端返回 `304 Not Modified`（无 body），浏览器/客户端使用缓存数据。

---

## 获取视频文件路径

- 方法：GET
- 路径：`/nassav/api/downloads/abspath?avid=<AVID>`
- 功能：返回视频文件的绝对路径。Compose 部署中通过 `VIDEO_HOST_DIR` 映射到宿主机目录，然后拼接 `config.FilePathPrefix`；浏览器需能访问此路径。
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "abspath": "http://your-server/path/to/video/ABC-123.mp4"
  }
}
```

---

## 任务队列状态

- 方法：GET
- 路径：`/nassav/api/tasks/queue/status`
- 功能：获取当前任务队列状态（包括所有 PENDING 和 STARTED 状态的任务）
- 返回示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "pending": [
      {
        "task_id": "abc123...",
        "avid": "ABC-123",
        "task_type": "download",
        "status": "PENDING"
      }
    ],
    "active": [
      {
        "task_id": "def456...",
        "avid": "DEF-456",
        "task_type": "download",
        "status": "STARTED",
        "progress": 45.2
      }
    ],
    "total_pending": 10,
    "total_active": 2
  }
}
```

---

## 单项操作返回最新对象

- 新增资源：`POST /nassav/api/resource`（body: {avid, source?}）
  - 返回 `data.resource`：精简资源对象，仅包含以下字段：
    - `avid`: 视频编号
    - `original_title`: 原始标题（来自 Scraper，如 JavBus）
    - `source_title`: 源标题（来自下载源网站，如 Jable/MissAV）
    - `translated_title`: 翻译后的标题
    - `source`: 来源网站名称
  - 返回示例：

    ```json
    {
      "code": 201,
      "message": "success",
      "data": {
        "resource": {
          "avid": "ABC-123",
          "original_title": "テストタイトル",
          "source_title": "ABC-123 Test Title",
          "translated_title": "测试标题",
          "source": "Jable"
        },
        "cover_downloaded": true,
        "metadata_saved": true,
        "scraped": true
      }
    }
    ```

  - 资源已存在时（409）也返回相同格式的精简资源对象

- 刷新资源：`POST /nassav/api/resource/refresh/{avid}`
  - 返回 `data.resource`：刷新后的资源对象
  - **支持细粒度刷新参数**（Body JSON，可选）：
    - `refresh_m3u8`: 是否刷新 m3u8 链接（默认 `true`）
    - `refresh_metadata`: 是否刷新元数据（从 source 重新抓取，默认 `true`）
    - `retranslate`: 是否重新翻译标题（默认 `false`）
  - 示例：

    ```json
    // 只刷新 m3u8 链接
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_m3u8": true, "refresh_metadata": false, "retranslate": false}

    // 只重新翻译
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_m3u8": false, "refresh_metadata": false, "retranslate": true}

    // 刷新元数据并重新翻译（注意：会先刷新元数据获取新标题，再执行翻译）
    POST /nassav/api/resource/refresh/ABC-123
    {"refresh_metadata": true, "retranslate": true}
    ```

  - 响应包含：
    - `resource`: 更新后的资源对象
    - `metadata_refreshed`: 是否刷新了元数据
    - `m3u8_refreshed`: 是否刷新了 m3u8
    - `translation_queued`: 是否已提交翻译任务（异步）
    - `cover_downloaded`, `metadata_saved`, `scraped`: 保存结果

- 删除资源：`DELETE /nassav/api/resource/{avid}`
  - 持久任务记录仍持有该 AVID 活动名额或存在未恢复 promoting 文件日志时，单条删除返回 HTTP 409，批量 `delete` / `delete-all` / `delete-video` 返回该项 `code: 409`；运行/暂停任务须先终止，未恢复日志须先重试清理；之后才能删除。暂停也持有名额。下载删除 `DELETE /nassav/api/downloads/{avid}` 遵循同一规则。
  - 返回 `data.resource`（删除前序列化对象，纯文件资源为 `null`）和 `deleted_files`；数据库行或任一文件存在即可删除，无记录无文件返回 404
  - 与批量 `delete` / `delete-all` 共用删除操作：清理封面、small/medium/large 缩略图、MP4、备份目录和数据库行。`deleted_files` 只列出已确认删除的文件名
  - 文件或数据库步骤失败返回 HTTP 500、`message: "删除未完成，请重试"`，`data` 包含 `failed_stage`（`lock`、`files` 或 `database`）、`retryable: true` 和已删除文件名。取锁失败时 `failed_stage: lock`、`deleted_files: []`，message 明确提示检查锁目录及锁文件写入权限，修复后重试；未取锁不会执行文件或数据库删除。其他失败重试会继续清理剩余状态；错误响应不包含本地路径

- 下载视频：`POST /nassav/api/downloads/{avid}`
  - 功能：提交视频下载任务（异步，使用 Celery）
  - 前提：资源元数据必须已存在
  - 返回示例：

    ```json
    {
      "code": 202,
      "message": "下载任务已提交",
      "data": {
        "avid": "ABC-123",
        "task_id": "celery-task-id",
        "status": "pending"
      }
    }
    ```

  - 如果视频已下载，返回 `code: 409, message: "视频已下载"`
  - 如果任务已存在，返回 `code: 409, message: "下载任务已存在"`

- 删除视频：`DELETE /nassav/api/downloads/{avid}`
  - 功能：删除已下载的视频文件并清除数据库视频状态；若文件已删但数据库状态未清，重复请求可完成清理
  - 返回示例：

    ```json
    {
      "code": 200,
      "message": "success",
      "data": {
        "avid": "ABC-123",
        "deleted_file": "ABC-123.mp4",
        "file_size": 1234567890
      }
    }
    ```

前端应在收到 `resource` 对象后做局部合并更新，而非整页刷新。

---

## 批量接口

1. 批量资源操作

- 方法：POST
- 路径：`/nassav/api/resources/batch`
- Body 示例：

```json
{
  "actions": [
    { "action": "add", "avid": "ABC-123", "source": "any" },
    { "action": "refresh", "avid": "DEF-222" },
    { "action": "delete-video", "avid": "XYZ-001" },
    { "action": "delete-all", "avid": "OLD-999" }
  ]
}
```

- 返回：`data.results` 为数组，每项包含 `action, avid, code, message, resource?, deleted_files?, deleted_file?, file_size?`。

**操作说明**：

- `add`：添加资源
  - 如果资源已存在，返回 `code: 200, message: "already exists"` 和现有资源数据
  - 如果资源不存在，从指定 source 获取并创建，返回 `code: 201, message: "created"`
  - 如果获取失败，返回 `code: 404, message: "获取信息失败"`
- `refresh`：刷新资源
  - **支持细粒度刷新参数**（可选，默认全部刷新）：
    - `refresh_m3u8`: 是否刷新 m3u8 链接（默认 `true`）
    - `refresh_metadata`: 是否刷新元数据（默认 `true`）
    - `retranslate`: 是否重新翻译（默认 `false`）
  - 示例：

    ```json
    {
      "actions": [
        { "action": "refresh", "avid": "ABC-123", "refresh_m3u8": true, "refresh_metadata": false },
        { "action": "refresh", "avid": "DEF-456", "retranslate": true }
      ]
    }
    ```

  - 返回 `code: 200, message: "refreshed"`，`refresh_info` 包含操作结果，以及更新后的资源数据

- `delete-video`：只删除视频文件（保留元数据）
  - 返回 `code: 200, message: "视频已删除"`，包含 `deleted_file` 和 `file_size`
  - **数据库操作**: 更新记录标记视频不存在（`file_exists=False`）
  - **保留内容**: 元数据记录、封面图片、缩略图、备份目录
  - 示例返回：

    ```json
    {
      "action": "delete-video",
      "avid": "ABC-123",
      "code": 200,
      "message": "视频已删除",
      "deleted_file": "ABC-123.mp4",
      "file_size": 1234567890
    }
    ```

- `delete-all` 或 `delete`：删除全部数据（视频+元数据+封面+备份）
  - 返回 `code: 200, message: "已删除全部数据"` 和删除前的资源数据
  - **删除内容**: 视频文件、封面图片、small/medium/large 缩略图、备份目录、数据库记录；纯数据库行或纯文件也可删除
  - 示例返回：

    ```json
    {
      "action": "delete-all",
      "avid": "ABC-123",
      "code": 200,
      "message": "已删除全部数据",
      "resource": {...},
      "deleted_files": ["ABC-123.jpg", "ABC-123.mp4"]
    }
    ```

批量删除的 HTTP 响应保持 200；每个 `data.results[]` 独立报告结果。删除步骤失败时该项 `code: 500`、`message: "删除未完成，请重试"`，附 `failed_stage`、`retryable: true` 和已确认删除的 `deleted_files`，取锁失败同样使用 `failed_stage: lock`、空 `deleted_files` 和写入权限提示；其余项继续执行；非法编号为单项 400。前端只对 `code: 200` 的项目更新本地列表，失败项保留以便重试。旧 `add` / `refresh` 仍为同步兼容入口，当前前端新增和刷新走 `/resource/jobs/batch`；旧入口移除了无来源限流依据的固定 2 秒等待，后续退役须单独核对外部调用方。

1. 批量下载提交

- 方法：POST
- 路径：`/nassav/api/downloads/batch_submit`
- Body：`{ "avids": ["ABC-123","DEF-222"] }`
- 返回：每个 avid 的提交结果（`task_id` 或 409 表示任务已存在）。

前端在处理批量返回时应使用返回的 `resource` 对象做局部合并更新。

---

## 模拟下载（仅 DEBUG 模式）

- 方法：POST
- 路径：`/nassav/api/downloads/mock/{avid}`
- 功能：模拟下载任务，用于测试下载流程（不实际下载视频）
- 仅在 `DEBUG=True` 时可用
- 请求 Body（可选）：

  ```json
  {
    "duration": 30 // 模拟下载持续时间（秒），默认 30，范围 1-300
  }
  ```

- 返回示例：

  ```json
  {
    "code": 202,
    "message": "模拟下载任务已提交",
    "data": {
      "avid": "ABC-123",
      "task_id": "mock-task-id",
      "duration": 30
    }
  }
  ```

---

## 缓存与条件请求（前端要点）

- 对于 metadata/cover/thumbnail，后端会返回 `ETag` 与 `Last-Modified`。
- 浏览器会自动管理条件请求；若使用 `fetch`/`axios` 手动请求，可在请求头中传 `If-None-Match` 或 `If-Modified-Since`，并在收到 `304` 时复用本地缓存。

示例（curl）:

```json
curl -i -H 'If-None-Match: "123abc"' "http://<host>/nassav/api/resource/cover?avid=ABC-123&size=small"
```

---

## 响应 Envelope 约定

- `code`：业务层码，`200`/`0` 表示成功（视端点而定），非 2xx 需参考 `message` 字段并处理错误。
- `message`：可展示的错误/成功信息
- `data`：主载荷（资源数组、单个 resource、results 等）
- `pagination`（可选）：当返回分页集合时包含 `total,page,page_size,pages`。

---

## 示例前端注意事项（简短）

- `fetchResources` 应将 `search,status,sort_by,order,page,page_size,source` 传给后端，直接使用后端返回 `data` 与 `pagination` 渲染。
- 搜索框添加 200–400ms 防抖，减少请求频率。
- 在新增/刷新/批量接口返回 `resource` 时做局部合并更新。
- 图片直接使用 `thumbnail_url` 作为 `img.src`，依赖浏览器自动带条件头，或手动在 axios 中传 `If-None-Match`。

---

## 异步资源抓取任务

旧 `POST /nassav/api/resource`、`POST /nassav/api/resource/refresh/{avid}`、`POST /nassav/api/resources/batch` 保持同步响应结构。新接口不会在 HTTP 请求中等待 Byparr。

- `POST /nassav/api/resource/jobs`：提交一条 `add` 或 `refresh` 任务。请求示例：`{"action":"add","avid":"ABC-123","source":"any"}`。刷新可传 `refresh_m3u8`、`refresh_metadata`、`retranslate` 布尔值；重新翻译在刷新后提交。提交成功或重复提交均返回 HTTP 202，`data` 含稳定 `job_id`、当前 `task_id`、`status_url`、`status_token`、`job` 和 `duplicate`。存在自身活动任务时返回 duplicate，其他已有资源的 add 为 409；越权为 403；刷新不存在资源为 404；参数错误为 400；broker 发布失败保留 pending 并接受为 202；状态存储不可用为 503。
- `POST /nassav/api/resource/jobs/batch`：请求 `{"actions":[{"action":"add","avid":"ABC-123"},...]}`，一次 1–100 项，仅接受添加/刷新。HTTP 202 的 `data.results` 按输入顺序逐项给出 202、400、403、404、409 或 503；某项失败不阻止其他项入队。每个成功项有独立的 `job_id`、`task_id`、`status_url`、`status_token` 和 `duplicate`。
- `GET /nassav/api/resource/jobs/{task_id}`：请求头 `X-Resource-Job-Token: <status_token>` 必填。返回最新快照；令牌无效为 403，未知或过期任务为 404，状态存储不可用为 503。令牌有效期覆盖最长排队、运行和终态快照保留时间，不要写入公开日志或分享链接。

历史 Redis 任务的快照字段为 `task_id`、`job_type=scrape`、`action`、`avid`、`state`、`stage`、`version`、`updated_at`、`resource_avid`、`error_code`、`message`。状态顺序为 `queued → running → succeeded|failed`；运行阶段按实际执行进入 `source_lookup`、`metadata`、`cover`、`saving`、`translation_queued`。无总工作量时不提供百分比。前端应在入队后先查快照，按 `version` 忽略旧事件；成功后再重新查询资源。`scrape_job_update` WebSocket 事件仅含任务 ID、类型、状态、阶段、版本和更新时间；完整快照需凭令牌查询。

历史 Redis 快照查询额外返回 `resource`（可为空，含 AVID 和原始 / 来源 / 译后标题）及 `translation`。后者含 `state`，已提交时含翻译子任务 `task_id`；状态为 `not_requested`、`queued`、`translating`、`completed`、`failed`、`skipped`、`unknown` 或 `unavailable`。`unknown` 表示暂时无法读取结果，可重试；旧任务未记录子任务为 `unavailable`。Celery `SUCCESS` 必须结合业务返回的 `success` 和 `translation_status` 判定，不能当作翻译成功。刮削保存成功仍保持父任务 `succeeded`，翻译结果参与下述整体状态展示；子任务状态通过签名快照查询读取，不修改父任务终态和版本，也不在公开 WebSocket 广播标题或子任务结果。入队失败单独返回翻译 `failed`。结果和快照保留期限届满后停止轮询；客户端保留此前已取得的翻译终态及时间，尚未取得结果时明确显示未记录或已过期，不推断翻译成功。

历史 Redis 任务的资源编号采用大小写归一化后的单一任务锁，因此同一编号的添加与刷新互斥；重复提交返回正在处理的任务。排队任务 4 小时未开始则过期，锁最长保留 4 小时并在运行阶段续期；终态保存 24 小时；worker 丢失后待锁过期，查询会返回 `WORKER_LOST` 并允许重新提交。当前业务接口和任务 WebSocket 均要求 operator session；任务快照还要求独立签名令牌。远程部署必须使用同源 HTTPS 代理。

## P4 Cookie 管理兼容扩展

人工 `POST /nassav/api/source/cookie` 可加可选字符串 `user_agent`（最多 4096 字符）；省略或传空值会清除旧的配套 UA 和自动会话元数据。`auto=true` 的旧请求方式不变。GET 保留 `source/cookie/mtime`，增加 `session_source`（`manual`/`verified_browser`）、`user_agent_paired`、`session_expired` 和 `verified_direct_reuse` 布尔状态；完整 UA 不返回。`verified_direct_reuse` 还要求当前源的代理路线与保存时一致，仍不保证站点此刻放行。添加资源页 Cookie 弹窗中的“已保存”与“已验证可直连”按此状态区分。

### Jable 自动 Cookie（2026-10-01 修复）

`POST /nassav/api/source/cookie`，请求 `{"source":"Jable","auto":true}`：

- 启用 Byparr 且配置代理时，通过浏览器获取首页，验证同站点、非挑战页及列表业务结构，再携带返回的 Cookie 和 UA 经相同代理直连同页验证（200，最多 3 秒）。通过后保存完整会话。
- 显式自动获取不依赖 `BrowserFetch.session_reuse_enabled`；不会开启普通页面请求的会话复用。
- 浏览器禁用时保留原 HTTP 获取流程。浏览器会话缺少 Cookie/UA、页面校验失败、直连验证失败或写入保护拒绝时，自动获取仍返回 500，旧记录保留。
- 使用现有刷新租约及版本检查，自动结果不会覆盖获取期间的手动更新或清空。

## 演员、类别搜索源选择（2026-10-01）

`GET /nassav/api/source/search-capabilities` 返回当前启用且已实现的搜索源，独立于原 `/source/list` 下载源接口：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "source": "missav",
      "label": "MissAV",
      "actor": true,
      "genre": true,
      "orderings": ["-views", "-likes", "-latest"]
    }
  ]
}
```

演员 `/actors/{id}/detail`、类别 `/genres/{id}/detail` 沿用 `source` 参数，省略默认 Jable。支持 Jable/MissAV，实际可用项以能力接口为准。MissAV 优先使用对应源的演员/类别映射，缺少映射时使用实体名称关键词搜索；关键词结果不保证属于该演员或类别。支持按源站播放量、收藏量、发行日期降序，列表不提供数值，因此保留源站顺序，不对缺失指标做本地排序。

错误状态：未知源或 MissAV 不支持的排序为 400；禁用或未实现源为 503；抓取、挑战页或业务结构校验失败为 502。有效空搜索仍为 200。失败不缓存，不返回部分成功页伪装成完整结果。分页仍是 `EXTERNAL_SEARCH_FETCH_PAGES` 页采集结果的本地分页，并非全站总量；强制刷新沿用 `force_refresh=true`。

前端演员、类别页提供搜索源下拉选择，使用会话存储记住选择；缓存按实体、源和排序隔离，切换源重置分页，过期异步响应不会覆盖当前结果。添加资源时提交结果对应的源。

演员/类别外部搜索请求单独使用 450 秒前端超时与 600 秒 Nginx 读取预算，以覆盖默认最多 5 页浏览器采集；普通 API 超时保持原设置。改变采集页数或浏览器等待预算时应同步评估这两个限制。

## 外部搜索后台任务

演员、类别页面使用后台任务；原有 `/api/actors/{id}/detail` 和 `/api/genres/{id}/detail` 同步接口保留。省略 source 时使用持久化默认源，不可用时选择启用且支持该搜索的源。

### POST /api/search/jobs

需要已登录会话；遵循既有 CSRF 要求。请求字段：

- `entity_type`：`actor` 或 `genre`。
- `entity_id`：正整数。
- `source`：`jable` 或 `missav`，可省略。
- `page`：正整数，默认 1；`page_size`：1–100，默认 20。
- `ordering`：默认 `-views`；必须属于搜索源 capabilities 的排序项。
- `force_refresh`：布尔值，默认 false。

返回 HTTP 202，data 包含 `task_id`、签名 `token`、`state`、`duplicate` 和 `query`。相同查询复用正在执行的任务；普通查询可复用 300 秒内成功的任务。强制刷新只复用正在执行的相同强制刷新任务。

参数无效返回 400，对象不存在返回 404，搜索源或队列不可用返回 503。提交不执行上游抓取。

### GET /api/search/jobs/{task_id}?token=

需要已登录会话及提交返回的 token；凭证无效返回 403，快照不存在返回 404，Redis 不可用返回 503。

HTTP 200 的 data.state 为 `queued`、`running`、`succeeded`、`failed` 或 `cancelled`。每个非空源页面完成后，`running` 快照就包含累计去重、排序和分页后的 `data.result`，结构为 `data.detail`、`data.external_source`、`data.external_meta`、`data.external_results` 和 `pagination`。阶段结果的 detail 可以为空，`external_meta.partial=true`，`pages_completed` 记录已完成源页数。`pagination.total/pages` 与 Jable 本地排序会随后续页更新，最终成功后 `partial=false`。命中成功缓存时可直接返回完整结果。

失败时包含 `error_code`、`message`；若此前有成功源页，保留最后的阶段结果，前端展示“不完整”提示，允许添加已获取的资源。阶段结果不写入成功缓存，重试不会将残缺列表当作成功结果。请求第 N 个展示页时，只有累计结果足以覆盖该展示页才能显示卡片。

### POST /api/search/jobs/{task_id}/cancel

需要已登录会话及 CSRF，JSON 请求体为 `{ "token": "提交时返回的签名凭证" }`。凭证无效返回 403，任务不存在返回 404，已成功或失败返回 409，Redis 不可用返回 503。成功返回 200 和 `cancelled` 快照；重复取消返回同一终态。已获取的阶段结果保留，后续同条件查询可重新提交任务。

排队任务会向 Celery 发送撤销通知；运行中的任务在当前外站请求返回后停止后续页面抓取。取消状态先写入 Redis，迟到结果不会覆盖终态，也不会写入成功缓存。页面上的取消按钮发送该请求；离开页面只停止本地轮询。

既有登录 WebSocket `/nassav/ws/tasks/` 增加 `external_search_update`，data 仅含 `task_id/state/version/updated_at`。收到新版本通知后，前端立即带签名 token 查询快照；通知不包含搜索结果、查询和 token。保留每 1.5 秒轮询恢复断线或丢失通知，忽略旧版本响应；切源、离开页面时终止旧请求与订阅，后台任务继续执行。演员与类别页面进入外部搜索页、切源或调整排序均不自动提交；用户通过搜索按钮手动发起，来源设置不触发搜索。

### 默认搜索源与封面

`GET/PUT /api/setting` 增加 `default_external_search_source`，允许 `jable`（默认）和 `missav`。保存到当前登录用户的数据库设置；页面临时切换不修改默认值。0033及旧INI导入见[个人状态与设置](personal-state-architecture.md)。

`GET /api/recommendations/cover?url=...&source=missav` 支持 MissAV 搜索封面。省略 source 保持 Jable 行为。MissAV 当前只允许实测的 `fourhoi.com`，使用源配置代理与中文页面 Referer；下载限 20 秒、5 MiB，不跟随重定向，不转发站点 Cookie，成功后原子写入现有封面缓存。

## 页面抓取顺序与会话开关

`Source.<source>.browser_fetch_strategy` 独立决定顺序：`direct_first` 先直连、失败后浏览器；`browser_first` 先浏览器、失败后直连；`direct_only` 仅直连。即使 `BrowserFetch.session_reuse_enabled=false`，也不会改写 `direct_first`。

关闭完整会话复用时，直连仍采用已有 Cookie 的传统请求方式，不进行完整 Cookie + UA 会话复用、自动验证保存或刷新协调；开启后采用配套 UA、出口与过期检查及已验证会话刷新。此改动不修改正式配置或自动启用复用。

策略语义以本节与[配置契约](configuration-contract.md)为准；当前验证范围见[部署与验证边界](compose-deployment.md#近期改动与验证边界)，历史现场报告不作为本次新测量。

## 下载任务租约

下载执行使用独立 owner token，任务锁与全局锁的续租、释放均校验当前 owner。迟到执行不能覆盖后继任务的进度或清理其队列。失租或续租 Redis 故障停止下载 CLI，返回现有 failed 结果，不更新成功状态；CLI 无输出时也检测取消。默认锁 TTL 仍为 3600 秒，正常执行定期续租。任务名称和 HTTP 字段不变。旧 worker 的无条件删除逻辑不能与此实现混用，部署切换仍需单独验收。

### 下载提交与缓存准备

真实下载任务注册名仍为 nassav.tasks.download_video_task，模拟为 nassav.tasks.mock_download_video_task；参数和队列不变。缓存元数据缺失或无 m3u8 时，真实下载可能先准备资源并再次读取缓存，准备异常后仍尝试已有缓存。正常成功通知先于 DB 持久化，DB 失败告警不改变既有成功返回；数据一致性检查见[数据库说明](database.md)。

### 批量翻译异常收尾

批量标题筛选使用 `original_title` 或 `source_title`，保留指定 AVID 和 `skip_existing` 规则。翻译器异常、返回数量不一致或保存异常返回失败；本批未完成记录从 translating 收尾为 failed，已有译文及已保存成功结果保留。未选中的任务状态不受影响。

单条/批量翻译仍使用原 nassav.tasks.\* 任务名和结果字段。HTTP 重新翻译先清空译文、重置 pending，再提交任务；提交失败返回既有 translation_error，已重置状态不回滚。标题和持久化规则见[数据库说明](database.md)。

## 开发与复验导航

本文件维护消费者 URL、字段、权限、错误、缓存头和任务状态；内部模块与装配规则见[任务架构](task-control-architecture.md)与[推荐架构](recommendation-architecture.md)。URL/OpenAPI 的 paths/components 及路由由 tests/fixtures/backend_http_contract.json 对照验证，模拟/故障样本见[测试说明](../tests/README.md)。旧同步入口、兼容尾斜杠与原任务名继续存在；维护文档无需调整消费者请求。

### 外部任务结果分页

`GET /api/search/jobs/{task_id}?token=...` 支持可选 `page`（正整数）与 `page_size`（1–100，默认 20）；省略 page 保留提交时的结果页。分页参数无效返回 400。带有效签名 token 的查询从同一任务累积去重结果切片，返回的 `result.pagination` 按展示条数计算，不提交任务、不重新抓取、不修改任务版本。运行、失败、取消和成功状态均可浏览已获取结果；总条数和可浏览页数随进度增长，fetch_pages/pages_completed 专指源站抓取页数。内部累积结果不直接出现在公开快照或 WebSocket 中。

前端默认每页 15 项；搜索和浏览结果页是独立操作，翻页不停止后台搜索。已有旧 worker 生成的快照无法补出未保存的其他页，跨页读取返回 400 并提示重新搜索；发布时同步更新 API/worker。原有 URL、签名校验、取消、版本及 TTL 保持。

### 刮削整体状态与活动时间线

资源任务快照查询新增 `workflow_state` 和 `workflow_stage`，用于包含翻译子任务的整体展示：历史 Redis 任务的原始 `state=succeeded` 仍只表示资源已保存；翻译 queued / translating / unknown 时整体 running，completed 时 succeeded，failed 时 failed，skipped / not_requested 时允许结束。旧任务 unavailable 保留保存结果并明确标注翻译未记录或已过期。前端统计、筛选及“已结束任务”清理按整体状态执行，失败包含翻译失败。

新增 `timeline` 数组，元素为 `{stage, state, at}`，记录实际状态 / 阶段进入时间；`at` 为 Unix 秒或翻译完成的 ISO 时间。资源保存事件为 resource_saved，翻译终态为 translation_completed / translation_failed / translation_skipped。翻译详情可返回 `completed_at`（Celery date_done；提交失败使用失败发生时间）。未记录的历史时间为空，不根据资源的其他翻译结果或当前读取时间推断。字段只在持有签名令牌的完整快照接口返回，不扩大全局 WebSocket 数据。

### 持久下载任务控制（P3）

`POST /nassav/api/downloads/{avid}` 和批量提交新增 `job_id`，保留原 `task_id`；先保存待派发 attempt，broker 不可用仍接受为 202 并保留 pending，不伪造已经开始。TaskJob 是控制/历史所有者，Redis 只投影运行队列和进度；暂停保留同类型 AVID 去重名额，恢复产生新 task_id。

- `GET /nassav/api/tasks/jobs?page=1&page_size=50`：只读取本人任务，管理员可读全部；page_size 1–100、page 正整数。返回 `{jobs, pagination: {page, page_size, total, has_more}}`，未结束任务先于终态，各组按创建时间倒序，私有字段裁剪与详情相同。
- `POST /nassav/api/tasks/jobs/actions`：`{action: pause|resume|cancel|cleanup_retry, request_id: UUID, items: [{job_id: UUID, expected_version: 正整数}]}`，1–100 项且不重复。HTTP 202 返回 `{results: [{job_id, code, message, job}]}`；逐项权限、版本和控制结果，403/404 不含快照；409 附授权的当前快照。沿用单条命令幂等，部分失败不回滚其他项，500 的确认未知可用原 request_id 重试。
- `GET /nassav/api/tasks/jobs/{job_id}`：操作人自身或管理员读取，返回 state/stage/version/generation、timeline、allowed_actions、progress 和 cleanup_state/message；不返回 checkpoint、URL、AES key 或私有路径。
- `POST /nassav/api/tasks/jobs/{job_id}/{pause|resume|cancel}`：operator session 和 CSRF，携带 `{expected_version: 正整数, request_id: UUID}`。返回 202 的已登记快照，不把 pausing/cancelling 当作停止确认。重复 request_id 不重复派发；版本/状态冲突 409 并附当前快照，越权 403，任务不存在 404，输入无效 400。
- `POST /nassav/api/tasks/jobs/{job_id}/cleanup/retry`：相同请求字段，只重试终态 failed 清理，不能复活任务。

RESTART_REQUIRED 的 paused 任务不能 resume，需终止后重新下载；它表示轨道/内容无法确认，不是下载成功。终止只清理本任务私有目录，保留正式视频和共享资产。控制适用于新增 download 及包含关联翻译的 scrape；旧无 job_id 的任务不具控制契约。Channels 的 task_job_update 只含 job_id/job_type/version，前端应授权取快照后按版本合并，不能按 AVID 把旧事件覆盖新任务。

### 持久刮削与翻译控制（任务控制 P5）

登录资源提交改为持久 TaskJob/Attempt，绑定操作者；响应新增稳定 job_id，当前 task_id 随恢复及父子交接变化。保留 status_url/status_token，原签名查询 URL 可以定位原 attempt 所属 job，返回最新整体快照。恢复使用新的登录控制入口，不依赖旧 token 有效期。旧令牌只授予读取能力，不能控制他人任务。

broker 失败保留 pending 并接受为 202，不伪造开始；状态存储故障才返回 503。重复自身活动任务返回 duplicate，即使资源已经保存；其他操作者提交同 AVID 返回 403。批量成功项新增 job_id，失败独立报告，状态集合增加 403。暂停持有同类型 AVID 名额且没有 Redis 的 24 小时 TTL。

新快照 state/workflow_state 表示包含所属翻译的整体状态，resource_saved 单独表示已有保存结果；翻译失败整体 failed，已保存资源保留。resource 返回裁剪的原始/来源/译后标题，未保存时可从已解析检查点获取标题，不暴露 HTML/URL。所属翻译的排队、执行、暂停、终止、完成/失败写入 DB 及 timeline，当前 stage 独立记录；翻译被新请求替代为 TRANSLATION_SUPERSEDED，不覆盖新译文。旧任务继续上文 Redis/Celery 结果合成，不具暂停/终止契约。

恢复不重做已保存资源；仅重翻译 refresh 不抓取来源或图片。add 维持取得元数据才自动翻译的规则，refresh 仅 retranslate=true 请求翻译。受控任务保留原译文到新结果提交；同步重新翻译仍先清空并重置 pending。新单条派发携带 expected_generation；批量 task 可携带 expected_generations，旧消息必须按部署说明排空。结果和异常收尾都校验资源 generation/owner，不能伤及较新的手动/批量翻译。见[所属翻译架构](task-control-architecture.md)。

任务停止异常的恢复提示：WORKER_INTERRUPTED 表示原执行器退出已确认并保留 paused 检查点，可按 allowed_actions 恢复；RECOVERY_UNCONFIRMED 表示身份未知，不能声称已停止或清理。ASSET_RECOVERY_PENDING 表示已停止，但文件提升日志尚未恢复，暂时禁止恢复；后台重试。清理失败仍独立使用 cleanup_state/cleanup_message，不改变 succeeded/failed/cancelled。维护命令的人工退出确认不对 HTTP 开放。

任务列表 `GET /api/tasks/jobs` 可选 `ordering=-created_at|-updated_at`，均为全列表降序并在数据库排序后分页，禁止升序或其他字段（400）。省略时保留活动任务优先、创建时间降序的旧行为；权限过滤保持。

下载恢复校验持续网络超时返回持久任务 `state: paused`、`error_code: RESUME_VALIDATION_TIMEOUT`，保留未提交产物及 resume/cancel 动作。它不表示下载器已经启动或视频已完成；同 job/new attempt 重试核对当前播放列表/轨道/密钥身份及本地缓存哈希，不重新下载已缓存分片。校验通过后由 CLI 复用完整分片，仅下载缺失或损坏分片。相同 URL 下服务器替换字节而播放列表及密钥不变的情况无法检出；身份变化或不支持的轨道仍返回 RESTART_REQUIRED。

持久任务的当前架构、执行归属、资产提交及扩展检查清单见[任务控制架构](task-control-architecture.md)。历史阶段的迁移/部署状态只代表记录当时；本轮验收确认及仍需独立验证的范围以[部署与验证边界](compose-deployment.md#近期改动与验证边界)为准。

## 推荐任务（异步）

- `POST /api/recommendations/jobs`：参数沿用推荐接口的偏好、分页预算和刷新选项，
  返回 202。数量参数有明确上限，无效参数返回 400。
- `GET /api/recommendations/jobs/{job_id}`：返回创建者的任务快照；其他用户返回 404。
- `POST /api/recommendations/jobs/{job_id}/cancel`：幂等取消；已结束任务返回原终态。

响应 data 包含 `job_id`、递增 `version`、`state`、`message`、`allowed_actions`、
`created_at`、`updated_at`。仅 succeeded 携带 `result`，内容沿用推荐 items/seeds/meta。
任务预算 300 秒，包含排队；失败/取消不会保存推荐 snapshot。
旧 GET 推荐接口保留同步兼容，重置历史导致迟到提交被拒绝时返回 409。

## 推荐网络预算与进度（2026-10-07）

生产 DB 推荐 job 保留提交后 300 秒硬期限（含排队），提前 30 秒停止网络工作，
给协作退出、评分和短事务提交预留时间。该软预算独立于取消、归属与硬期限；
只有软预算耗尽允许收尾，取消、失效、硬超时与来源错误不转换为部分成功。
详情按两项业务批次调度，通过公共 ProxyServer 使用实际共享容量；按已有因子预排序、
多样性重排与新鲜度优先选择候选，核验后过滤黑名单，满足目标的新鲜合格数量即可停止。
24 次详情是跨补召回共享的尝试上限，不是必须完成数量；失败尝试不返还预算。
兼容同步 GET 不使用生产 job 软预算，保持原执行范围。

运行快照新增 `progress`（其他状态为 null）：`stage`（recall/details）、
`candidate_count`、`verified_count`、`detail_attempt_count`、`elapsed_seconds`、
`network_remaining_seconds`。协调线程按执行 UUID/running/deadline 条件更新 DB JSON
与 version；进度不产生历史 snapshot，也不提供未经验证的资源或可反馈的历史 item。
`result` 仍仅在 succeeded 时可见。进度随完成批次更新，非固定心跳。

软预算耗尽且已有核验、过滤通过的资源时正常提交部分推荐；结果 meta 新增
`partial`、`completion_reason`（completed/network_budget）、`requested_count`、
`returned_count`。部分结果继续接受最终黑名单检查；即使没有演员/类别黑名单，
预算耗尽后的结果也只能包含详情核验成功的资源。没有合格结果则失败，不保存空成功历史。
数量不足但未耗尽网络预算沿用既有语义，`partial` 专指网络预算收尾。

超时日志记录 job、阶段、异常原因及 DB/网络剩余时间，用于区分硬期限和网络阶段期限；
此前提前约 27 秒失败的确切原因尚未由现有日志证明，不能宣称已定位系统时钟问题。
部署需同步更新 API 与 scrape worker；无需数据库迁移。未重新部署的服务仍使用旧契约。

推荐进度 progress 和结果 meta.verification_context 增加分类统计：
`recalled_count`（本轮唯一召回 AVID）、`detail_success_count`（详情获取并应用成功）、
`blacklist_excluded_count`（召回或详情命中黑名单）、`unverified_count`（保留池未核验）、
`qualified_count`（通过返回条件的候选）。详情尝试数在进度为 detail_attempt_count，
结果同时放在 verification_context 和 effective_request；返回数仍以 meta.returned_count 为准。
黑名单排除数可能包含未获取详情的候选，因此不直接与详情成功数相减求通过率。
候选池大小不等于详情已核验数，未核验不代表失败；旧字段继续保留。

### 持久详情缓存统计

推荐的 progress、effective_request 与 verification_context 可包含 `detail_cache_hit_count` 和 `detail_network_attempt_count`；`detail_attempt_count` 包含缓存及网络详情尝试。缓存命中仍使用当前黑名单与偏好，且不消耗网络详情尝试上限。显式刷新跳过详情缓存。缓存表迁移和时效约定见 [持久抓取缓存](resource-cache-architecture.md)。

### 外部搜索任务结果 TTL

相同查询的已成功任务按 YAML `ExternalSearch.ResultTTLSeconds` 复用，默认 300 秒，0 禁用，最大 86400 秒。强制刷新仍跳过已完成任务；queued/running 仍返回重复任务身份。结果新鲜期以 completed_at 为起点，不因轮询或迟到事件延长，原接口字段和 URL 不变。配置说明见[配置契约](configuration-contract.md)。

### 外部搜索聚合缓存与详情命中

外部搜索默认启用完整聚合结果缓存（ExternalSearch.CacheEnabled=true，AggregateTTLSeconds=300），与 ResultTTLSeconds 独立。结果 meta.cache.enabled/hit/force_refresh 保留，新增 meta.detail_cache_hit_count 表示本轮完整集合命中的有效来源详情数，资源可带 detail_cached。命中仅补缺失标题/封面，不触发逐条详情抓取；该标记不承诺添加阶段缓存仍新鲜。in_library 在查询/分页返回时按当前数据库重新计算，不保存到原站聚合缓存。接口 URL、任务身份、部分进度与分页契约保持不变。

## 在线播放会话与媒体（P1/P2，默认关闭）

控制接口、请求身份、授权及状态见[在线播放契约](online-playback-architecture.md#http-契约)。新增提交、查询、关闭入口；ready 返回签名同源 manifest_url。GET/HEAD /nassav/api/playback-sessions/{session_id}/manifest/{asset_id} 与 assets/{asset_id} 要求当前登录和 cap 签名，支持单段 Range。媒体返回清单/二进制，发送头前错误沿用 JSON 包装，均 no-store；无效签名 403、失效资产 410、容量不足 429、不可用 503、清单不支持 422、非法范围 416。已开始的流失败会断开连接。正式播放器留到 P3。

### 在线播放失效刷新（P4）

`POST /nassav/api/playback-sessions/{session_id}/refresh`：操作者登录和 CSRF，JSON 为 expected_version（正整数）与 request_id（UUID）。202 返回现有会话的新 generation、queued/version/refresh_count；同一命令幂等，不延长绝对期限。版本冲突、已关闭/过期、已刷新或缺少完整兼容基线返回 409。后台仍由 scrape worker 执行，成功读取授权 GET 快照的同源 manifest_url；失败用 preparation_failed 或 media_identity_changed 脱敏说明。公开快照新增 refresh_count，allowed_actions 仅在 ready/未刷新/基线完整时包含 refresh。前端不接收或提交上游 URL。

### 已下载视频播放

`POST /nassav/api/resources/{avid}/playback-sessions` 可选 JSON `mode: "local"`（默认source），与request_id UUID共同定义幂等请求。local直接返回202/ready，不派发抓取；已下载文件缺失404、发布待恢复/锁忙409、非普通文件/内部链接422。GET快照新增mode与media_type；local ready返回签名同源media_url，不返回manifest_url或文件绝对路径。

`GET/HEAD /nassav/api/playback-sessions/{session_id}/file?cap=...`：当前operator登录、会话拥有者及代次签名授权；MP4支持单一bytes Range（206/416及Content-Range）、HEAD、ETag/If-Range，no-store。未登录401、另一登录404、签名错误403、关闭/删除/文件替换410、容量429/503；头发出后失败中断流。local不支持refresh，支持既有close。文件缺失或变化后的GET快照为failed并给脱敏error_code。视频传输不走ProxyServer或Celery。

## 播放进度

新增所属播放会话 progress 查询/保存/claim 和个人资源进度 DELETE，参数、错误码与归属规则见[播放进度架构](playback-progress-architecture.md#接口)。所有接口沿用operator登录、CSRF及no-store，不返回上游地址。

## 个人收藏、观看和备注（第二阶段）

`PATCH /api/resource/{avid}/status` 沿用地址和envelope，仅更新当前登录用户的个人状态。请求可部分提交 `watched`、`is_favorite`（严格JSON布尔值）、`notes`（纯文本，最多5000字符，空字符串清除）、`expected_version`（非负整数）。未知字段（包括user、评分）拒绝；空更新400，资源不存在404，版本冲突409且data返回当前个人快照，前端需保留编辑草稿并重新确认。

成功data为 `{avid, watched, is_favorite, notes, state_version}`。无个人记录为 false/false/空备注/版本0，首写版本1；多个字段一起保存或部分保存均在短事务中完成。资源列表原有 `watched`、`is_favorite` 字段及筛选仍存在，但全部取当前用户投影，并返回 `state_version`；备注仅在详情/状态响应出现。

`GET /api/resource/metadata?avid=...` 包含当前用户状态。ETag同时绑定用户和状态；带Cookie的响应标记private，只有ETag校验可返回304，单独的If-Modified-Since不再验证这组含个人状态的响应。共享元数据Last-Modified继续提供参考，不代表个人状态更新时间。

`GET/PUT /api/setting` 路由和六项字符串字段保持，读取/部分保存均由数据库持有，用户身份来自会话。请求不能指定他人ID；服务器代理、Cookie、来源开关、TTL不属于个人设置。省略外部搜索source时，HTTP按当前用户默认值选择并写入已解析的任务查询；worker不读用户INI。搜索内容缓存仍是共享原站事实，不存个人状态。

登录范围仍限定现有操作者。用户隔离是本阶段的数据边界，不能据此开放所有账号的任务/推荐/媒体权限。

### 用户设置JSON存储（0034）

`GET/PUT /api/setting` 保持原路由与扁平envelope，不要求前端包裹preferences。六项字符串字段名称不变；created_at/updated_at属于持久记录，不新增到当前设置响应。GET按当前定义合并缺省值，不建行、不补写；删除/未知键不返回，非法存储值回退默认值。

PUT仅合并明确提交的当前键；整组提交在写入前严格校验，未知/废弃键、null、错误类型或非法枚举返回400且不部分写入。空对象返回当前有效值且不建行；已有存储值相同不更新时间。缺失项保留隐式默认值，显式保存默认值成为覆盖值。不会按当前版本清除原JSON中的未知键；删除/改名需要显式数据迁移。当前没有键别名或重置接口，null不表示删除。完整行为、导入及回退见[个人状态与设置](personal-state-architecture.md#json设置与0034当前实现)。

## 推荐个人归属（未发布）

推荐job、历史指标、反馈、重置与三类黑名单只读写当前账号；他人snapshot不可反馈，他人job返回404。演员/类别目录共享，屏蔽投影个人化。旧共享数据需显式导入。job提交遗漏偏好或limit时读取个人JSON默认值，明确传参优先，后续设置变化不改变在途job。

GET/PUT `/api/setting`新增recommendation_type_preference（actor_heavy/balanced/genre_heavy）、recommendation_actor_preference及recommendation_genre_preference（familiar/balanced/rare）、recommendation_limit（JSON整数12/24/36）；默认balanced与12。原有六项字符串设置兼容，PUT仅合并提交键。

### 用户播放偏好

GET/PUT `/api/setting`新增playback_volume（JSON数值0–1，默认0.8）、playback_muted（布尔，默认false）、playback_rate（数值0.5/0.75/1/1.25/1.5/1.75/2，默认1）、playback_subtitles_enabled（布尔，默认true）、playback_default_mode（auto/local/source，默认auto）。仅数值项允许整数与小数等价输入，拒绝布尔、字符串、非有限和越界数；默认值补齐不写库，仍只合并提交字段。后端播放会话POST的mode默认仍是source，auto仅为前端入口选模规则。
