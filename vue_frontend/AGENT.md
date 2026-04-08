# 项目开发规范（FOR AGENT）

## 编写代码前

- 阅读项目代码，理解项目结构和功能
- 本项目使用`pnpm`管理

## 编写代码时

- 遵守**合理封装**，**适当复用**、**开放修改**的代码设计原则
- 严格遵循仓库级别的`AGENTS.md`中关于**前端页面设计规范**的各项约定：
  - **颜色统一与语义一致性**：使用 `tailwind.config.js` 的变量 (`bg-primary`, `text-primary`, `accent-primary` 等)，禁止硬编码十六进制颜色。
  - **SVG 图标与 Unicode 规范**：首选 `svg` 结合 `fill="currentColor"`。避免用复杂的 Unicode/Emoji 以防渲染差异。
  - **组件与交互一致性**：如需下拉、弹窗、搜索、分页等，优先复用现有组件 (如 `ConfirmDialog`, `CustomSelect`)；全局按钮和浮窗的圆角、阴影和 hover 动画必须保持统一。

## 编写代码后

- 使用`pnpm run build | tail -10`测试代码的正确性
- 使用`pnpm run lint:fix`测试代码的风格规范
