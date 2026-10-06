# 前端语义与模块重构执行记录

## S1 HTML 语义

分支 refactor/frontend-semantics；基线 1ded0f6。补齐标签、标题、目录链接、分页名称、跳过导航和路径导航焦点。运行 pnpm run check、浏览器 semantics/directory 及根目录 pre-commit run -a；浏览器使用本机 Vite、已有 Chromium 和模拟 API，不代表真实服务联调。后续阶段在质量门槛通过后追加记录。

## S2 交互与归属

S1 提交 3c33903；S2 分支 refactor/frontend-interactions。统一菜单/复选框和资源操作选项，修复实体详情重复删除、添加批次 task_id 变化后的匹配及推荐迟到结果。执行 pnpm run check、resourceActions 浏览器模拟及既有实体/封面检查、pre-commit run -a；新增批次代次和推荐乱序/清空回归。

## S3 页面职责

S2 提交 40a1c65；S3 分支 refactor/frontend-page-modules。拆出外部搜索面板及添加工作流/结果、推荐偏好/指标/种子，页面保留装配与跨模块协调。前端 check 的 58 项单元测试通过；执行全部 browser 套件（模拟 API/WS）、新增添加结果交接/深浅主题用例及 pre-commit run -a。历史浏览器选择器仍引用用户修改前的排序/隐藏按钮文字，已与当前可访问名称对齐。

## S4 模块布局

S3 提交 6cfedbd；S4 分支 refactor/frontend-feature-layout。业务归 features，公共能力归 shared，应用装配归 app；拆分 API 领域声明，保留 index.js 导出与唯一 HTTP 实例。同步仓库/前端规范、开发契约、模块布局说明和源码链接。执行 pnpm run check、完整 pnpm run test:browser（模拟 API/WS）和 pre-commit run -a；新增 shared 依赖边界与 API 实例/包络回归检查。没有真实后端、worker 或生产部署验收。
