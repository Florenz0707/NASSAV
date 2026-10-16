# 多用户准入与浏览器上下文

## 开关与身份

`NASSAV_MULTI_USER_ENABLED`为严格布尔，默认false。true必须同时启用共享库与范围来源凭证；准入只允许启用且具有UserAccount的账号。应用管理权限来自UserAccount.role，不从Django staff/superuser推导，不自动创建角色或开放注册。false保留配置operator的兼容登录，is_operator仅保留兼容/显式导入语义；新业务入口使用is_admitted。

默认开关与某个实例的实际启用状态分开维护。发布准备不会修改当前实例的准入或回收开关；开启前按[切换手册](multi-user-cutover.md)核查归属、凭证和目标验收。

多用户模式关闭Django内置`/admin/`后台：其auth.User表单可以绕过应用账号命令的审计、最后管理员保护、凭证/会话/持有撤销。管理员使用已实现的管理中心；首管理员/恢复使用有维护记录的受控CLI。旧模式的Django后台行为保留。不要另行暴露User/Group表单或仅按is_staff放行。

## HTTP上下文预条件

登录/session响应提供cache_identity，绑定当前用户、具体登录session、账号version与能力集。它是预条件与前端命名空间，不是Session key，也不能作为bearer token代替Cookie/CSRF。

- 多用户JSON业务请求带`X-NASSAV-Context: <cache_identity>`。SchemaAPIView在认证后、权限与业务之前核对；缺失/过期/其他登录返回409与`data.error_code=browser_context_changed`，不返回新身份或执行原修改。
- `GET /auth/session`与显式登录用于取得当前Cookie的快照；`POST /auth/logout`也核查上下文，旧标签页不能登出后来登录的账号。原CSRF和对象权限继续必需。
- AVID封面与目录头像的原生img无法带自定义头，使用`_context`查询参数。Entry UUID图片与本人结果句柄由自身账本/owner/代次核查，不免除当前登录与对象权限；不会因为没有头就放行任意图片地址。
- 原生HLS/本地Range保持播放会话UUID＋具体登录及版本grant协议，统一准入使用is_admitted；进度和离页keepalive JSON同样带当前上下文。
- 多用户业务响应统一private/no-store并Vary Cookie，包括冲突与图片。客户端内存/object URL仍按登录/关系revision失效，不能用HTTP缓存免除授权。

普通对象继续以request.user决定owner，禁止接受owner参数取得他人数据。上下文检查是请求边界，管理与持有/文件发布的短事务仍重新核查当前角色、active、版本和lease，不能以通过请求头代替业务fence。

## 前端与异步归属

api/client只维护当前预条件与请求代次；session store接收授权快照后更新，注销清空。跨Cookie409只触发session只读重查，不自动重放写请求。旧响应/旧401/旧冲突不能改写新登录，store销毁后旧bootstrap不能发布上下文。长操作仍须在每个异步边界检查自己的owner/epoch，不能认为发送时取当前全局头就能修复旧回调。

通用图片URL由API helper附加_context；离页进度/关闭使用相同头。本人结果图片不回退任意URL。组件/页面按既有identity重建并清理本人设置、资源、队列、推荐/搜索、备注草稿和object URL；不把个人数据写入共享缓存。

## WebSocket

多用户客户端使用两个subprotocol：`nassav.tasks.v1`及`nassav.context.<cache_identity>`；服务器在加入任何组前核对具体登录和上下文，只选择前一个协议响应。普通用户只加入本人提示组，应用管理员另加入脱敏管理组，不恢复旧全局队列。

每次发送/接收重新核查session、准入和账号/能力代次。无效登录4401，仍有效但上下文变化4409；上下文不是消息中的owner参数。多用户客户端遇到旧登录4401先重查当前Cookie，可能已经登录另一个账号；有效时用新身份连接，不能让旧socket直接注销新登录。旧模式保留原过期处理。
