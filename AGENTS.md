# 仓库级开发规范（FOR AGENT）

本文件是仓库级总规范，用于约束在 `NASSAV` 仓库中的通用开发行为。

更细粒度的子项目规范以各自目录下的 `AGENT.md` 为准：

- 后端开发前，先阅读 [django_backend/AGENT.md](django_backend/AGENT.md)
- 前端开发前，先阅读 [vue_frontend/AGENT.md](vue_frontend/AGENT.md)

如果根规范与子项目规范冲突，优先遵守更贴近目标目录的规范。

## 项目结构

- `django_backend/`
  - Django 后端
  - 核心代码位于 `django_backend/nassav/`
  - 项目配置位于 `django_backend/django_project/`
  - 后端文档位于 `django_backend/doc/`

- `vue_frontend/`
  - Vue 3 + Vite 前端
  - 页面位于 `vue_frontend/src/views/`
  - 业务组件与状态位于 `vue_frontend/src/features/<业务>/`
  - 无业务依赖的 UI、组合函数及工具位于 `vue_frontend/src/shared/`
  - 路由、导航及全局事件连接位于 `vue_frontend/src/app/`
  - API 封装位于 `vue_frontend/src/api/`

## 开发前

- 先确认本次修改影响的是后端、前端，还是两者都有
- 在进行后端开发之前，先阅读 `django_backend/AGENT.md`
- 在进行前端开发之前，先阅读 `vue_frontend/AGENT.md`
- 修改前先阅读相关代码和文档，避免直接跳到实现
- 阅读[重构原则与持续开发约束](docs/development-principles.md)，核对目标模块的公开契约与状态所有者
- 如涉及接口、数据结构、脚本、配置或架构变更，评估是否需要同步更新文档

## 开发时

- 优先保持现有架构分层，不要把调度逻辑、抓取逻辑、API 逻辑和数据对象混在一起
- 尽量复用已有抽象，而不是平行复制一套相似实现
- 新增模块时优先考虑：
  - 职责是否单一
  - 抽象边界是否清晰
  - 后续是否容易替换或扩展
- 不要在未确认上下文的情况下重构无关代码
- 面向消费者能力定义接口，核心接受显式依赖，生产默认实现由装配层提供；不为纯函数、数据对象和简单框架入口强制增加抽象基类
- 按单一职责划分状态与副作用，通过注册、工厂、策略或 hook 扩展；不在通用流程堆叠来源/实体分支，也不为假想需求创建框架
- 结构重构保持 URL、任务名、数据字段、缓存与副作用顺序；行为修复单独说明新旧差异并覆盖失败、取消、部分成功及终态
- 异步操作检查结果归属；旧响应、迟到事件和失租执行不得覆盖新状态或发布成功副作用

## 前端页面设计规范

在修改前后端页面与组件（如 `vue_frontend/` 目录下的代码）时，除遵循 `vue_frontend/AGENT.md` 外，必须保证以下 UI 规范：

### 1. 颜色的统一与语义一致性

- **禁止硬编码颜色**：独立组件不得新增十六进制、rgb/rgba 等颜色字面量；主题值集中定义于 `src/styles/main.css`，使用 `tailwind.config.js` 映射的语义工具类或已有 CSS token。新增 token 同时覆盖深浅主题，保留入口的显式 `@config` 并验证生成样式。
- **背景与文本**：
  - 背景统一使用 `bg-primary`（应用主背景）与 `bg-secondary`（侧边栏、卡片、浮层背景）。
  - 文本统一根据权重使用 `text-primary`（常用于正文/标题）、`text-secondary`（副文本）与 `text-muted`（提示/占位文本）。
- **强调与交互（Accent）**：使用 `accent-primary`（主要交互/高亮）、`accent-secondary`、`accent-tertiary` 来处理按钮和重要点缀。
- **语义一致性**：相同语义（如危险/删除动作、确认动作、链接等）在全站的色彩应当保持唯一且一致。

### 2. SVG 图标与 Unicode 图标使用规范

- **首选 SVG 图标**：用于表达功能、操作、核心元素的图标应统统使用内联 `<svg>`。并通过 `fill="currentColor"` 或 `stroke="currentColor"` 让图标颜色跟随上下文的文字颜色变化。
- **尺寸与对齐**：所有的 SVG 图标必须显式通过 Tailwind 类定义宽高（例：`w-5 h-5` 或 `w-4 h-4`），并结合 Flex 布局（`flex items-center gap-2` 等）保证它与相邻文本精确的垂直居中对齐。
- **限制 Unicode 表意符**：严禁使用复杂的 Unicode 符号或 Emoji 代替核心功能图标（例如不要用 ⚙️、❌ 代替设置或关闭），避免在不同设备和操作系统上发生渲染差异。Unicode 图标仅限用于少量纯文本占位符或极简列表符（如 `·` 或箭头 `→`）。

### 3. 组件一致性（按钮、下拉菜单等）

- **公共组件首选**：优先复用 `AppButton`、`CustomSelect`、`ConfirmDialog`、`SearchInput`、`ResourcePagination` 等已有组件；目录与演员/类别详情复用公共模块，不复制同语义的查询和任务生命周期。
- **交互状态一致**：
  - 按钮使用公共 variant、尺寸与 loading/disabled 状态；基础样式使用合适的 CSS layer，使工具类可以覆盖显示和布局。
  - 下拉与浮窗使用 `bg-secondary`、默认语义边框（`--border-color`）、预设阴影与圆角，保证深浅主题一致。
  - 弹窗复用 `useDialog`，检查初始打开、嵌套、焦点循环/恢复和卸载清理；下拉支持键盘操作与禁用项跳过。
- **结构与留白**：区块（Card）、表单内外间距必须统一使用 Tailwind 标准间距尺码（如 `p-4`, `gap-3`, `mt-6`），同一层级应保持视觉一致，避免生硬和跳跃的排版。

## 验证要求

`pre-commit` 是必须项，不是可选项。

完成代码或文档修改后，至少执行：

- `pre-commit run -a`

如果任务只涉及后端，还应优先补充：

- `cd django_backend && uv run pytest tests/ --ds=django_project.refactoring_test_settings -v`

前端代码修改执行 `cd vue_frontend && pnpm run check`；主题、布局、键盘和弹窗生命周期修改另执行相关浏览器检查。命令必须保留退出码，不通过输出截断掩盖失败。后端隔离设置、在线 opt-in 和测试依赖见[测试说明](django_backend/tests/README.md)。

如果 `pre-commit run -a` 失败：

- 必须先修复失败项，再结束任务
- 不要在存在已知 lint、format、type check 或 compile check 错误的情况下宣称完成
- 质量门槛无法达成时说明失败证据，暂停依赖该门槛的合并并与用户沟通
- 分别报告已实现、隔离验证与目标环境验收，不把模拟 API、eager task 或构建通过当作真实服务联调

## 文档要求

- 版本变更日志统一写入根目录 [CHANGES.md](CHANGES.md)，按版本倒序排列并沿用现有分类；README 仅保留入口，不再追加版本记录
- 后端相关改动，需要检查 `django_backend/doc/` 下文档是否需要同步更新
- 新增接口时，应更新接口文档
- 新增或调整数据库相关行为时，应更新数据库文档
- 新增脚本、推荐链路、服务编排或其他非显然行为时，应补充设计说明文档
- 后端职责维护于[任务架构与职责](django_backend/doc/task-control-architecture.md)，前端职责与组件约束维护于[开发契约](vue_frontend/doc/development-contracts.md)与[模块布局](vue_frontend/doc/module-layout.md)；执行记录注明提交、命令和验证范围

## 提交约定

- 提交信息沿用仓库既有前缀风格：
  - `[Feat]`
  - `[Fix]`
  - `[Chore]`
  - `[Enhancement]`
  - `[Doc]`
- 一次提交应尽量聚焦一个明确目标
- 未获提交授权时主动询问并给出提交信息；用户已授权分阶段提交和合并时直接执行，不重复询问
- 本轮已授权流程：仅在 `/tmp/nassav-agent-worktree` 使用独立阶段分支，通过质量门槛后提交并合并 `idle`，结束保持工作树干净且位于 `idle`；默认工作树保留给用户使用

## 默认收尾清单

除非任务明确说明不需要，完成修改后默认执行以下检查：

1. 运行与改动直接相关的测试
2. 清理相关临时文件
3. 运行 `pre-commit run -a`
4. 确认必要文档已更新
5. 再输出最终结论

## 持久任务开发约束

涉及下载、刮削、所属翻译、任务控制或文件清理时，先阅读[任务控制架构](django_backend/doc/task-control-architecture.md)。DB 是持久业务状态所有者；恢复使用新 attempt/generation，旧执行不得提交。暂停/终止须确认写入者停止，终态不等于清理完成；不得在线删除锁文件、手动清空 `.tasks` 或以 Celery revoke 代替控制协议。发布、回滚与删除复用共享资源/目标锁及资产日志；网络、复制和大文件哈希不得放入短 DB 提交回调。前端按 job_id/version 合并授权快照，以 allowed_actions 决定操作。

## 推荐开发约束

修改推荐、反馈或历史重置前阅读[推荐架构](django_backend/doc/recommendation-architecture.md)。
推荐 job 由 DB 持有，Celery 仅运输；成功检查历史 generation、执行 UUID 和 deadline。
网络不进入短提交事务；取消/重置后的旧执行不得保存 snapshot。
推荐来源与浏览器出口共用全局 Proxy.url，Byparr 控制直连，不混用下载代理。
详情失败消耗共享预算，启用 seed 黑名单时排除未核验候选并告知数量；
反馈先取得共享历史写入 fence，再读取旧值和更新计数。离线映射不默认自动运行。

代理服务器并发能力统一由 `ProxyServer` 提供，不以 Byparr 等具体 provider 决定业务调度；
来源实例、会话和网络控制按并发操作隔离，结果、预算与提交由协调线程持有，
跨 worker 容量和开发约束见[代理并发架构](django_backend/doc/proxy-concurrency.md)。
