# 前端改进计划

## 已完成

- [x] 将所有组件中的硬编码 hex 颜色替换为 CSS 变量
- [x] 将 Unicode 图标（◉ ◷ ✓ ✕ ⚠ ℹ）替换为 SVG 图标
- [x] Navbar 完整重写，统一使用 SVG 图标和 CSS 变量

---

## 待办

### 1. Views 层颜色一致性

组件层已完成，但各 View 文件中仍存在硬编码颜色，需同步替换：

- `HomeView.vue` — 统计卡片、快捷操作按钮中的 `#ff6b6b`、`#ff9f43`、`#4ecdc4` 等
- `ResourceDetailView.vue` — 收藏/观看按钮、元数据标签中的硬编码色值
- `ActorsView.vue` / `ActorDetailView.vue` — 演员卡片、头像占位符颜色
- `GenresView.vue` / `GenreDetailView.vue` — 类别卡片颜色
- `AddResourceView.vue` — 状态标签（404 橙色、403 紫色等）可考虑统一到 CSS 变量
- `SettingsView.vue` — 表单控件、Cookie 状态标签颜色
- `DownloadsView.vue` — 列表项颜色

### 2. 移动端适配

- Navbar 在小屏幕下缺少汉堡菜单，导航项挤压
- ResourceCard 操作按钮在窄屏下文字溢出
- BatchControls 批量操作栏在小屏下换行布局混乱
- ResourceSearchBar 筛选项在小屏下需要横向滚动

### 3. 无障碍（Accessibility）

- 所有图标按钮缺少 `aria-label`（如刷新、删除按钮）
- 下拉菜单缺少 `role="menu"` / `role="menuitem"` 语义
- ConfirmDialog 缺少 `role="dialog"` 和 `aria-modal`
- Toast 通知缺少 `role="alert"` / `aria-live`
- 键盘导航：下拉菜单无法用方向键操作，Esc 键未绑定关闭

### 4. 交互细节

- ResourceCard 的刷新/删除下拉菜单在页面边缘时会被裁剪，需要智能定位（flip）
- 批量操作时选中卡片缺少视觉高亮（边框或背景变化）
- 下载按钮点击后缺少 loading 状态反馈
- 长列表滚动时 Navbar 阴影过渡不够平滑

### 5. 性能

- ActorGroupCard / GenreGroupCard 的头像图片未做懒加载
- ResourcesView 在切换筛选条件时会短暂闪烁（可加 skeleton 过渡）
