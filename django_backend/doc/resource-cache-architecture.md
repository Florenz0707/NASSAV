# 持久抓取缓存

新增 ResourceMetadataCache 与 ResourcePlaybackCache（迁移 0027），不关联 AVResource，删除资源不会级联清理缓存；缓存本身不创建资源、演员、类别或推荐偏好。两张表使用相同规范化身份（AVID、提供者类型/名称、上下文哈希、版本路径哈希），播放表只接受 source。播放缓存不依赖元数据行，允许分别清理。

ProviderFactsCache 消费 ProviderFactsStore，统一批量读取、字段证据、解析版本、新鲜期与有界 single flight；生产 ORM Adapter 只执行短条件写。网络在事务外，publication fence 由任务装配提供。缓存领取使用 UUID/generation/240 秒租期，最多等待 60 秒且每次检查控制；过期/失效/清理后的旧发布只能条件更新，不能 upsert 复活。失败与空结果不覆盖旧成功；已缓存结果深复制，缺少要求字段不记为验证成功。

P1 建立表和公共能力，P2 接入推荐消费者。不回填旧 AVResource 或 Redis：旧数据出处与时间不可靠。当前 source/scraper/Jable 短缓存继续运行。P2–P5 将依次接入推荐、结构化刮削、短期播放与清理。正式 migrate/worker/站点验收不由隔离回归代替。

验证入口：`uv run pytest tests/test_resource_cache.py --ds=django_project.refactoring_test_settings -v`；完整后端门槛及根目录 pre-commit 通过后阶段提交合并 idle。后续阶段维护本文件的当前契约。

P1 阶段提交标题 `[Feat] Add persistent provider facts cache and publication fencing`，分支 feat/resource-cache-p1。SQLite 正向/反向/再次正向迁移通过；专项 7 项、完整隔离 808 passed/28 skipped，根目录 pre-commit 全通过后合并。未执行正式 migrate 或目标 PostgreSQL；旧 docs/development-principles.md 已不在当前树，现行约束以 AGENTS/AGENT 和当前任务/推荐架构为准。

## 推荐详情读取

生产 Jable 实例使用统一持久缓存，推荐在协调线程批量读取候选详情，再通过 ProxyServer 并发获取未命中项。命中后仍按当前资源库存、黑名单、反馈和偏好重新核验、评分；不缓存推荐结果或翻译。显式刷新跳过批量读取并强制获取详情。详情页面成功解析后同时缓存来源元数据（7 天）和短期 m3u8（5 分钟），原 HTML 不进入数据库。

缓存键隔离来源域名及详情路径；播放键另隔离代理出口与浏览器会话版本。解析身份不匹配不发布。成功缓存已知空演员/类别，不能把缺失字段误当核验成功。取消、历史重置、执行 UUID 失效或 deadline 到期后，任务 fence 拒绝旧执行的缓存发布；网络不进入历史/任务短事务。

`detail_attempt_count` 保留全部尝试数，新增 `detail_cache_hit_count` 与 `detail_network_attempt_count` 区分缓存与网络；缓存命中不占用网络详情尝试上限。失败详情仍消耗共享网络预算。缓存 miss 不回退旧 Redis 详情，以免把缺少时间和来源证据的内容写入持久缓存。

## 持久刮削接入

持久刮削准备器按已启用来源优先级读取同一 source 缓存，并单独保存每个 scraper 的原始元数据。scraper 键隔离名称和域名、默认新鲜期 30 天；不读取旧 Redis 元数据写入新表。显式 refresh 强制更新对应事实；取消、暂停或 attempt 失效由任务短事务 fence 阻止发布。来源和 scraper 仍使用全局 Proxy.url，不写共享单例控制状态。

热缓存无需原 HTML，因此添加资源可不生成 AVID.html；冷抓取仍通过任务资产日志发布 HTML。缺失封面和新头像按缓存 URL 下载到任务私有目录，再复用原有验证、提交、回滚及清理流程。缓存不保存本地路径，删除正式资源后的再添加不会把残留图片当成功。来源默认路径代表该来源既有候选回退策略，显式详情路径使用独立 variant；不混合不同提供者事实或本地翻译。
