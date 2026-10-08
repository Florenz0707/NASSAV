# 前端重构执行与验证

基线：6753377。每阶段在独立分支工作，通过全量 pre-commit 和前端检查后合并 idle。

| 阶段 | 范围                                   | 状态                                                 |
| ---- | -------------------------------------- | ---------------------------------------------------- |
| F1   | 本地查询顺序、错误展示、轮询和生命周期 | 完成：37 项测试、模拟浏览器倒序响应与失败提示通过    |
| F2   | 主题工具类及语义颜色                   | 完成：主题类产物检查及深浅模式浏览器验收             |
| F3   | 弹窗、下拉、图标与键盘行为             | 完成：公共组件模拟浏览器验收通过                     |
| F4   | 按钮、搜索、分页及目录页复用           | 完成：目录默认分页、URL、错误和移动布局验收通过      |
| F5   | 演员与类别详情公共逻辑                 | 完成：两种实体适配、手动搜索、部分结果与取消验收通过 |
| F6   | 推荐页、标题规则及状态职责             | 完成：39 项测试，黑名单并发与设置浏览器验收通过      |

本地模拟测试不代表生产抓取、下载或部署验收。外部搜索继续手动触发，切换来源与排序不自动启动任务。

2026-10-05 用户反馈：Docker 构建问题已解决，前端验收暂时通过、没有明显阻断问题。该反馈作为本轮接受状态记录，未提供的真实来源、worker 或数据库验收结果仍按各自验证文档维护。持续开发原则见[仓库开发规范](../../AGENTS.md)和[前端开发契约](development-contracts.md)。

F1：旧响应不能覆盖当前结果或错误/加载状态；资源页卸载失效旧查询；目录使用统一客户端。浏览器使用本地 Chromium 与模拟 API，无页面异常。

F2：Tailwind 显式加载配置；背景、文本分别映射，状态/浅色表面/阴影共用 token。Vue 页面不再包含十六进制及 rgb/rgba 字面量。

F3：共用弹窗滚动锁与焦点行为；保留原滚动状态并处理嵌套、初始打开和卸载；下拉转发交互属性并跳过禁用项。核心图标改为 SVG，EmptyState 不再解析 HTML 字符串。

F4：演员/类别目录共用页面与 store 查询工厂，统一搜索输入、分页与原生键盘卡片入口；分页和设置保存使用公共按钮。移除无消费者的旧样式族。移动端首次浏览器检查发现按钮基础样式覆盖隐藏类，已调整 CSS layer 并复验通过。

F5：两个路由页仅传入实体类型，共用查询、批量操作、缓存、来源与搜索展示。保留头像和类别徽标差异、原缓存 key；补充实体信息和路由异步生命周期保护，并按 URL 页码初始化资源列表。浏览器使用模拟任务验证部分结果与取消请求契约（响应由模拟 API 提供）。

F6：推荐黑名单具有独立的 show/close/invalidate 接口，包含自身的读写、缓存和生命周期；实体类型切换不会让旧屏蔽操作修改新列表。资源列表与下载队列状态从 facade/传输中移出，保留消费者方法和任务事件。下载队列缓存原始元数据，标题偏好改变后重新解析，退出连接后迟到元数据不写缓存。统一标题首选字段，缺失时依次回退翻译标题、来源标题、原始标题、title 和 AVID。

ESLint 启用 Vue essential、未定义变量、未使用变量和 debugger 检查。设置面板通过事件更新状态，保留即时预览与手动保存。普通前端测试从 34 项增加到 39 项；模拟浏览器脚本覆盖主题、公共组件、目录、实体详情、黑名单和设置。浏览器使用本机 Chromium 和完全模拟的 API，不能代替真实 worker、站点抓取或部署验收。

本轮未调整后端 URL、数据库或任务协议。推荐主页面与实体详情模块仍包含较多布局；本轮以消除复制和划分已知职责为范围，没有按行数机械拆分所有模板。应用 UI 与外部环境联调仍需目标环境验证。

## 2026-10-07 任务与推荐页面信息层级

提交：`[Enhancement] Simplify task and recommendation information and unify card actions`，阶段分支 `enhancement/ui-information-and-cards`，通过检查后合并 idle。

- 任务跟踪统计移入副标题旁的 info 弹窗，删除手动刷新列表，保留加载更多、自动跟踪和错误重试。
- 推荐统计、核验明细、种子和维护操作收进信息弹窗，偏好按需打开；主区域直接呈现结果和必要运行、失败、部分结果提示。普通网格按桌面三列、中等宽度两列、移动端一列展示，少量结果不放大填满整行。
- 推荐与外部搜索共用 RemoteResourceActions，主操作复用 AppButton 五态。InfoDialog 复用 useDialog，导航栏顶部边框透明、滚动后显示边框。

验证命令：`cd vue_frontend && pnpm run check`（67 项测试、ESLint、构建），根目录 `pre-commit run -a`。浏览器使用 Chromium、完全模拟 API：`recommendationJobs.cjs`、`resourceTaskFixes.cjs`、`entityDetail.cjs`，覆盖推荐结果位置、信息/偏好弹窗、跟踪统计更新、深浅主题及移动端、导航滚动；Vite 开发服务上的 `components.cjs` 与 `uxControls.cjs` 覆盖公共按钮状态、弹窗禁用/加载、嵌套、焦点循环/恢复和卸载清理。

旧 `taskDetails.cjs` 使用非持久的队列任务夹具，无法加载当前任务明细；未将它作为本轮任务页验收。当前任务协议由 `resourceTaskFixes.cjs` 验证。本轮未修改后端，也未进行真实 worker 或部署验收。

## 2026-10-08 推荐添加与信息弹窗修复

提交：`[Fix] Track recommendation adds by job identity and reorganize information dialog`，阶段分支 `fix/recommendation-controls-and-information`，质量门槛通过后合并 idle。

- 原先仅等待整体 succeeded，遗漏了资源保存后仍翻译的状态，并在提交返回后释放 loading。现在按提交身份匹配快照，资源已保存即禁用；未保存失败/取消恢复重试。回归覆盖快速终态、同 AVID 的其他任务、409 与卸载迟到响应。
- 回到顶部不再同时定义页面颜色和公共按钮颜色，复用 primary 五态与 SVG 图标。
- 信息弹窗拆为历史统计、本轮核验、推荐依据和管理操作；各区块按内容自适应，刷新独立放在标题旁，空组有占位、长种子换行，移除旧页面宽度驱动的统计/种子布局。弹窗边框与分隔线显式采用主题 token。

验证：`cd vue_frontend && pnpm run check`，71 项单元测试、ESLint 和构建；根目录 `pre-commit run -a`。Chromium `recommendationJobs.cjs` 使用模拟 API，复现过已保存资源按钮未禁用；修复后验证按钮禁用、悬浮颜色、空/运行/完成信息、不均衡种子、移动/桌面无横向溢出、焦点与任务取消等既有回归。公共弹窗 `components.cjs` 验证焦点、嵌套及卸载行为。未修改后端，未代替真实 worker/部署验收。

## 2026-10-08 推荐信息层级与多轮恢复

提交：`[Fix] Persist recommendation batches and refine context and preferences layout`，阶段分支 `fix/recommendation-layout-and-restoration`，通过质量门槛后合并 idle。

- 原先只在组件卸载保存，浏览器刷新不可靠地触发该回调，可能恢复旧批次或丢失新列表。现在每轮结束及状态变化后保存完整去重列表，pagehide/路由卸载补保存；初始恢复前禁用查询，卸载后的初始化响应不注册监听器。
- 推荐错误只显示在页底继续推荐下方；无结果时也能在同一位置重试。信息弹窗只保留历史、指标刷新和重置；移除刷新外部结果，清空回到页头。
- 核验与推荐依据默认折叠成卡片上方的摘要；偏好与黑名单合并到同一响应式弹窗。屏蔽叉移到喜欢、不喜欢右侧，保留操作契约。

验证：`cd vue_frontend && pnpm run check`（71 项测试、ESLint、构建），根目录 `pre-commit run -a`。Chromium 模拟 API 脚本 `recommendationRestore.cjs` 复现过刷新丢失列表，修复后覆盖多批次、硬刷新、清空持久化、已有/无结果失败提示、卡片操作位置、左右/上下弹窗与无横向溢出；`recommendationJobs.cjs`、`recommendationBlacklist.cjs` 覆盖原异步流程、取消、核验回退、反馈、类型切换和迟到读写。未修改后端，未进行真实 worker/来源验收。

## 2026-10-08 用户布局调整后的细化

提交：`[Fix] Refine recommendation controls and add local verification timing`，阶段分支 `fix/recommendation-details-and-timer`，基于用户 `06f9a19` 调整，通过质量门槛后合并 idle。

- 历史标题靠左、刷新与重置成组靠右，修复用户调整后的重置事件名/禁用参数。偏好与下拉增加间距，两列加主题竖线；黑名单标题与 AppButton 选项同排，空页脚不再渲染。
- 核验摘要展示已通过/召回总数及前端本轮用时，不等待后端进度；完成冻结并保存成功批次用时，旧缓存未知用时显示“—”，卸载停止计时。移除重复的上方运行文案。演员/类别 seed 使用 coral/teal 底色和浅色文字；屏蔽与反馈圆角统一。

验证：`cd vue_frontend && pnpm run check`（72 项测试、ESLint、构建），根目录 `pre-commit run -a`。计时单元回归覆盖无 progress 更新、完成冻结、下一轮重置、卸载清理。Chromium 模拟 API 的 `recommendationJobs.cjs`、`recommendationRestore.cjs`、`recommendationBlacklist.cjs` 验证计时独立更新、历史按钮对齐、标签间距、分割线、黑名单五态接入、多批次恢复与迟到响应；`components.cjs` 验证公共弹窗嵌套和焦点清理。本轮未修改后端或进行真实来源/worker 验收。

## 2026-10-08 黑名单滚动区域修复

提交：`[Fix] Let blacklist fill available dialog space`，阶段分支 `fix/blacklist-dialog-scroll-space`，质量门槛通过后合并 idle。

黑名单固定 13rem 列表上限导致弹窗剩余区域无法展示条目。现在桌面列表填满剩余高度，偏好列独立滚动；窄屏内容区整体滚动，标题固定，条目不压缩。SettingsModal 新增默认空值的 contentClass，不改变其他消费者布局。

验证：`pnpm run check`（72 项测试、ESLint、构建）、`pre-commit run -a`；Chromium 模拟 API 的 `recommendationBlacklist.cjs` 覆盖 40 项长列表、900/600 高度桌面填充与末项访问、移动端末项访问及原迟到请求/类型切换；`recommendationRestore.cjs` 和 `components.cjs` 检查已有布局、恢复与公共弹窗生命周期。本轮无后端修改或真实 worker 联调。

## 2026-10-08 v2.4.5 文档汇总

阶段分支 `docs/release-2.4.5`，提交标题 `[Doc] Release 2.4.5 recommendation and UI documentation`。汇总 2.4.4 之后的推荐 worker/公共代理并发和前端细化，保留用户主题与布局；更新 README、推荐说明/架构、前端开发入口与约束、验证状态和前后端版本元数据。验证为 `pnpm run check`（72 项、lint/build）、离线 uv 锁文件检查、版本/修改文档链接和全量 pre-commit；不重复声明真实服务验收，历史浏览器证据保留在对应阶段。
