# 前端改进计划

## 已完成

- [x] 将所有组件中的硬编码 hex 颜色替换为 CSS 变量
- [x] 将 Unicode 图标（◉ ◷ ✓ ✕ ⚠ ℹ）替换为 SVG 图标
- [x] Navbar 完整重写，统一使用 SVG 图标和 CSS 变量

---

## 待办

### ~~1. Views 层颜色一致性~~ ✓ 已完成

### ~~2. 移动端适配~~ ✓ 已完成

### ~~3. 无障碍（Accessibility）~~ ✓ 已完成

### 4. 交互细节

- ResourceCard 的刷新/删除下拉菜单在页面边缘时会被裁剪，需要智能定位（flip）
- 批量操作时选中卡片缺少视觉高亮（边框或背景变化）
- 下载按钮点击后缺少 loading 状态反馈
- 长列表滚动时 Navbar 阴影过渡不够平滑

### 5. 性能

- ActorGroupCard / GenreGroupCard 的头像图片未做懒加载
- ResourcesView 在切换筛选条件时会短暂闪烁（可加 skeleton 过渡）
