# 界面预览

更新于 2026-10-08。这里保存当前 Vue 页面组件的浏览器截图，涵盖首页、资源库、演员库、类别库、资源详情、批量添加、Cookie、下载/刮削任务、外部搜索、推荐、个性化和设置；tasksDark 展示深色主题，其余使用浅色主题。页面介绍与图片索引见[前端 README](../../README.md#功能概览含页面与预览图)。

截图使用 1440 × 1080 视口、1 倍像素比例，保存完整页面为 JPEG（质量 92），长页高度随内容变化；弹窗按视口截图，避免固定遮罩之外出现页底内容。示例标题、演员、分类、封面与任务为虚构数据，不包含真实资源、Cookie、代理凭据或账号；截图仅展示当前布局，不证明来源网站、API/worker 联调或正式迁移完成。

## 更新方法

使用[截图脚本](../../scripts/capture-previews.cjs)和现有 Playwright 环境，依赖安装见[浏览器验收说明](../../README.md#公共组件浏览器验收)。从 vue_frontend 启动本机 Vite：

```bash
pnpm exec vite --host 127.0.0.1 --port 4178 --strictPort
```

另一个终端从 vue_frontend 执行：

```bash
NODE_PATH=/tmp/nassav-browser-audit/node_modules node scripts/capture-previews.cjs
```

有现成 Chromium 时设置 NASSAV_CHROMIUM_PATH；可用 NASSAV_BROWSER_ORIGIN 更换本机地址。脚本拒绝远程 origin，拦截业务 HTTP/WebSocket，外部网络请求中止；推荐和搜索的提交仅由浏览器替身应答，不发送后台任务。固定示例数据，等待字体及图片就绪，检查页面 JavaScript 异常，关闭浏览器后退出；不改生产组件或服务配置。

更新后目视检查图片、README 引用与文件大小，执行 pnpm run check 和仓库根目录 pre-commit run -a。截图脚本不放入自动 browser suite，避免普通回归检查覆写版本化预览图。
