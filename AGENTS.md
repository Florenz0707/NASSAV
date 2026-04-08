# 仓库级开发规范（FOR AGENT）

本文件是仓库级总规范，用于约束在 `NASSAV` 仓库中的通用开发行为。

更细粒度的子项目规范以各自目录下的 `AGENT.md` 为准：

- 后端开发前，先阅读 [django_backend/AGENT.md](django_backend/AGENT.md)
- 前端开发前，先阅读 [vue_frontend/AGENT.md](vue_frontend/AGENT.md)

如果根规范与子项目规范冲突，优先遵守更贴近目标目录的规范。

## 项目结构

- `django_backend/`
  - Django 5 后端
  - 核心代码位于 `django_backend/nassav/`
  - 项目配置位于 `django_backend/django_project/`
  - 后端文档位于 `django_backend/doc/`

- `vue_frontend/`
  - Vue 3 + Vite 前端
  - 页面位于 `vue_frontend/src/views/`
  - 组件位于 `vue_frontend/src/components/`
  - store 位于 `vue_frontend/src/stores/`
  - API 封装位于 `vue_frontend/src/api/`

- `origin_project/`
  - 历史参考实现
  - 除非任务明确要求，否则不要在此目录中进行功能开发

## 开发前

- 先确认本次修改影响的是后端、前端，还是两者都有
- 在进行后端开发之前，先阅读 `django_backend/AGENT.md`
- 在进行前端开发之前，先阅读 `vue_frontend/AGENT.md`
- 修改前先阅读相关代码和文档，避免直接跳到实现
- 如涉及接口、数据结构、脚本、配置或架构变更，评估是否需要同步更新文档

## 开发时

- 优先保持现有架构分层，不要把调度逻辑、抓取逻辑、API 逻辑和数据对象混在一起
- 尽量复用已有抽象，而不是平行复制一套相似实现
- 新增模块时优先考虑：
  - 职责是否单一
  - 抽象边界是否清晰
  - 后续是否容易替换或扩展
- 不要在未确认上下文的情况下重构无关代码
- 除非任务明确要求，否则不要修改 `origin_project/`

## 前端页面设计规范

在修改前后端页面与组件（如 `vue_frontend/` 目录下的代码）时，除遵循 `vue_frontend/AGENT.md` 外，必须保证以下 UI 规范：

### 1. 颜色的统一与语义一致性

- **禁止硬编码颜色**：严禁在独立组件中随意手写或硬编码未在规范内的十六进制颜色值。必须统一使用 `tailwind.config.js` 中配置的设计系统变量。
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

- **公共组件首选**：凡遇到下拉菜单（Select）、二次确认弹窗（ConfirmDialog）或搜索框、分页等场景，必须优先复用 `vue_frontend/src/components/` 下的已有组件（如 `CustomSelect.vue`, `ConfirmDialog.vue`），杜绝在单一页面中重新手写一套相同逻辑。
- **交互状态一致**：
  - 按钮样式（Button）：必须保持全局统一的 Padding、圆角大小（如 `rounded-lg`）、一致的背景与悬浮反馈（常用 `hover:bg-opacity-80` 或过渡样式 `transition-colors duration-200`）。
  - 下拉与浮窗（Dropdown / Dialog）：统一使用 `bg-secondary`，辅以一致的淡色边框（如 `border border-white/10`）以及阴影（预设的 `shadow-md` 或 `shadow-lg`）与圆角，保证所有弹出层景深感受相同。
- **结构与留白**：区块（Card）、表单内外间距必须统一使用 Tailwind 标准间距尺码（如 `p-4`, `gap-3`, `mt-6`），同一层级应保持视觉一致，避免生硬和跳跃的排版。

## 验证要求

`pre-commit` 是必须项，不是可选项。

完成代码修改后，至少执行：

- `pre-commit run -a`

如果任务只涉及后端，还应优先补充：

- `cd django_backend && uv run pytest tests/ -v`

如果 `pre-commit run -a` 失败：

- 必须先修复失败项，再结束任务
- 不要在存在已知 lint、format、type check 或 compile check 错误的情况下宣称完成

## 文档要求

- 后端相关改动，需要检查 `django_backend/doc/` 下文档是否需要同步更新
- 新增接口时，应更新接口文档
- 新增或调整数据库相关行为时，应更新数据库文档
- 新增脚本、推荐链路、服务编排或其他非显然行为时，应补充设计说明文档

## 提交约定

- 提交信息沿用仓库既有前缀风格：
  - `[Feat]`
  - `[Fix]`
  - `[Chore]`
  - `[Enhancement]`
  - `[Doc]`
- 一次提交应尽量聚焦一个明确目标
- 提交时应主动询问是否需要代为提交，并给出提交信息

## 默认收尾清单

除非任务明确说明不需要，完成修改后默认执行以下检查：

1. 运行与改动直接相关的测试
2. 运行 `pre-commit run -a`
3. 确认必要文档已更新
4. 再输出最终结论
