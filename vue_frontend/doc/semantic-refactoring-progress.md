# 前端语义与模块重构执行记录

## S1 HTML 语义

分支 refactor/frontend-semantics；基线 1ded0f6。补齐标签、标题、目录链接、分页名称、跳过导航和路径导航焦点。运行 pnpm run check、浏览器 semantics/directory 及根目录 pre-commit run -a；浏览器使用本机 Vite、已有 Chromium 和模拟 API，不代表真实服务联调。后续阶段在质量门槛通过后追加记录。

## S2 交互与归属

S1 提交 3c33903；S2 分支 refactor/frontend-interactions。统一菜单/复选框和资源操作选项，修复实体详情重复删除、添加批次 task_id 变化后的匹配及推荐迟到结果。执行 pnpm run check、resourceActions 浏览器模拟及既有实体/封面检查、pre-commit run -a；新增批次代次和推荐乱序/清空回归。
