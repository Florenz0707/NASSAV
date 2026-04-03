# Recommendation Overview

本文档说明当前后端实际生效的推荐机制实现。内容以 `django_backend/nassav/recommendation/`、`nassav/views.py` 与现有测试为准，不再保留历史方案设想。

## 当前实现结论

当前后端只提供一条推荐链路：

- recommender: `jable_page_lookup`
- strategy: `local_preference`
- 召回源：
  - 本地库偏好种子
  - Jable actor/model 页
  - Jable genre tag/category 页
  - 搜索页回退召回
  - Jable 热榜与最近更新 discovery 页

推荐流程概括如下：

1. 从本地 `AVResource` 统计 actor / genre 偏好，生成推荐种子
2. 优先走 Jable 映射页召回，不足时回退搜索页
3. 额外引入 Jable 热榜与最近更新作为 discovery 候选
4. 过滤本地已存在资源与被负反馈屏蔽的 `avid`
5. 如果候选仍不足，则继续向低位种子扩展召回
6. 对候选做历史避让、打分、去重和多样性重排
7. 持久化 snapshot / items，供下次历史避让与审计使用

## API

### 1. `GET /nassav/api/recommendations/`

统一推荐接口。

当前支持的 query 参数：

- `strategy`
  - 当前仅支持 `local_preference`
- `limit`
- `per_seed_limit`
- `actor_seed_limit`
- `genre_seed_limit`
- `exclude_existing`
- `avoid_recent_recommendations`
- `recent_snapshot_limit`
- `recent_item_limit`
- `include_hot_board`
- `include_latest_updates`
- `discovery_limit`
- `type_preference`
  - `actor_heavy | balanced | genre_heavy`
- `actor_preference`
  - `familiar | balanced | rare`
- `genre_preference`
  - `familiar | balanced | rare`

注意：

- 当前接口没有开放 `recommender` 参数
- 实际固定使用 `jable_page_lookup`

### 2. `GET /nassav/api/recommendations/options`

返回当前默认配置、可用 recommender 和 strategy。

当前返回结果中：

- `defaults.recommender = jable_page_lookup`
- `defaults.strategy = local_preference`

### 3. `GET /nassav/api/recommendations/demo`

兼容性 demo 入口。

- 内部仍然直接转发到 `recommender_manager.recommend()`
- 与 `/api/recommendations/` 使用同一条默认推荐链路

### 4. `POST /nassav/api/recommendations/feedback`

记录推荐反馈。

当前 API 层只接受：

- `feedback = dislike`

请求体：

```json
{
  "snapshot_id": 12,
  "avid": "ABCD-123",
  "feedback": "dislike"
}
```

效果：

- 为对应 `RecommendationItem` 记录负反馈
- 后续推荐时，该 `avid` 会被直接屏蔽

### 5. `POST /nassav/api/recommendations/reset`

清空推荐状态：

- `RecommendationSnapshot`
- `RecommendationItem`
- `RecommendationFeedback`

### 6. `GET /nassav/api/recommendations/cover`

代理并缓存推荐封面，避免前端直接访问受限站点资源。

## 代码分层

### 1. API 层

文件：

- `nassav/views.py`
- `nassav/urls.py`

职责：

- 解析 query/body 参数
- 调用 `recommender_manager`
- 返回统一响应结构

### 2. Manager 层

文件：

- `nassav/recommendation/manager.py`

职责：

- 维护 recommender / strategy 注册表
- 构造 `RecommendationRequest`
- 计算请求指纹
- 读取近期推荐历史与种子历史
- 读取负反馈学习结果
- 构造具体 recommender
- 执行推荐
- 持久化 snapshot 与 item

当前注册表非常简单：

- recommender:
  - `jable_page_lookup`
- strategy:
  - `local_preference`

### 3. Strategy 层

文件：

- `nassav/recommendation/strategies.py`

`RecommendationStrategy` 负责描述一套“推荐配置”，包括：

- 种子提供器
- 打分因子
- 默认请求参数
- recommender 额外参数
- 参数说明元数据 `parameter_profile`

当前唯一 strategy 为 `local_preference`，关键配置如下：

- 默认请求：
  - `limit=12`
  - `per_seed_limit=12`
  - `actor_seed_limit=5`
  - `genre_seed_limit=5`
  - `seed_types=["actor", "genre"]`
  - `exclude_existing=true`
  - `include_hot_board=true`
  - `include_latest_updates=true`
  - `discovery_limit=12`
- 多样性重排参数：
  - `diversity_penalty=0.72`
  - `actor_diversity_weight=1.0`
  - `genre_diversity_weight=0.72`

### 4. Recommender 层

文件：

- `nassav/recommendation/base.py`
- `nassav/recommendation/jable_search.py`
- `nassav/recommendation/jable_page_lookup.py`

当前实际使用的类是 `JablePageLookupRecommender`，它继承自 `JableSearchRecommender`，在 `recall_by_seed()` 中采用如下优先级：

1. actor 种子先尝试 Jable model 页
2. genre 种子先尝试 Jable tag/category 页
3. 若页映射召回不到结果，再按种子值与别名搜索

`JableSearchRecommender.recommend()` 的完整执行顺序为：

1. `build_seeds()`
2. 计算种子出现档位 `seed_occurrence_tiers`
3. `recall_candidates()`
4. 过滤本地已有资源
5. 过滤被负反馈屏蔽的资源
6. 若“优先候选”不足，扩展种子池并再次召回
7. 再次过滤本地已有资源与负反馈屏蔽资源
8. 再次刷新种子档位
9. 做近期推荐避让
10. `enrich_candidates()`，当前未做额外 enrich
11. `score_candidates()`
12. `rank_and_trim()`

其中 `rank_and_trim()` 又分为：

1. 先按 `total_score desc`、`search_rank asc`、`random_seed` 稳定排序
2. 再做多样性重排 `rerank_candidates()`
3. 最后把“新候选”放到“近期已推荐候选”前面
4. 截断到 `limit`

## 种子生成机制

文件：

- `nassav/recommendation/seeds.py`

当前只使用 `LocalPreferenceSeedProvider`。

### 偏好来源

种子来自本地库中的 `Actor` 与 `Genre` 统计，并对每个标签计算偏好分数：

- `resource_count`
- `watched_count`
- `favorite_count`
- `recent_count`

偏好分受以下参数影响：

- `watched_boost = 0.75`
- `favorite_boost = 1.15`
- `recent_boost = 0.9`
- `recent_days = 160`

### 种子选择

生成种子时会：

- 按偏好分排序
- 将同类种子拆为 `high / mid / low` 三档
- 根据前端传入的 `actor_preference` 与 `genre_preference`，从三档中按比例选种子
- 使用 `recent_seed_counts` 对近期反复暴露过的种子施加轮换抑制

当前三档偏好模式：

- `familiar`
  - 更偏向高频种子
- `balanced`
  - 高频、中频、低频相对均衡
- `rare`
  - 更偏向低频种子

### 映射与别名

actor / genre 种子会尽量复用映射信息：

- actor:
  - 读取 `ActorSourceMapping`
  - 携带 `model_slug`、源站名称、演员别名
- genre:
  - 读取 `GenreSourceMapping`
  - 携带 `genre_slug` 与 taxonomy 信息

actor 种子还会自动提取别名，用于搜索回退时提升召回率。

## 候选召回机制

文件：

- `nassav/recommendation/jable_search.py`
- `nassav/recommendation/jable_page_lookup.py`
- `nassav/source/Jable.py`

### 1. 按种子召回

每个种子独立召回候选。

actor 种子：

- 若存在 Jable `model_slug`，优先调用 `get_model_videos()`
- 否则按 `seed.value + aliases` 依次调用 `search()`

genre 种子：

- 若存在 genre 映射，优先调用 `get_tag_videos()` 或 `get_category_videos()`
- 否则按关键词调用 `search()`

翻页规则：

- actor/model 页、genre 页、搜索页都支持最多 `max_pages_per_query=5` 页
- 每轮召回遇到无新结果或达到目标数即停止

### 2. Discovery 补充召回

除种子召回外，还会补充 discovery 候选：

- `discover_hot_items()`
- `discover_latest_updates()`

控制参数：

- `include_hot_board`
- `include_latest_updates`
- `discovery_limit`

命中 discovery 的候选会在 `raw_metrics.discovery_sources` 中记录来源，供后续打分。

### 3. 候选合并

候选按 `avid` 合并。

合并时会：

- 合并 `matched_seeds`
- 合并 `raw_metrics`
- 保留更小的 `search_rank`
- 补齐标题、详情页、封面等基础字段

### 4. 候选补量

如果过滤后“优先候选”仍不足 `limit`，系统会继续：

- 从 `SeedProvider.get_additional_seeds()` 获取额外种子
- 再做最多 3 轮扩展召回

这里的“优先候选”指：

- 当开启近期避让时，优先统计“不在最近推荐历史里的候选”
- 当未开启近期避让时，统计全部候选

## 过滤与历史避让

### 1. 过滤本地已存在资源

`exclude_existing=true` 时，会查询 `AVResource.avid`，剔除本地已存在条目。

### 2. 过滤负反馈资源

当前学习机制非常直接：

- 仅统计 `dislike`
- 只做 `avid` 级黑名单
- 不做 seed 级正负反馈学习

实现位置：

- `nassav/recommendation/feedback.py`

`build_learning_profile()` 当前返回：

- `blocked_avids`
- `feedback_count`

manager 会把 `blocked_avids` 写入 `RecommendationRequest.blocked_feedback_avids`，后续在召回后立即过滤。

### 3. 同配置近期避让

`avoid_recent_recommendations=true` 时，manager 会基于以下条件读取最近推荐结果：

- 同一 `recommender_id`
- 同一 `strategy_id`
- 同一 `request_fingerprint`

随后将这些 `avid` 写入 `recently_recommended_avids`。

过滤策略不是“硬剔除到底”，而是：

- 先尽量保留新候选
- 如果新候选已经足够 `limit`，则完全不返回历史候选
- 如果新候选不够，则允许近期候选回填补位

因此该逻辑更接近“优先避让”，不是绝对屏蔽。

### 4. 跨请求重复惩罚

除了同配置避让之外，manager 还会读取：

- `recent_recommendation_counts`
  - 同一 recommender 下最近若干个 snapshot 中，各 `avid` 的出现次数
- `recent_seed_counts`
  - 同一 recommender 下最近若干个 snapshot item 中，各 seed 的出现次数

这些历史统计会参与：

- `NoveltyFactor`
- `SeedWeightFactor` 中的轮换抑制

## 打分机制

文件：

- `nassav/recommendation/factors.py`

当前 `local_preference` 使用以下 factor：

### 1. `SeedWeightFactor`

基础作用：

- 根据命中的 seed 权重加分

同时叠加四类乘数：

- actor / genre 基础乘数
- `type_preference` 类型偏好乘数
- `actor_preference` / `genre_preference` 对应的高中低频档位乘数
- 基于 `recent_seed_counts` 的轮换抑制乘数

### 2. `MultiSeedBonusFactor`

若候选同时命中多个种子，按数量追加加分。

### 3. `SearchRankFactor`

按 `search_rank` 提供线性衰减加分，排序越靠前分越高。

### 4. `PopularityFactor`

根据 `views` 和 `likes` 提供热度分，分值有上限。

### 5. `DiscoverySourceFactor`

命中以下来源时额外加分：

- `hot_board`
- `latest_updates`

### 6. `NoveltyFactor`

根据 `recent_recommendation_counts` 调整新鲜度：

- 近期未出现：加 `fresh_bonus`
- 近期出现过：按次数扣 `repeat_penalty`
- 使用 `random_seed` 生成轻微抖动，打散同分项

注意：

- 代码中存在 `FeedbackSignalFactor`
- 当前 strategy 并未启用它
- 因此当前实现没有基于 seed 级反馈做排序学习

## 请求指纹与持久化

文件：

- `nassav/recommendation/repository.py`
- `nassav/models.py`

### 1. 请求指纹

`request_fingerprint` 由以下参数计算 SHA-256：

- recommender / strategy
- limit / per_seed_limit
- actor_seed_limit / genre_seed_limit
- seed_types
- exclude_existing
- avoid_recent_recommendations
- recent_snapshot_limit / recent_item_limit
- include_hot_board / include_latest_updates
- discovery_limit
- type_preference / actor_preference / genre_preference

注意：

- `random_seed` 不参与指纹计算
- 因此同一配置下的不同随机次序仍会被视为同一类请求

### 2. Snapshot

每次推荐执行后都会写入 `RecommendationSnapshot`：

- `recommender_id`
- `strategy_id`
- `request_fingerprint`
- `request_payload`
- `seed_summary`
- `item_count`
- `random_seed`
- `generated_at`

### 3. Item

每个返回候选会写入 `RecommendationItem`：

- `rank`
- `avid`
- `title`
- `detail_url`
- `cover_url`
- `source`
- `score`
- `search_rank`
- `reasons`
- `matched_seeds`
- `score_breakdown`
- `raw_metrics`

### 4. Feedback

负反馈保存在 `RecommendationFeedback`：

- 与 `RecommendationItem` 一对一
- 同时冗余存储 `avid`
- 当前只在推荐阶段用于构建 `blocked_avids`

## 返回结构

`execution.to_dict()` 返回：

- `items`
- `seeds`
- `summary`
- `meta`

`meta` 中重点字段：

- `recommender`
- `strategy`
- `snapshot_id`
- `request_fingerprint`
- `recommender_detail`
- `strategy_detail`
- `effective_request`
- `history_context`
- `learning_context`

其中：

- `history_context.filtered_history_count`
  - 表示这次请求关联的近期历史中，有多少 `avid` 没有再次出现在本次最终结果里
- `learning_context.feedback_count`
  - 表示当前负反馈样本数

## 当前限制

截至当前代码版本，推荐机制有以下边界：

- 只有一个 recommender：`jable_page_lookup`
- 只有一个 strategy：`local_preference`
- API 不支持切换 recommender
- 反馈 API 只支持 `dislike`
- 负反馈只做 `avid` 级屏蔽
- 没有把 snapshot 当作结果缓存复用，每次请求仍会重新召回和计算

## 相关文件

- `nassav/views.py`
- `nassav/models.py`
- `nassav/recommendation/manager.py`
- `nassav/recommendation/entities.py`
- `nassav/recommendation/base.py`
- `nassav/recommendation/seeds.py`
- `nassav/recommendation/factors.py`
- `nassav/recommendation/strategies.py`
- `nassav/recommendation/jable_search.py`
- `nassav/recommendation/jable_page_lookup.py`
- `nassav/recommendation/feedback.py`
- `nassav/recommendation/repository.py`
- `nassav/recommendation/cover_cache.py`
