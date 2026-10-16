# 应用角色、管理与配额

0038/0039引入角色/审计与配额。默认仍使用指定operator门禁；受控多用户准入由NASSAV_MULTI_USER_ENABLED显式开启，要求共享库和范围凭证，且账号启用并有UserAccount。身份、浏览器预条件及内置后台限制见[准入架构](multi-user-admission-architecture.md)。迁移、旧数据归属及目标验收必须逐实例核查，步骤见[切换手册](multi-user-cutover.md)。

## 职责与兼容窗口

| 模块                      | 状态/职责                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------------ |
| account_models            | UserAccount角色/配额/version；AccountControl管理串行fence；AuditEvent；持久命令receipt；登录绑定；预留 |
| account_management        | 无ORM的命令字段/类型/版本/理由校验，显式接受commands                                                   |
| account_records           | 管理事务、最后管理员保护、账号/会话/持有/旧独占工作撤销和安全审计                                      |
| account_policy            | 当前应用角色、动作与持有/范围授权；未知受管视图拒绝                                                    |
| quota_records             | user→pool锁内按用户逻辑大小预留/释放，不根据超时自动退款                                               |
| resource_administration   | 带版本/幂等/审计的可用性切换，下架关闭会话，保留文件                                                   |
| admin_presentation / HTTP | 管理投影、参数与响应；不返回密码、Cookie、私有路径或队列payload                                        |

没有UserAccount的原operator保留旧单用户行为，仅用于协调升级兼容，不能当成新应用管理员。新管理API必须通过当前准入并有显式admin；默认关闭普通准入时仍限配置operator。is_staff/is_superuser均不自动授予应用管理角色。现有任务的superuser例外仅保留在未引导的旧operator路径。

赋予UserAccount后，该账号走显式策略：资源列表与演员/类别作品数按本用户有效库投影，正式元数据/预览/封面先核验持有/访问范围，再检查条件请求或打开文件；跨对象不可读返回404。普通角色不能调用旧全局添加/刷新/删除/下载/任务控制、Cookie、路径与全局队列接口。私有范围不能借管理员角色读取；正式读取沿本人不可变版本、public或本人legacy范围核查，私人版本必须匹配owner；未知范围失败关闭。旧阶段的引导/验收记录不代表当前实例已完成P8。

受管管理员的旧全局资源/Cookie写入口同样暂不开放，等待P3–P6的凭证与共享工作协议；原未引导operator的兼容入口保持。受管管理员可使用已实现的账号、下架与任务控制；任务控制额外需要reason代码，并在管理事务内保存审计与幂等receipt，broker/文件收尾仍走现有事务外编排。批量控制由父request_id和job_id派生稳定子命令ID，不把多个工作塞入同一幂等槽。

## 管理命令、幂等与锁顺序

新增HTTP管理命令需要UUID request_id、明确版本（创建除外）和理由代码；允许bootstrap/security/maintenance/user_request/quota_adjustment，不保存任意自由文本理由。密码仅盲写，校验与昂贵哈希在事务外；请求摘要用服务端HMAC，不在审计存明文密码或正文。

管理操作先取得AccountControl单例写fence，再按ID排序user fence，涉及持有时再按规范身份排序pool，最后工作/会话等子行；不从普通用户事务反向取得管理fence。此顺序补充P0：普通业务仍user→pool→operation/work，凭证/历史按各自短事务，不在DB锁内等待文件锁、网络或broker。

全局管理fence保护两个管理员同时降级/停用时仍至少保留一个启用admin。命令receipt和业务写入同事务，跨动作/内容复用request_id冲突；重试成功命令返回原结果，不重复修改版本、撤销或退款。AuditEvent是有界保留的操作历史，AdminCommandReceipt是独立持久幂等账本；审计清理不删除receipt，不使旧请求重新可执行。

新账号由管理API创建，密码12–256字符且满足Django校验；没有公开注册/邮件邀请；其他账号登录只在显式多用户准入模式下开放。角色/停用/密码重置/显式撤销会删除该用户登录session并关闭其播放会话。新登录在用户fence内保存session与UserLoginSession绑定；旧未绑定会话在管理事务前只读扫描，再于事务内合并删除，避免将长扫描放入短锁。停用不直接删用户行。

停用先移出本用户持有、释放其quota预留，并通过现有协议请求取消**旧单owner**任务，保留停止确认/文件收尾；其他人的任务继续。本人推荐job标记取消，外搜worker检查owner启用状态，迟到提交仍受各自fence限制。共享工作只撤销本用户订阅，他人仍有需求时不终止共享job；旧单owner任务仍走原停止协议。

## 媒体与事件

0039新增PlaybackSession.library_grant：服务端在user→pool→session顺序内保存已合法授予的池/资源/范围快照。普通移出后允许该原会话在既有绝对期限内继续读取，拒绝新prepare、refresh及进度claim；原进度写入/观看记录不恢复持有。未知/旧授权快照不能凭AVID制造读取权。强制下架设置pool.is_available=false、递增版本、关闭对应会话；原文件保留，正式读取还必须固定不可变媒体版本并维护读取占用，不能以grant或Redis容量替代；见[资源版本](resource-version-architecture.md)。

受管WebSocket只加入自己的任务组；管理组仅发送工作ID/类型/version安全提示，不包含他人的推荐/搜索结果。旧全局组只供未引导operator兼容。普通角色不接收全局队列，管理队列投影去掉AVID、payload和错误正文。每次消息核验登录session和数据库中的启用用户；角色撤销/停用后的旧连接不能继续获得事件。

TaskRecords.create在写入前取得启用用户fence，与停用串行；账号已停用时迟到的HTTP请求不能再建新job。外搜owner_epoch绑定UserAccount.version，账号代次变化后拒绝旧句柄，worker在网络前/分页间检查并持久收尾cancelled，防止停用后再启用使旧任务恢复。用户id/代次字段不返回客户端，不作为公共聚合缓存的用户数据。

外部搜索查询去重键和签名token绑定用户，状态/取消同时核验snapshot.owner_id；公开聚合缓存仍可复用，返回时重新投影本用户pending/active持有。旧未绑定HTTP任务句柄不继续授权，需重新搜索，不改变全局来源代理或浏览器容量。推荐库存排除也改用本人持有，worker默认装配显式传owner；继续观看仅返回仍有合法持有的资源。

## 配额与运维

storage_quota_bytes为NULL时不设存储上限；max_active_operations默认2。逻辑用量按本用户active持有的已下载媒体完整大小计算，物理共享不摊薄；内部reserve在user fence内合并已有用量/有效预留再判断。amount_bytes是本次所需额外空间，发布方必须根据工作/发布规格计算，不能相信客户端数值。reserve/release按request_id与归属幂等，已released预留不会因重试重新激活；没有自动超时退还，以免活跃writer与配额脱节。预留尚未接入旧全局任务/下载流程，不宣称这些路径已执行配额。

维护窗口先完成迁移和P1归属核查，确认目标实例满足接入条件后再显式引导：

```bash
uv run python manage.py bootstrap_app_admin --username <原操作者>
uv run python manage.py bootstrap_app_admin --username <原操作者> --apply --request-id <UUID>
uv run python manage.py prune_audit_events --days 180 --limit 500
uv run python manage.py prune_audit_events --days 180 --limit 500 --apply
```

引导默认预览，只允许配置中的启用操作者；已有启用管理员时拒绝重新引导。审计清理默认预览，一次最多1000条，仅清AuditEvent。角色和命令账本不自动映射成旧Django标志；逆向0038/0039会丢失新角色、审计、预留、登录绑定、读取grant和下架标志，须先备份并停止受管消费者，不能带着旧授权快照直接运行旧版本。
