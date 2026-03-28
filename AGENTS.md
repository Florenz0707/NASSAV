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

## 验证要求

`pre-commit` 是必须项，不是可选项。

完成代码修改后，至少执行：

- `pre-commit run -a`

如果任务只涉及后端，还应优先补充：

- `cd django_backend && uv run pytest tests/ -v`
- `cd django_backend && uv run pyright`

如果任务只涉及前端，还应优先补充：

- `cd vue_frontend && pnpm run build`
- `cd vue_frontend && pnpm run lint:fix`

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
