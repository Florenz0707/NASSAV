# 前端开发规范（FOR AGENT）

## 开发前

- 阅读[仓库规范](../AGENTS.md)、[重构原则](../docs/development-principles.md)和[前端开发契约](doc/development-contracts.md)，核对公开组件、状态所有者和生命周期。
- 使用仓库指定的 `pnpm`，命令和浏览器环境见 [README](README.md)。

## 开发时

- 遵循单一职责、面向消费者能力及开闭原则，优先复用同语义的公共能力；不为文件行数机械拆组件。
- 路由页装配公共目录/详情模块；查询归对应 store，HTTP 归统一 API 客户端，WebSocket 保持连接与事件职责，黑名单自身管理读写/缓存/清理。
- 可重入异步操作使用请求版本/令牌检查结果归属；错误、loading、缓存同样受保护。路由变化、实体切换和卸载使旧操作失效。
- 外部搜索保持按钮手动触发，来源/排序变化不自动启动；取消调用后端接口，partial/失败/取消明确展示，不缓存为完整成功。
- 标题选择复用 `utils/resourceTitle.js`，下载队列保存原始字段，保持偏好变化后的重新解析；设置面板通过事件更新父状态。
- 颜色使用 main.css 的主题 token 及 Tailwind 语义映射，禁止组件新增颜色字面量；新增 token 检查深浅主题和生成样式，保留显式 `@config`。
- 优先使用 AppButton、SearchInput、ResourcePagination、CustomSelect、ConfirmDialog、AppIcon 与 useDialog；组件样式使用合适的 CSS layer，不覆盖工具类的布局/显示效果。
- 核心图标使用有明确尺寸的 currentColor SVG；弹窗/下拉检查键盘、焦点、禁用项、嵌套和卸载清理，移动端布局一并验证。

## 验证与文档

从前端目录执行：

```bash
pnpm run check
```

该入口包含 lint、单元测试和构建；根目录另执行 `pre-commit run -a`。不使用 `build | tail` 掩盖退出码；修复检查失败后再提交/合并。

主题、布局和公共交互改动执行相关 Playwright 浏览器检查，异步改动覆盖乱序、失败、取消和迟到事件；环境准备见 README。纯文档改动检查链接/命令并执行 pre-commit。同步开发契约中的新增 props/事件/状态/缓存行为；执行记录注明提交与范围，模拟验收与真实 API/worker 联调分开报告。

## 持久任务开发约束

涉及下载、刮削、所属翻译、任务控制或文件清理时，先阅读[任务控制架构](../django_backend/doc/task-control-architecture.md)。DB 是持久业务状态所有者；恢复使用新 attempt/generation，旧执行不得提交。暂停/终止须确认写入者停止，终态不等于清理完成；不得在线删除锁文件、手动清空 `.tasks` 或以 Celery revoke 代替控制协议。发布、回滚与删除复用共享资源/目标锁及资产日志；网络、复制和大文件哈希不得放入短 DB 提交回调。前端按 job_id/version 合并授权快照，以 allowed_actions 决定操作。
