# 持久抓取缓存

新增 ResourceMetadataCache 与 ResourcePlaybackCache（迁移 0027），不关联 AVResource，删除资源不会级联清理缓存；缓存本身不创建资源、演员、类别或推荐偏好。两张表使用相同规范化身份（AVID、提供者类型/名称、上下文哈希、版本路径哈希），播放表只接受 source。播放缓存不依赖元数据行，允许分别清理。

ProviderFactsCache 消费 ProviderFactsStore，统一批量读取、字段证据、解析版本、新鲜期与有界 single flight；生产 ORM Adapter 只执行短条件写。网络在事务外，publication fence 由任务装配提供。缓存领取使用 UUID/generation/240 秒租期，最多等待 60 秒且每次检查控制；过期/失效/清理后的旧发布只能条件更新，不能 upsert 复活。失败与空结果不覆盖旧成功；已缓存结果深复制，缺少要求字段不记为验证成功。

P1 建立表和公共能力，P2 接入推荐消费者。不回填旧 AVResource 或 Redis：旧数据出处与时间不可靠。推荐与持久刮削/下载使用新缓存；旧兼容 SourceManager/ScraperManager 的 Redis 入口保留，不为新表回填。P2–P5 已接入推荐、结构化刮削、短期播放与清理。正式 migrate/worker/站点验收不由隔离回归代替。

验证入口：`uv run pytest tests/test_resource_cache.py --ds=django_project.refactoring_test_settings -v`；完整后端门槛及根目录 pre-commit 通过后阶段提交合并 idle。后续阶段维护本文件的当前契约。

P1 阶段提交标题 `[Feat] Add persistent provider facts cache and publication fencing`，分支 feat/resource-cache-p1。SQLite 正向/反向/再次正向迁移通过；专项 7 项、完整隔离 808 passed/28 skipped，根目录 pre-commit 全通过后合并。未执行正式 migrate 或目标 PostgreSQL；旧 docs/development-principles.md 已不在当前树，现行约束以 AGENTS/AGENT 和当前任务/推荐架构为准。

## 推荐详情读取

生产 Jable 实例使用统一持久缓存，推荐在协调线程批量读取候选详情，再通过 ProxyServer 并发获取未命中项。命中后仍按当前资源库存、黑名单、反馈和偏好重新核验、评分；不缓存推荐结果或翻译。显式刷新跳过批量读取并强制获取详情。详情页面成功解析后同时缓存来源元数据（7 天）和短期 m3u8（5 分钟），原 HTML 不进入数据库。

缓存键隔离来源域名及详情路径；播放键另隔离代理出口与浏览器会话版本。解析身份不匹配不发布。成功缓存已知空演员/类别，不能把缺失字段误当核验成功。取消、历史重置、执行 UUID 失效或 deadline 到期后，任务 fence 拒绝旧执行的缓存发布；网络不进入历史/任务短事务。

`detail_attempt_count` 保留全部尝试数，新增 `detail_cache_hit_count` 与 `detail_network_attempt_count` 区分缓存与网络；缓存命中不占用网络详情尝试上限。失败详情仍消耗共享网络预算。缓存 miss 不回退旧 Redis 详情，以免把缺少时间和来源证据的内容写入持久缓存。

## 持久刮削接入

持久刮削准备器按已启用来源优先级读取同一 source 缓存，并单独保存每个 scraper 的原始元数据。scraper 键隔离名称和域名、默认新鲜期 30 天；不读取旧 Redis 元数据写入新表。显式 refresh 强制更新对应事实；取消、暂停或 attempt 失效由任务短事务 fence 阻止发布。来源和 scraper 仍使用全局 Proxy.url，不写共享单例控制状态。

热缓存无需原 HTML，因此添加资源可不生成 AVID.html；冷抓取仍通过任务资产日志发布 HTML。缺失封面和新头像按缓存 URL 下载到任务私有目录，再复用原有验证、提交、回滚及清理流程。缓存不保存本地路径，删除正式资源后的再添加不会把残留图片当成功。来源默认路径代表该来源既有候选回退策略，显式详情路径使用独立 variant；不混合不同提供者事实或本地翻译。

## 下载与恢复

生产受控下载的 resolver 使用相同来源准备器，只有当前播放缓存新鲜、会话/出口上下文一致时复用 m3u8；不再把 AVResource 中未带新鲜期的播放地址当作永久有效。缓存过期则重新获取来源事实，优先保留该正式资源已选且仍启用的来源，避免无故换源；未选或来源已禁用才按当前来源优先级查找，不触发完整 scraper 刮削、翻译或封面/头像/HTML 发布。resolver 的可选 control/force 参数注入任务检查与短事务发布 fence，调用方无控制参数的旧入口仍兼容。

HLS 入口返回 401/403/404/410 时只强制刷新一次，再执行完整的 manifest/密钥/分片身份校验；其他异常不触发无界重试。下载传输及校验仍使用 DOWNLOAD_PROXY_URL，来源获取仍使用全局 Proxy.url。刷新链接不放宽续传条件：新旧媒体身份不同按既有协议要求重新下载，保留暂停产物，不绕过停止写入者和资产清理。

## 配置、统计与清理

可选 YAML ResourceCache 块由同一设置入口校验，本地/Compose 样例均已补充；省略时保持默认值。SourceTTLSeconds=604800、ScraperTTLSeconds=2592000、PlaybackTTLSeconds=300 分别控制新发布记录的新鲜期。MetadataRetentionDays=90 按最近使用清理，PlaybackGraceHours=24 按播放链接过期时间加宽限清理，CleanupBatchSize=500 限制每张表每次删除量（最大 5000）。改配置需重启相关进程；不会改写已有记录的 fresh_until。

Celery Beat 每 6 小时第 10 分钟调用 nassav.tasks.cleanup_provider_cache，未运行 Beat 则不会自动清理。清理只处理两张缓存表，跳过有效领取租约，在实际删除时再次检查条件；不会删除资源、演员、类别、业务标记、图片、视频或任务锁/中间目录。清理后旧 owner 不能重新插入结果，只能条件更新既有行。数据库备份包含缓存，保留期与批次限制用于控制增长，命中率与耗时仍须目标环境观察。

```bash
# 默认统计并预览本批数量，不展示原始事实或播放 URL
uv run python manage.py provider_cache
# 显式执行，每张表最多 500 条
uv run python manage.py provider_cache --apply --limit 500
```

统计输出 total/fresh/leased/eligible_for_cleanup；fresh 为时效统计，不等于某一消费者解析版本的可用命中数。推荐 progress 与结果的缓存/网络详情计数用于判断实际收益。

## 部署与验证边界

先备份数据库，暂停旧 API/worker 消费，再应用 0027 并一致更新 API、scrape/download worker 和 Beat。迁移只建两张空表，不恢复已删除业务资源，也不将旧数据库/Redis 中的过期播放地址升级为有效缓存。当前权限和资源目录策略不变。不要在新消费者运行时逆向迁移；停用新消费者后可逆向删缓存表，正式资源和原有业务表不受影响，但事实缓存全部丢失。

隔离阶段依次在 feat/resource-cache-p1–p5 工作，通过完整 pytest 与 pre-commit 后提交合并 idle。已合并：7e80f14（P1）、6799434（P2）、cbf52a7（P3）、dd02b58（P4）；P5 提交标题为 `[Feat] Add bounded provider cache maintenance and policy configuration`。完整隔离结果依次 808/812/814/817 passed、各 28 skipped；P1 临时 SQLite 正向/反向/再次正向迁移通过。专项覆盖热/冷缓存、强制刷新、TTL、提供者/路径/出口隔离、错误身份、缺图恢复、无 HTML 发布、一次失效链接刷新、控制 fence 和清理竞争。

未执行正式迁移、生产重启、真实站点和 Docker/目标 PostgreSQL 验收；隔离网络替身与 SQLite 不能证明真实反爬、签名链接有效期或并发数据库性能。部署后应观察冷/热推荐的 detail_cache_hit_count/detail_network_attempt_count、失效链接刷新、暂停恢复及定期清理统计。

P5 最终完整隔离验证：`uv run pytest tests/ --ds=django_project.refactoring_test_settings -v` 为 831 passed/28 skipped（含配置非法值、有效租约保留、选择后续租竞争、缓存时效与当前来源优先、取消/重置/执行归属/截止时间 fence）；`uv run python manage.py makemigrations --check --dry-run --settings=django_project.refactoring_test_settings` 返回 No changes detected。根目录 pre-commit 格式修正后全通过才提交；未改钩子配置。

## 从详情缓存添加资源

添加仍创建受控刮削任务。仅相同提供者、域名/上下文、variant 和解析版本且未过期的事实可命中。来源元数据和播放缓存都有效时复用来源准备；若播放缓存已失效，目前会重新获取该来源页面并更新事实。scraper 缓存独立，推荐仅产生 source 事实时，添加仍需获取未缓存的 JavBus 等元数据。封面和新头像按 URL 下载到私有目录，数据库资源/关系保存及所属翻译仍执行；缓存不会代替这些业务副作用。显式刷新强制获取对应事实，选择其他来源不会混用旧来源缓存。

## 外部搜索接入

外部搜索链路为任务结果复用 → 完整聚合结果缓存 → 来源列表获取；完整集合在 Redis/Django cache 中按来源/域名/出口/排序/采集页数隔离，默认启用，配置见[配置契约](configuration-contract.md)。只在完整成功时发布；异步缓存发布延后到权威任务终态 succeeded 之后，取消/失败不能发布。搜索页摘要没有 m3u8、完整演员/类别证据，不写入 ResourceMetadataCache 冒充完整详情，也不逐条追加详情网络请求。

协调线程通过可选 facts_lookup 批量读取同一 ProviderFactsCache 的有效来源详情，每批最多 200 个键；补充列表缺失的原站标题/封面，输出 detail_cached 与 detail_cache_hit_count。这些标记表示本轮读取时命中，不保证添加时播放缓存或 scraper 缓存仍有效。搜索缓存命中、过期和强制刷新不更改数据库事实新鲜期。缓存原始结果不含库存或详情命中标记；任务/聚合结果返回时重新查询库存，避免已添加/删除资源后按钮状态过时。添加仍复用原有受控刮削流程补齐缺失事实与资产。
