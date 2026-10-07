# Recommendation Overview

本文档说明当前后端实际生效的推荐机制实现。内容以 `django_backend/nassav/recommendation/`、`nassav/http/recommendation_views.py` 与现有测试为准，不再保留历史方案设想。

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
4. 过滤本地已存在资源与 AVID 黑名单中的 `avid`
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
- `detail_enrichment_limit`
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

### 4. `GET /nassav/api/recommendations/metrics`

返回推荐效果与状态概览：

- snapshot / item / distinct avid 数量
- 重复推荐率
- `like` / `dislike` 反馈数量
- AVID 黑名单与 seed 屏蔽数量
- 最近 seed 曝光排行

### 5. `POST /nassav/api/recommendations/feedback`

记录推荐反馈。

当前 API 层接受：

- `feedback = like`
- `feedback = dislike`

请求体：

```json
{
  "snapshot_id": 12,
  "avid": "ABCD-123",
  "feedback": "like"
}
```

效果：

- 为对应 `RecommendationItem` 记录显式反馈
- `like` 会将命中的 actor / genre seed 计入正反馈统计，后续排序加权
- `dislike` 会将命中的 actor / genre seed 计入负反馈统计，后续排序降权
- `clear` 会取消该推荐项的现有反馈，并回退对应 seed 反馈计数
- AVID 级屏蔽由 `/recommendations/avid-blocklist` 独立管理

### 6. `POST /nassav/api/recommendations/reset`

清空推荐状态。默认 `preserve_blocklist=true`，只清空推荐历史、推荐项和反馈事件，保留 AVID 黑名单与手动 seed 屏蔽；传 `preserve_blocklist=false` 时会连同黑名单状态一起清空。

- `RecommendationSnapshot`
- `RecommendationItem`
- `RecommendationItemSeed`
- `RecommendationFeedback`
- 非屏蔽用途的 `RecommendationSeedProfile`

### 7. `POST /nassav/api/recommendations/seed-block`

手动屏蔽库中已有的 actor / genre。

请求体：

```json
{
  "seed_type": "actor",
  "id": 12,
  "reason": "manual"
}
```

当前支持：

- `seed_type = actor`
- `seed_type = genre`

说明：

- 这里只支持屏蔽数据库中已存在的 actor / genre
- actor / genre 的屏蔽状态最终落在 `RecommendationSeedProfile.is_blocked`
- 被屏蔽的 seed 在生成阶段直接被过滤，不会参与本轮推荐

### 8. `DELETE /nassav/api/recommendations/seed-block`

取消手动屏蔽。

请求体与 `POST` 相同，只是不再需要 `reason`。

### 9. `GET /nassav/api/recommendations/cover`

代理并缓存推荐封面，避免前端直接访问受限站点资源。

## 外部搜索缓存（单用户 NAS 场景）

为减少重复抓取外部页面带来的耗时，Jable 搜索相关入口已启用页面结果缓存。

当前缓存策略：

- 缓存层：Django cache（默认 Redis）
- 缓存粒度：page 级搜索结果（keyword / model / tag / category / hot / latest）
- 生效链路：
  - 详情页外部搜索（ActorDetail / GenreDetail）
  - 推荐召回链路（`jable_page_lookup` / `jable_search`）

配置项（`django_project/settings.py`）：

- `EXTERNAL_SOURCE_SEARCH_CACHE_ENABLED`
  - 是否启用外部搜索缓存，默认 `True`
- `EXTERNAL_SOURCE_SEARCH_CACHE_TTL_DEFAULT`
  - 通用搜索缓存 TTL（秒），默认 `1800`
- `EXTERNAL_SOURCE_SEARCH_CACHE_TTL_HOT`
  - 热榜缓存 TTL（秒），默认 `300`
- `EXTERNAL_SOURCE_SEARCH_CACHE_TTL_LATEST`
  - 最新更新缓存 TTL（秒），默认 `300`

说明：

- 该缓存为“单用户、低复杂度”设计，不引入分布式锁或多层缓存。
- 在默认配置下，能显著减少同一时间段重复请求外部站点造成的延迟与波动。

## 代码分层

### 1. API 层

文件：

- `nassav/http/recommendation_views.py`
- `nassav/urls.py`

职责：

- 解析 query/body 参数
- 调用 `recommender_manager`
- 返回统一响应结构
- 处理 actor / genre 的手动屏蔽写接口

### 2. 用例、装配与数据层

| 模块                                                        | 职责                                                                                                                       |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| recommendation/workflow.py                                  | RecommenderManager 组织策略、请求与推荐执行，依赖 RecommendationContextStore 和 recommender 工厂                           |
| recommendation/manager.py                                   | 为 HTTP 和既有同步消费者导出生产 facade；不承载 ORM 查询实现                                                               |
| composition.py                                              | 装配生产来源、inventory/context Adapter 和推荐器工厂                                                                       |
| recommendation/contracts.py                                 | 定义来源召回、种子、存在性、上下文与推荐工作流能力                                                                         |
| recommendation/data_access.py                               | DjangoRecommendationContext 生成随机种子/指纹、加载历史/反馈/屏蔽并保存 execution；DjangoCandidateInventory 批量查询存在性 |
| recommendation/repository.py、feedback.py、seed_profiles.py | 对应快照、学习与屏蔽数据规则及持久化事务                                                                                   |
| recommendation/seed_selection.py                            | 纯种子选择、配额与排序；不查询 Django                                                                                      |

实际默认注册仍为 jable_page_lookup 与 local_preference。工厂在注入表中查找，新测试推荐器只需实现并注册；新增生产来源还需实现完整 RecommendationSource。实现内部 TypeError 不重试旧签名，替身也需接受 force_refresh、sort_by 和 detail_url 等真实参数。

上下文在执行前加载给 RecommendationRequest；算法复制运行请求，active seeds/tier 等写入返回的 execution_request，不修改调用者输入。算法通过 CandidateInventory 一次查询候选集合，避免评分/过滤时逐项查询 ORM。纯核心可在没有 Django 配置时导入；生产 facade 和策略 builder 使用真实 Adapter 时需要项目配置。

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
- 反馈调权：
  - 启用 `FeedbackSignalFactor`
  - 当前只对 actor / genre seed 画像做调权
  - 不对 `avid` 做软调权，AVID 级过滤由黑名单管理

### 4. Recommender 层

文件：

- `nassav/recommendation/base.py`
- `nassav/recommendation/jable_search.py`
- `nassav/recommendation/jable_page_lookup.py`

当前实际使用的类是 `JablePageLookupRecommender`，它继承自 `JableSearchRecommender`，在 `recall_by_seed()` 中采用如下优先级：

1. actor 种子先尝试 Jable model 页
2. genre 种子先尝试 Jable tag/category 页
3. 若页映射召回不到结果，再按种子值与别名搜索

主流程只在 `AbstractRecommender.recommend()` 维护，JableSearchRecommender 通过种子上下文、扩种和详情后补量 hook 保留来源特殊行为：

1. 复制请求，build_seeds 并排除已屏蔽 seed，记录 active seeds 和出现档位。
2. recall_candidates，批量排除库内资源及黑名单候选。
3. 扩展不足的种子池，再次排除已有/屏蔽候选并刷新种子上下文。
4. 近期避让后 enrich_candidates，补详情元数据并再次执行黑名单过滤。
5. 详情过滤后按需补量，再 score_candidates、rank_and_trim，返回前做黑名单兜底。
6. 返回 RecommendationRun 的 seeds、items 和 execution_request；协调用例将实际运行请求交给上下文 Adapter 写快照。

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

在种子真正进入推荐流程前，还会先经过 `RecommendationSeedProfile` 过滤：

- 若某个 actor / genre seed 被显式标记为 `is_blocked=true`
- 且名称或 source 身份匹配
- 则该 seed 不会进入本轮推荐

当前屏蔽能力主要面向“库中已有的演员 / 类别”。

对于 actor，还保留了一条基于推荐历史的 lazy mapping 链路：

- 推荐接口本身不再实时写入映射，避免拖慢响应
- 定时脚本会读取历史 `RecommendationItem`
- 对最近推荐过的 `avid` 同时读取 JavBus 与 Jable 页面
- 先从 JavBus 提取演员名，映射回本地 `Actor.name`
- 再从 Jable 详情页解析 `div.models a.model`
- 最后用 JavBus 演员名和 Jable `source_actor_name` 做对齐，自动补 `ActorSourceMapping`

这意味着：

- actor 的映射仍可随着推荐历史逐步补全
- 但补全动作转移到了离线脚本 / 定时任务
- 后续该 actor 更容易走 `model` 页召回
- genre 当前不做类似的 lazy mapping

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

### 4. 候选详情补充

在 `detail_enrichment_limit` 范围内，推荐器会优先为 discovery 候选抓取 Jable 详情页；开启 seed 黑名单时，已命中 seed 的候选也会补详情，用于过滤详情页中命中黑名单的 actor / genre。补充字段包括：

- `detail_actors`
- `detail_actor_slugs`
- `detail_genres`
- `detail_genre_slugs`
- `detail_tag_slugs`
- `detail_category_slugs`

如果详情中的 actor / genre 与本轮本地 seed 名称或 source slug 匹配，会把该 seed 补充进候选 `matched_seeds`，让热榜/最近更新候选也能获得本地偏好加分。详情抓取失败时只跳过补充，不影响候选返回。

### 5. 候选补量

如果过滤后“优先候选”仍不足 `limit`，系统会继续：

- 从 `SeedProvider.get_additional_seeds()` 获取额外种子
- 再做最多 3 轮扩展召回

这里的“优先候选”指：

- 当开启近期避让时，优先统计“不在最近推荐历史里的候选”
- 当未开启近期避让时，统计全部候选

## 过滤与历史避让

### 1. 过滤本地已存在资源

`exclude_existing=true` 时，会查询 `AVResource.avid`，剔除本地已存在条目。

### 2. 过滤黑名单资源与反馈学习信号

当前学习机制保持直接、可解释：

- `like` 累计到 `RecommendationSeedProfile.accepted_count`
- `dislike` 累计到 `RecommendationSeedProfile.disliked_count`
- AVID 级别永久屏蔽由 `RecommendationAvidBlocklist` 单独管理
- 重复提交反馈时，会按旧值和新值的差异修正 seed 计数

实现位置：

- `nassav/recommendation/feedback.py`
- `nassav/recommendation/seed_profiles.py`

`build_learning_profile()` 当前返回：

- `blocked_avids`
- `feedback_count`
- `seed_scores`

manager 会把 `blocked_avids` 写入 `RecommendationRequest.blocked_avid_blocklist`，后续在召回后立即过滤。
同时会把 `seed_scores` 写入 `RecommendationRequest.feedback_seed_scores`，供排序阶段做 actor / genre 级加权或降权。

黑名单过滤要求：

- seed 进入召回前会先过滤 actor / genre seed 黑名单，黑名单 seed 不会触发 Jable model/tag/category/search 请求
- 每次召回完成后都会过滤 AVID 黑名单与命中 actor / genre 黑名单的候选
- discovery 候选 enrichment 后会再次按详情页 actor / genre 名称与 slug 过滤
- 返回前会再执行一次黑名单兜底过滤，避免新增召回路径绕过过滤

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

- `FeedbackSignalFactor` 已在当前 strategy 中启用
- 当前主要使用 seed 级正负反馈信号
- `avid_weight` 为 0，AVID 级过滤直接通过永久屏蔽表处理

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
- detail_enrichment_limit
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

### 4. ItemSeed

每个结果命中的 actor / genre seed 会额外写入 `RecommendationItemSeed`：

- `seed_type`
- `seed_value`
- `normalized_value`
- `seed_key`
- `source_name`
- `source_identifier`
- `aliases`
- `weight`
- `resource_count`
- `preference_score`

这张表承担了“结构化 seed 统计”的职责，后续近期 seed 轮换统计直接读它，不再依赖 `matched_seeds` JSON。

### 5. AvidBlocklist

用户对具体作品执行“拉黑/屏蔽”后，会把 `avid` 写入 `RecommendationAvidBlocklist`：

- 该表中的 `avid` 会在后续推荐中被直接过滤
- `like` / `dislike` 反馈本身不会自动修改该表

### 6. SeedProfile

系统会把 actor / genre 级别的长期状态写入 `RecommendationSeedProfile`：

- `recommended_count`
- `accepted_count`
- `disliked_count`
- `is_blocked`
- `block_reason`

当前系统已经会：

- 在保存推荐结果时累计 `recommended_count`
- 在用户点 `like` 时累计 `accepted_count`
- 在用户点 `dislike` 时累计 `disliked_count`
- 在生成种子时过滤 `is_blocked=true` 的 seed
- 在手动调用 block 接口时把库中已有 actor / genre 写入 `is_blocked=true`

### 7. Feedback

显式反馈保存在 `RecommendationFeedback`：

- 与 `RecommendationItem` 一对一
- 同时冗余存储 `avid`
- `feedback` 当前持久化 `like` 与 `dislike`；接口提交 `clear` 会删除现有记录
- 当前主要承担“反馈事件”与审计上下文职责

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
  - 表示当前反馈样本数

## 当前限制

截至当前代码版本，推荐机制有以下边界：

- 只有一个 recommender：`jable_page_lookup`
- 只有一个 strategy：`local_preference`
- API 不支持切换 recommender
- genre 当前不做 lazy mapping
- actor 的 lazy mapping 不在推荐请求内执行，而是交给离线脚本
- 没有把 snapshot 当作结果缓存复用，每次请求仍会重新召回和计算

## 相关文件

- `nassav/http/recommendation_views.py`
- `nassav/models.py`
- `nassav/recommendation/manager.py`
- `nassav/recommendation/workflow.py`
- `nassav/recommendation/contracts.py`
- `nassav/recommendation/data_access.py`
- `nassav/recommendation/seed_selection.py`
- `nassav/composition.py`
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

扩展接口与默认装配见[模块边界](p5-domain-boundaries.md)，纯算法和批量查询验证见[测试说明](../tests/README.md)。

## 来源失败、代理与详情预算

生产推荐使用独立的 Jable 实例，共用全局 `Proxy.Enable` / `Proxy.url`；
列表、详情的直接请求及浏览器出口沿用该代理，视频下载代理不参与推荐。
Jable `weight=0` 时明确拒绝推荐，不绕过来源启用配置。
生产推荐启用 `strict_failures`：抓取/校验和解析失败不再伪装为零条结果；
兼容同步接口分别返回 503（未启用）与 502（来源失败），失败不保存 snapshot。
旧来源调用默认保留兼容模式。

`detail_enrichment_limit` 按尝试的 AVID 计数，详情失败也消耗预算；
同一轮补候选与重入共用预算，不重复请求已尝试的 AVID。
响应 `meta.effective_request.detail_attempt_count` 可核对实际尝试数。

## 推荐异步任务

推荐任务独立于下载/刮削 TaskJob，DB `RecommendationJob` 为状态所有者。
HTTP 仅提交；Celery `nassav.tasks.recommendation_job_task` 在 `scrape` 队列
执行完整召回、详情和评分。旧 GET 接口暂保留同步兼容。
任务状态为 queued/running/succeeded/failed/cancelled，快照按 job_id/version 合并。
只允许创建者查询和取消。取消幂等，禁止旧执行保存推荐 snapshot；
它表示停止业务提交，网络检查点协作退出，不承诺立刻停止所有 IO。
推荐不写正式封面、视频或头像，无需下载任务的资产回滚；共享来源缓存仍可保留。

端到端预算固定 300 秒，包含排队。来源及 Byparr 控制请求复用 TaskNetworkControl；
不改变来源抓取策略或 Cookie 会话策略。worker 主进程现有恢复循环补派 queued
任务并收尾过期执行，不依赖 Beat。broker 失败保留 queued，30 秒后可重试派发。
重复 Celery 消息通过 DB 条件领取拒绝。终态 job 保留一天后清理，推荐历史仍单独保留。

清空历史原子递增 `RecommendationState.generation`、取消未结束 job、删除 snapshot；
同步兼容请求也检查准备时的 generation。成功保存 snapshot 和任务结果位于同一短
事务内，先取得历史 fence 再取得任务 fence，不包含网络请求。
部署需先应用迁移 0026，再重启 API 与各 worker；本文只证明隔离验证，尚未做真实部署验收。
