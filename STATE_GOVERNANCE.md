# 状态治理方案

本文档用于梳理 NASSAV 当前的运行时状态、持久状态与缓存状态，并给出一版按优先级排序的治理方案。

目标不是“消灭所有状态”，而是明确：

- 哪些数据本来就应该持久化
- 哪些数据只能作为短期缓存存在
- 哪些状态本应无状态，但当前仍滞留在进程内

当前重点关注推荐系统扩展前的治理问题，尤其是 Cookie、一致性和 manager 单例行为。

## 1. 治理原则

### 1.1 状态分类

所有状态统一分为三类：

- `Persistent Truth`
  - 持久真值
  - 以数据库或文件为唯一事实来源
- `Ephemeral Cache`
  - 可丢失缓存
  - 失效后可以重建
- `Process-local Runtime State`
  - 仅存在于当前 Python 进程内的运行态状态
  - 风险最高，因为多进程下容易不一致

### 1.2 设计约束

- manager 应尽量只做调度与组装，不保存业务真值
- 运行时会被用户修改的数据，必须有明确的唯一真值
- 进程内副本如果存在，必须具备刷新机制、失效机制或严格的只读语义
- 推荐结果如果需要保留，必须落表，不进入 `RecommenderManager` 内存

## 2. 当前状态盘点

### 2.1 Persistent Truth

这些状态应该继续持久化：

- `SourceCookie`
  - 源 Cookie 真值
  - 位置：数据库表
- `AVResource / Actor / Genre`
  - 资源与聚合元数据真值
  - 位置：数据库表
- `config/user_settings.ini`
  - 用户显示配置真值
  - 位置：配置文件
- 推荐封面缓存文件
  - 不是业务真值，但属于落盘缓存
  - 位置：`resource/recommendation_cover/`

### 2.2 Ephemeral Cache

这些状态是合理缓存，但需要明确 TTL 和失效策略：

- `source_info:{avid}`
  - SourceManager 的资源信息缓存
- `scraper_metadata:{avid}`
  - ScraperManager 的元数据缓存
- Redis 中的任务进度、队列状态、锁
  - 下载任务运行态缓存
- 推荐封面代理缓存
  - 文件级缓存，可重建

### 2.3 Process-local Runtime State

这些是当前最值得治理的部分：

- `source_manager`
  - 模块级单例
- `SourceManager._cookies_loaded`
  - 只在首次加载 Cookie 时置位
- `SourceBase.cookie`
  - 各 source 实例保留一份进程内 Cookie 副本
- `SourceBase.last_error_code`
  - 最近一次请求错误码，属于请求态信息
- `scraper_manager`
  - 模块级单例
- `ScraperManager._last_successful_scraper`
  - 最近一次成功 scraper，影响后续 `download_cover()` 行为
- `recommender_manager`
  - 当前仅是调度器，状态风险较低
- `UserSettingsManager` 全局单例
  - 依赖内存中的 config 与 mtime 检测

## 3. 核心判断

### 3.1 当前哪些状态“本应无状态，实际有状态”

优先考虑以下对象：

- `SourceManager` / `SourceBase`
  - Cookie 真值在 DB，但内存副本长期存在，且缺少跨进程刷新机制
- `ScraperManager`
  - `_last_successful_scraper` 属于隐式进程状态，不应影响后续独立请求
- `UserSettingsManager`
  - 有文件真值，但仍保留模块级单例缓存

### 3.2 当前哪些状态“有状态是合理的”

- `SourceCookie`
  - Cookie 本来就是运行时可变且需持久化的状态
- 资源数据表
  - 属于业务真值
- Redis 任务状态
  - 属于运行态共享状态
- Django cache / 文件缓存
  - 属于可丢失缓存

### 3.3 推荐系统当前是否违规持有状态

当前 `RecommenderManager` 基本是无状态的：

- 持有的是 builder registry
- 不保存推荐结果
- 不保存用户级偏好状态

因此推荐系统目前不需要先“去状态化”；如果未来要保存推荐结果，应该：

- 新建数据表
- 由 service / repository 层读写
- `RecommenderManager` 继续只负责 orchestration

## 4. 治理优先级

## P0：必须优先治理

### P0-1 Cookie 一致性

问题：

- `SourceCookie` 已持久化，但 `SourceManager` 在进程内维护一份长期 Cookie 副本
- `_cookies_loaded` 导致只加载一次
- 多进程部署下，某个进程更新 Cookie 后，其他进程可能继续使用旧值

目标：

- 明确 DB 为 Cookie 唯一真值
- 进程内 Cookie 仅允许作为短期只读缓存

建议方案：

1. 移除 `SourceManager._cookies_loaded` 的“一次性加载”语义
2. 将 Cookie 获取逻辑改为“按需读取 + 可缓存 + 可失效”
3. 引入 Cookie 版本或更新时间校验
4. `SourceBase.fetch_html()` / `download_file()` 前确保使用最新 Cookie
5. API 更新 Cookie 后主动清理相关 cache

落地方式建议二选一：

- 方案 A：每次请求前从 DB 读取 Cookie
  - 一致性最好
  - 适合低频站点请求
- 方案 B：增加 `CookieRepository + local TTL cache`
  - 例如缓存 30-60 秒
  - 每次请求前校验 TTL，过期则重新读库

推荐先做方案 B。

### P0-2 去除 `ScraperManager._last_successful_scraper`

问题：

- `download_cover()` 当前依赖“最近一次成功的 scraper”
- 该状态属于跨请求漂移状态
- 会让行为依赖历史请求顺序

目标：

- 让 `download_cover()` 的行为只依赖当前输入，而不是前序请求

建议方案：

1. 废弃 `_last_successful_scraper`
2. 将“使用哪个 scraper 下载封面”改为显式传参
3. 如果无法显式传参，则让 `scrape()` 返回 `(metadata, scraper_name)` 或 `(metadata, scraper_instance)`
4. 在当前调用链内透传，不写入 manager 成员变量

## P1：应尽快治理

### P1-1 UserSettingsManager 单例收敛

问题：

- 当前真值在 `user_settings.ini`
- 但存在模块级 `_settings_manager` 单例
- 虽然已有 mtime reload，但仍然是进程内有状态对象

目标：

- 保留文件真值
- 降低单例耦合

建议方案：

1. 保留 `UserSettingsManager`
2. 去掉全局强单例语义，改为轻量工厂或请求内获取
3. 如果继续保留单例，至少明确它只是文件缓存，不是业务真值
4. 所有写入必须立即落盘

### P1-2 Source / Scraper / Recommender Manager 职责边界

问题：

- manager 目前同时承担 registry、实例缓存和部分运行态行为

目标：

- manager 只负责注册和调度
- 运行态数据由 repository / cache / DB 提供

建议方案：

1. manager 内只保留 builder / registry 元数据
2. 请求态状态不要挂到 manager 成员变量
3. 需要共享状态时优先用 DB / Redis / Django cache

## P2：中期治理

### P2-1 推荐结果持久化设计

前提：

- 当前推荐流程基本无状态
- 后续若需要保存推荐结果，不应放入 `RecommenderManager`

建议新增数据表，例如：

- `RecommendationSnapshot`
  - 一次推荐请求的元信息
  - `recommender`
  - `strategy`
  - `request_payload`
  - `seed_summary`
  - `created_at`
- `RecommendationItem`
  - 每条推荐结果
  - `snapshot_id`
  - `avid`
  - `title`
  - `detail_url`
  - `cover_url`
  - `score`
  - `reasons`
  - `matched_seeds`

适用场景：

- 推荐结果审计
- 前端重复查看同一批推荐
- 后续策略效果评估

### P2-2 统一状态字典 / 术语

建议在架构文档中统一以下术语：

- 真值
- 缓存
- 进程内状态
- 请求态状态
- 共享运行态状态

避免未来把“缓存”和“真值”混在一起讨论。

## 5. 建议实施顺序

### 第一阶段

- 处理 Cookie 一致性
- 去掉 `_last_successful_scraper`

### 第二阶段

- 收敛 `UserSettingsManager`
- 收紧 manager 职责边界

### 第三阶段

- 引入推荐结果持久化表
- 补推荐结果缓存与审计机制

## 6. Checklist

### P0 Checklist

- [ ] 明确 `SourceCookie` 是唯一真值
- [ ] 明确 Cookie 进程内副本只是 cache，不是 source of truth
- [ ] 去除 `SourceManager._cookies_loaded` 的一次性加载语义
- [ ] 为 Cookie 增加统一读取入口，不再由各处自行决定何时读库
- [ ] API 更新 Cookie 后，清理对应 source 的进程内缓存 / Django cache
- [ ] 设计并实现 Cookie TTL 或版本校验机制
- [ ] 去除 `ScraperManager._last_successful_scraper`
- [ ] 将 scraper 选择改为请求内显式传递

### P1 Checklist

- [ ] 评估 `UserSettingsManager` 是否保留单例
- [ ] 若保留单例，补充文档说明其仅为文件缓存
- [ ] 梳理 `SourceManager`、`ScraperManager`、`RecommenderManager` 的成员变量
- [ ] 将运行态状态从 manager 成员变量迁出
- [ ] 统一 manager 层“只负责调度”的约束

### P2 Checklist

- [ ] 设计 `RecommendationSnapshot` 表结构
- [ ] 设计 `RecommendationItem` 表结构
- [ ] 明确推荐结果保存时机
- [ ] 明确推荐结果保留时长和清理策略
- [ ] 评估是否需要为推荐结果建立去重键
- [ ] 为推荐结果回放、对比和调试预留字段

## 7. 对齐结论

本轮治理优先级的结论如下：

1. 先不要动推荐结果存储
2. 先解决 Cookie 一致性问题
3. 再清理 manager 的隐式进程状态
4. 最后再引入推荐结果表

这样做的原因是：

- Cookie 问题会直接影响线上行为正确性
- manager 隐式状态会影响多进程一致性
- 推荐结果持久化属于能力扩展，不是当前最危险的问题
