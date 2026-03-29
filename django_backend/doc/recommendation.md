# Recommendation Overview

本文档说明当前后端推荐系统的设计、组件职责、API 入口与一次请求的完整调用过程。

当前实现目标是一个可扩展的 demo 推荐链路：

- 基于本地库中高频出现的演员与类别生成推荐种子
- 使用 Jable 搜索页召回候选资源
- 过滤本地已存在资源
- 过滤最近同配置已经推荐过的资源
- 对候选进行轻量打分并返回给前端
- 将每次推荐结果持久化为 snapshot，便于回放、审计与后续策略优化

## Scope

- 当前唯一的 recommender：`jable_search`
- 当前内置 strategy：
  - `local_preference`
  - `balanced`
  - `actor_heavy`
  - `recent_favorite`
- 当前唯一的外部召回源：`Jable.search()`

当前实现强调“层次分离”和“后续可扩展”，因此 API 层不直接绑定具体 recommender。

## Main Layers

### 1. API Layer

API 层只负责：

- 解析 Query 参数
- 调用 `RecommenderManager`
- 返回统一 envelope 响应

当前接口：

- `GET /nassav/api/recommendations/`
  - 统一推荐接口
  - 支持参数：
    - `recommender`
    - `strategy`
    - `limit`
    - `per_seed_limit`
    - `actor_seed_limit`
    - `genre_seed_limit`
    - `exclude_existing`
    - `avoid_recent_recommendations`
    - `recent_snapshot_limit`
    - `recent_item_limit`

- `GET /nassav/api/recommendations/options`
  - 返回当前可用的 recommenders、strategies 与默认值

- `GET /nassav/api/recommendations/cover`
  - 代理并缓存推荐封面
  - 用于前端加载 Jable 推荐封面，避免直接访问受限站点资源

- `GET /nassav/api/recommendations/demo`
  - 兼容性的 demo 入口
  - 当前内部同样走 `RecommenderManager`

对应文件：

- `nassav/views.py`
- `nassav/urls.py`

### 2. Manager Layer

`RecommenderManager` 是推荐系统的中间调度层，作用类似现有的 `SourceManager` / `ScraperManager`。

它负责：

- 注册可用 recommender
- 注册可用 strategy
- 校验 recommender 和 strategy 是否兼容
- 合并 strategy 默认参数和请求参数
- 构造 `RecommendationRequest`
- 构造请求指纹并读取最近推荐历史
- 实例化具体 recommender
- 执行推荐并返回统一结果结构
- 持久化推荐 snapshot 与 item

当前 manager 实现在：

- `nassav/recommendation/manager.py`

### 3. Strategy Layer

`RecommendationStrategy` 描述“推荐配置”，而不是单个算法函数。

它负责定义：

- strategy 标识与说明
- 支持哪些 recommender
- 使用哪个 `SeedProvider`
- 使用哪些 `RecommendationFactor`
- 默认请求参数覆盖项

当前内置 strategy：

- `local_preference`
  - `seed_provider`: `LocalPreferenceSeedProvider`
  - `factors`:
    - `SeedWeightFactor`
    - `MultiSeedBonusFactor`
    - `SearchRankFactor`
    - `PopularityFactor`
  - 默认参数：
    - `limit=12`
    - `per_seed_limit=12`
    - `actor_seed_limit=5`
    - `genre_seed_limit=5`
    - `seed_types=["actor", "genre"]`
    - `exclude_existing=true`

- `balanced`
  - 更均衡地使用 actor / genre 偏好
  - 启用更强的多样性重排，减少结果扎堆

- `actor_heavy`
  - 提高 actor 命中的权重
  - 降低 genre 命中的影响

- `recent_favorite`
  - 优先使用最近新增、已观看、已收藏资源生成种子
  - 当交互种子为空时回退到全量本地偏好

对应文件：

- `nassav/recommendation/strategies.py`

### 4. Recommender Layer

`AbstractRecommender` 定义推荐主流程模板，具体 recommender 只需要实现关键步骤。

当前唯一具体实现：

- `JableSearchRecommender`

它只依赖 `Jable`，不直接依赖 `ScraperManager`。

职责：

- 从 `SeedProvider` 获取推荐种子
- 对每个 seed 调用 `Jable.search()`
- 合并重复候选
- 过滤数据库中已存在的 `AVResource`
- 执行 factors 打分
- 返回排序后的推荐结果

对应文件：

- `nassav/recommendation/base.py`
- `nassav/recommendation/jable_search.py`

### 5. Source / Recall Layer

`Jable` 负责访问 Jable 站点并解析搜索结果页面。

当前使用的方法：

- `Jable.search(keyword, page=1)`

返回字段统一为：

```json
[
  {
    "avid": "FSDSS-717",
    "title": "...",
    "detail_url": "https://jable.tv/videos/fsdss-717/",
    "cover_url": "https://assets-cdn.jable.tv/...",
    "source": "Jable",
    "metrics": {
      "views": 3290381,
      "likes": 9370,
      "duration": "2:00:15"
    }
  }
]
```

对应文件：

- `nassav/source/Jable.py`

## Domain Objects

推荐系统内部主要使用以下对象：

- `RecommendationSeed`
  - 表示一个推荐种子
  - 例如：
    - `actor = Alice`
    - `genre = 中文字幕`

- `RecommendationCandidate`
  - 表示一个待打分候选
  - 保存 `avid`、标题、封面、命中的种子、原始热度指标、分数分解等

- `RecommendationRequest`
  - 表示一次推荐请求的参数
  - 除基础分页/seed 参数外，还包含：
    - `random_seed`
    - `avoid_recent_recommendations`
    - `recent_snapshot_limit`
    - `recent_item_limit`
    - `recently_recommended_avids`

- `RecommendationRun`
  - 表示 recommender 的原始执行结果

- `RecommendationExecution`
  - 表示经过 manager 调度后的最终执行结果
  - 在 `RecommendationRun` 外增加：
    - `snapshot_id`
    - `request_fingerprint`
    - `recommender`
    - `strategy`
    - `recommender_detail`
    - `strategy_detail`
    - `effective_request`
    - `history_context`

对应文件：

- `nassav/recommendation/entities.py`

## Snapshot Persistence

推荐系统现在会为每次请求保存一份 snapshot。

- `RecommendationSnapshot`
  - 保存推荐器、策略、请求指纹、请求参数、seed 摘要、返回数量、随机种子和生成时间
- `RecommendationItem`
  - 保存某次 snapshot 中的每一条推荐结果
  - 包含排名、`avid`、标题、封面、分数、理由、命中的 seeds、分数分解和原始热度指标

当前用途：

- 为“刷新推荐”提供历史过滤依据
- 为后续比较不同策略/因子效果提供审计数据
- 为未来增加推荐回放与缓存能力预留基础

对应文件：

- `nassav/models.py`
- `nassav/recommendation/repository.py`

## Seed Generation

当前种子生成逻辑来自本地数据库聚合：

- 演员种子：
  - `Actor.objects.annotate(resource_count=Count("resources"))`
  - 取出现次数最高的演员

- 类别种子：
  - `Genre.objects.annotate(resource_count=Count("resources"))`
  - 取出现次数最高的类别

权重归一化规则：

- `LocalPreferenceSeedProvider` 会综合以下信号计算 `preference_score`
  - `resource_count`
  - `watched_count`
  - `favorite_count`
  - `recent_count`
- 不同 strategy 通过调整：
  - `watched_boost`
  - `favorite_boost`
  - `recent_boost`
  - `recent_days`
  - `only_interacted`
    来改变 seed 排序结果
- 使用当前批次最大 `preference_score` 作为分母
- 归一到 `0 ~ 5` 区间

对应文件：

- `nassav/recommendation/seeds.py`

## Scoring Factors

当前评分较轻量，主要用于 demo 排序。

### `SeedWeightFactor`

- 作用：把命中的种子权重累加到候选分数上
- 结果示例：
  - `命中高频actor: Alice`
  - `命中高频genre: 中文字幕`

### `MultiSeedBonusFactor`

- 作用：同一个候选命中多个种子时追加 bonus

### `SearchRankFactor`

- 作用：利用 Jable 搜索结果中的卡片位置做弱加分
- 结果越靠前，bonus 越高

### `PopularityFactor`

- 作用：利用 Jable 搜索卡片中的：
  - `views`
  - `likes`
    做弱加分

### `NoveltyFactor`

- 作用：基于最近推荐历史做新颖度调节
- 若候选近期未在推荐历史中出现，则给予轻微 bonus
- 若候选已经在最近的推荐 snapshots 中多次出现，则给予惩罚
- 同时会结合本次 `random_seed` 注入小幅探索噪声，避免不同策略或连续刷新时长期完全同序

对应文件：

- `nassav/recommendation/factors.py`

## API Design

### 1. `GET /nassav/api/recommendations/`

功能：统一推荐入口。

请求参数：

- `recommender`: 可选，默认 `jable_search`
- `strategy`: 可选，默认 `local_preference`
- `limit`: 可选
- `per_seed_limit`: 可选
- `actor_seed_limit`: 可选
- `genre_seed_limit`: 可选
- `exclude_existing`: 可选，默认 `true`
- `avoid_recent_recommendations`: 可选，默认 `true`
- `recent_snapshot_limit`: 可选，默认 `3`
- `recent_item_limit`: 可选，默认 `36`

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "avid": "REC-001",
        "title": "Alice Result",
        "detail_url": "https://jable.tv/videos/rec-001/",
        "cover_url": "https://img/rec-001.jpg",
        "source": "Jable",
        "score": 10.5,
        "reasons": ["命中高频actor: Alice", "命中高频genre: 中文字幕"]
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
      "seed_count": 2,
      "item_count": 1
    },
    "meta": {
      "recommender": "jable_search",
      "strategy": "local_preference",
      "snapshot_id": 12,
      "request_fingerprint": "e6fd...",
      "recommender_detail": {
        "id": "jable_search",
        "name": "Jable Search",
        "description": "通过 Jable 搜索页召回候选资源。"
      },
      "strategy_detail": {
        "id": "local_preference",
        "name": "Local Preference",
        "description": "基于本地高频演员与类别的 Jable 搜索推荐 demo。",
        "supported_recommenders": ["jable_search"],
        "default_request_overrides": {
          "limit": 12,
          "per_seed_limit": 12,
          "actor_seed_limit": 5,
          "genre_seed_limit": 5,
          "seed_types": ["actor", "genre"],
          "exclude_existing": true
        }
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
        "recent_item_limit": 36
      },
      "history_context": {
        "recently_recommended_count": 12,
        "recent_history_candidate_count": 18,
        "filtered_history_count": 4
      }
    }
  }
}
```

### 2. `GET /nassav/api/recommendations/options`

功能：返回当前可选的 recommender / strategy / defaults，便于前端动态渲染筛选项。

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "defaults": {
      "recommender": "jable_search",
      "strategy": "local_preference"
    },
    "recommenders": [
      {
        "id": "jable_search",
        "name": "Jable Search",
        "description": "通过 Jable 搜索页召回候选资源。",
        "strategies": ["local_preference", "balanced", "actor_heavy", "recent_favorite"]
      }
    ],
    "strategies": [
      {
        "id": "local_preference",
        "name": "Local Preference",
        "description": "基于本地高频演员与类别的 Jable 搜索推荐 demo。",
        "supported_recommenders": ["jable_search"],
        "default_request_overrides": {
          "limit": 12,
          "per_seed_limit": 12,
          "actor_seed_limit": 5,
          "genre_seed_limit": 5,
          "seed_types": ["actor", "genre"],
          "exclude_existing": true
        }
      },
      {
        "id": "actor_heavy",
        "name": "Actor Heavy",
        "description": "以演员命中为主，类别只作为弱召回信号，适合演员偏好明显的库。",
        "supported_recommenders": ["jable_search"]
      }
    ]
  }
}
```

### 3. `GET /nassav/api/recommendations/cover`

功能：后端代理并缓存推荐封面。

请求参数：

- `url`: 原始封面地址

说明：

- 当前只允许 Jable 相关域名的封面地址
- 服务端会将图片缓存在 `resource/recommendation_cover/`
- 该接口与现有资源封面接口 `GET /nassav/api/resource/cover` 分离，避免和本地资源封面混淆

### 4. `GET /nassav/api/recommendations/demo`

功能：兼容历史 demo 调用方式。

说明：

- 当前并不直接构建 recommender
- 内部仍然转发到 `RecommenderManager.recommend()`
- 使用默认：
  - `recommender=jable_search`
  - `strategy=local_preference`

## Call Flow

以下是一次 `GET /nassav/api/recommendations/` 请求的完整调用过程。

### Step 1. View 接收请求

- `RecommendationsView.get()`
- 读取：
  - `recommender`
  - `strategy`
  - 各种 limit 参数
  - `exclude_existing`
  - `avoid_recent_recommendations`

### Step 2. View 调用 `RecommenderManager`

- `recommender_manager.recommend(...)`

manager 内部依次执行：

1. 解析 recommender id
2. 解析 strategy id
3. 读取 strategy 定义
4. 校验 strategy 是否支持该 recommender
5. 合并 strategy 默认参数和请求参数
6. 构造 `RecommendationRequest`
7. 生成 `request_fingerprint`
8. 根据同一组配置对应的最近 snapshots，读取需要回避的 `avid`
9. 构造具体 recommender

### Step 3. Recommender 执行主流程

`AbstractRecommender.recommend()` 的固定流程为：

1. `build_seeds()`
2. `recall_candidates()`
3. `filter_existing_resources()`
4. `enrich_candidates()`
5. `score_candidates()`
6. `rank_and_trim()`

当前 `enrich_candidates()` 仍为 no-op，保留为后续扩展点。

### Step 4. SeedProvider 生成种子

`LocalPreferenceSeedProvider`：

- 从本地 `Actor` 聚合得到 top actors
- 从本地 `Genre` 聚合得到 top genres
- 综合观看、收藏和近期新增信号计算 `preference_score`
- 生成 `RecommendationSeed[]`

### Step 5. Jable 搜索召回

`JableSearchRecommender.recall_by_seed()`：

- 对每个 seed 调用 `Jable.search(seed.value, page=1)`
- 将搜索卡片映射为 `RecommendationCandidate`
- 每个候选记录自己命中了哪些种子
- 同时记录候选在搜索结果中的最佳 `search_rank`

### Step 6. 合并重复候选

如果多个 seed 都召回了同一 `avid`：

- 按 `avid` 去重
- 合并 `matched_seeds`
- 合并 `raw_metrics`

### Step 7. 过滤本地已存在资源

`AbstractRecommender.filter_existing_resources()`：

- 批量查询 `AVResource.avid`
- 去掉本地库中已经存在的资源
- 若当前请求开启历史过滤，则优先去掉最近同配置已经推荐过的 `avid`
- 若过滤后没有剩余候选，则回退到未做历史过滤的结果，避免直接返回空列表

此外，manager 会额外读取同一 recommender 下最近若干次推荐的 `avid` 频次，并通过 `NoveltyFactor` 在打分阶段做跨策略的重复惩罚与新颖度加分。

### Step 8. 执行 factor 打分

对每个候选执行当前 strategy 配置的全部 factor：

- `SeedWeightFactor`
- `MultiSeedBonusFactor`
- `SearchRankFactor`
- `PopularityFactor`

最终得到：

- `total_score`
- `score_breakdown`
- `reasons`

### Step 9. 排序与裁剪

- 先按 `total_score` 和 `search_rank` 做基础排序
- 再执行一次基于 seed 重复度的多样性重排，减少相同 actor / genre 扎堆
- 截断为 `limit`

### Step 10. 返回 API 响应

manager 会在返回前保存 `RecommendationSnapshot` 与 `RecommendationItem`，并将：

- `snapshot_id`
- `request_fingerprint`
- `history_context`

封装进 `meta`，最终由 view 返回统一 envelope。

## Current Extension Points

当前设计已经预留以下扩展点：

- 新增 recommender
  - 例如：`jable_actor_page`
  - 例如：`hybrid_search`

- 新增 strategy
  - 例如：`actor_heavy`
  - 例如：`fresh_first`

- 新增 seed provider
  - 例如：只基于收藏资源生成种子
  - 例如：只基于最近观看记录生成种子

- 新增 factor
  - 例如：发布日期加分
  - 例如：演员精确匹配 bonus

- 新增 enrich 阶段
  - 例如：补抓详情页
  - 例如：使用 scraper 做进一步校验

## Current Limitations

- 当前只有一个 recommender
- 当前召回完全依赖 Jable 搜索页
- 当前类别种子直接用站内搜索词匹配，精度有限
- 当前只对推荐封面做了缓存，推荐结果本身尚未做 snapshot 级缓存复用
- 当前已经有结果持久化，但还没有单独的 snapshot 查询 / 回放接口
- 当前没有分页式多页召回
- 当前跨策略差异化仍以历史惩罚和轻量探索为主，还没有真正的多臂 bandit / 学习排序
- 当前 `demo` 接口仍保留，后续前端迁移完成后可考虑收敛

## Related Files

- `nassav/source/Jable.py`
- `nassav/recommendation/cover_cache.py`
- `nassav/recommendation/entities.py`
- `nassav/recommendation/base.py`
- `nassav/recommendation/seeds.py`
- `nassav/recommendation/factors.py`
- `nassav/recommendation/strategies.py`
- `nassav/recommendation/jable_search.py`
- `nassav/recommendation/manager.py`
- `nassav/recommendation/repository.py`
- `nassav/views.py`
- `nassav/urls.py`
