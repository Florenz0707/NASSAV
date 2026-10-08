# 持久抓取缓存

新增 ResourceMetadataCache 与 ResourcePlaybackCache（迁移 0027），不关联 AVResource，删除资源不会级联清理缓存；缓存本身不创建资源、演员、类别或推荐偏好。两张表使用相同规范化身份（AVID、提供者类型/名称、上下文哈希、版本路径哈希），播放表只接受 source。播放缓存不依赖元数据行，允许分别清理。

ProviderFactsCache 消费 ProviderFactsStore，统一批量读取、字段证据、解析版本、新鲜期与有界 single flight；生产 ORM Adapter 只执行短条件写。网络在事务外，publication fence 由任务装配提供。缓存领取使用 UUID/generation/240 秒租期，最多等待 60 秒且每次检查控制；过期/失效/清理后的旧发布只能条件更新，不能 upsert 复活。失败与空结果不覆盖旧成功；已缓存结果深复制，缺少要求字段不记为验证成功。

P1 仅建立表和公共能力，尚未接入生产消费者。不回填旧 AVResource 或 Redis：旧数据出处与时间不可靠。当前 source/scraper/Jable 短缓存继续运行。P2–P5 将依次接入推荐、结构化刮削、短期播放与清理。正式 migrate/worker/站点验收不由隔离回归代替。

验证入口：`uv run pytest tests/test_resource_cache.py --ds=django_project.refactoring_test_settings -v`；完整后端门槛及根目录 pre-commit 通过后阶段提交合并 idle。后续阶段维护本文件的当前契约。

P1 阶段提交标题 `[Feat] Add persistent provider facts cache and publication fencing`，分支 feat/resource-cache-p1。SQLite 正向/反向/再次正向迁移通过；专项 7 项、完整隔离 808 passed/28 skipped，根目录 pre-commit 全通过后合并。未执行正式 migrate 或目标 PostgreSQL；旧 docs/development-principles.md 已不在当前树，现行约束以 AGENTS/AGENT 和当前任务/推荐架构为准。
