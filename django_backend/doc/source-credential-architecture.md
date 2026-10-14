# 来源凭证与刷新快照

## 当前实施边界

P3分为存储协议（4c71e7f）和范围消费者两个提交。0040新增凭证/快照，0041新增专用写入密钥fence。新模式通过`NASSAV_SCOPED_SOURCE_CREDENTIALS=true`启用，默认false保持原operator兼容路径；普通用户登录继续关闭。启用后外搜/推荐按当前用户选择凭证，刮削/下载准备和共享资源播放只使用system范围，个人产物不进入正式共享媒体。私人任务与资产版本接入属于P4/P5。

运行代理证据见[代理凭证核查](source-credential-proxy-research.md)。当前匿名浏览器不会注入账户Cookie/UA，私人结果必须通过独立直连会话重放并验证，不能提交匿名页面。业务调度继续消费ProxyServer能力，不按具体provider分支。

## 数据与密钥

- SourceCredential：每来源一个system凭证、每用户每来源一个personal凭证。UUID、范围、owner、原站host、kind和version组成AEAD附加认证上下文；凭证不能换用户、换站点或换版本后解密。个人凭证不自动公开。
- SourceSessionSnapshot：按credential/version/host/出口摘要/browser_context唯一。加密Cookie及UA，owner/generation/lease形成刷新写入权。快照版本纳入认证上下文；不在Redis保存明文秘密。
- 使用AES-256-GCM，每次随机nonce。专用keyring文件格式为`{"active_key_id":"k1","keys":{"k1":"<32字节密钥的base64>"}}`；Unix权限必须为0600或更严格。密钥加载、解密失败返回明确不可用，不使用SECRET_KEY或明文兜底。
- `NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE`指向该文件。供新凭证HTTP/导入/轮换及启用后的来源消费者使用，未设置时明确不可用、盲写返回503；列表仍可只读查看状态。隔离测试强制清空该环境变量。
- 备份包括数据库和受保护密钥。密钥不能提交Git、写日志、放入任务参数或复制给浏览器；DB备份不等于密钥备份。

## 人工写入与刷新

POST创建使用expected_version=0；PUT/DELETE必须携带现有version。撤销保留行和递增版本，后续恢复须再次CAS写入，不删除身份。HTTP只返回source/scope/kind/state/host/version/时间，不返回Cookie、UA、密文或key_id。

个人写入只操作当前用户；system写入要求应用admin，包含reason代码及request_id，沿用独立审计和幂等回执。Django staff/superuser不自动授权。原站host来自服务端Source配置，不接受HTTP自由输入。系统活跃凭证只允许明确分类的挑战Cookie；未知账户Cookie只能在导入中隔离，不能成为公共鉴权信息。

刷新在事务外进行网络与加密。领取检查凭证当前版本和启用owner，再锁快照；租约忙时不抢占，过期后新owner和generation取代。提交同时检查凭证仍有效、快照context、generation、owner、未过期lease及执行check。人工写入清除旧快照秘密及租约并递增generation；旧刷新不能复活。释放必须匹配owner和generation。

人工账户Cookie不能被挑战刷新改变；账户UA也不能静默替换。只允许挑战Cookie更新，且必须完成业务验证；出口摘要只是配置身份，不能证明浏览器与直连的实际出口相同。生产验证仍须检查真实代理路线。

锁顺序：system管理先AccountControl，再key policy，再actor user，再credential，再snapshot/依赖播放；个人写入key policy→user→credential→snapshot/播放；刷新key policy→personal owner user→credential→snapshot。缓存及推荐最终发布先key policy→actor user→credential，再进入既有history/work/cache短提交。管理停用保持AccountControl→user→credential→pool/work，不反向取得key policy。key policy是短写入全局fence，网络不持有它。网络、文件读取和加密在这些锁外。共享任务与版本发布继续按P4/P5装配池/工作代次，不把缓存fence当成资产提交协议。

## 显式导入与轮换

从后端目录运行命令，默认实例须先完成迁移及管理员引导，停用旧写入者后再切换。这里的命令不自动bootstrap管理员、启用多用户或切换旧消费者。

```bash
uv run python manage.py create_source_credential_keyring --output /protected/source-keys.json --key-id k1
export NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE=/protected/source-keys.json
uv run python manage.py import_source_credentials --actor-id 1
uv run python manage.py import_source_credentials --actor-id 1 --apply
uv run python manage.py rotate_source_credentials --actor-id 1
uv run python manage.py rotate_source_credentials --actor-id 1 --apply --batch-size 100
```

创建命令只创建新文件，拒绝覆盖。导入默认预览，不复制给全部用户；仅挑战Cookie且有合法配套UA的旧行可活跃，其余加密后quarantined。已有新凭证不覆盖。旧表保持原值作为兼容回退，因此旧表和旧备份仍含明文；不能宣称全库秘密已加密。消费者统一切换前不得删除旧表或旧秘密。

轮换先在受保护keyring追加新密钥并指定active_key_id，同时保留全部历史密钥；所有消费者更新keyring后再重复有界重加密。每行只在version/key_id/ciphertext未变时更新，加密不改变业务version；冲突保留历史密钥后重试。remaining归零并核对所有凭证、快照、消费者及备份恢复方案后才能移除旧密钥。工具只修改密文，不切换文件或删除密钥。

## 验证范围

0040为新增可逆结构迁移，不自动导入Cookie/账号或改动资产。SQLite/PostgreSQL测试覆盖升级、回退、再次升级与旧Cookie保持；隔离协议测试覆盖A/B、加密篡改、缺钥、人工更新/撤销/停用、过期租约、旧owner释放、分类导入、轮换及盲写HTTP。真实账户Cookie、源站挑战重放和实际跨worker容量留待消费者切换及后续目标环境验收，模拟fixture不代替该验收。

存储子阶段最终隔离验证（2026-10-15）：全量SQLite1062 passed/28 skipped；PostgreSQL专项21 passed；模型迁移一致。执行分支`feat/scoped-source-credentials`，合并前运行全仓pre-commit。部署数据库、生产keyring与旧Cookie未修改。

## 范围消费者与运行切换

来源操作通过CredentialSourceContext消费独立CredentialSessionRecords契约。一个操作先绑定不可变ref，fork仅继承该ref、创建独立HTTP/控制实例；并发首次解析有锁，不在人工更新后重新选择新版本来掩盖旧执行失效。没有个人行时选择system，没有system时明确anonymous；个人行撤销或隔离后拒绝，不偷偷退回系统。人工更新、撤销和账号停用清除快照写入权；重新启用账号不复活旧个人凭证。

ProxyServer.session_capabilities声明隔离上下文、挑战重放、Cookie注入、UA绑定和context revision。固定Byparr仅声明前两项，不发送它会忽略的账户字段；未核查适配器默认不允许账户重放。共用原Redis全局slot，不在slot内重复抢占同一容量；同credential/context刷新由DB owner/generation租约去重。拒绝未知挑战Cookie、跨host/端口/userinfo、账户Cookie/UA替换及未验证重放，匿名HTML不作为私人结果。实际代理出口与浏览器指纹仍待目标环境验证。

Source直接请求每次读当前完整快照；Cookie仅发到配置HTTPS原站默认443端口，禁止自动重定向，封面/视频CDN不转发原站Cookie。源播放descriptor使用配套UA，不携带源站Cookie。旧SourceCookie HTTP在新模式返回410，来源自动保存也不再写旧表；配置切换必须统一重启消费者，不能混跑旧写入者。

DB事实与播放缓存、Jable短期摘要缓存、外搜聚合缓存包含credential身份/version、host、出口及context；DB缓存/推荐最终保存使用短fence。批量详情在批次边界核查，不逐资源查询授权。Redis短期缓存只使用不可变版本命名空间并检查当前选择，迟到写入即使存在也不可恢复使用，到原TTL清理；不把Redis网络调用放进DBfence。外搜提交保存非敏感source_context，worker再核查；原凭证变化后已完成句柄返回410，不伪造新的任务version或修改终态。

播放library_grant记录非敏感source_auth引用，准备、提交及每次媒体授权均核查。共享正式媒体只接受system范围；人工变化主动关闭依赖会话，迟到ready无法重开。local播放不依赖来源密钥。旧source会话缺少绑定时不在新模式继续授权，维护窗口关闭旧播放后重新创建。P5仍需不可变版本与读取占用。

轮换先备齐全部历史密钥并核查所有当前密文及active key，再CAS更新DB的key policy。旧active key进程明确拒绝新写入，不能把新快照降级为旧密钥；每行仍按原version/密文条件重加密，不改变业务ref。并发改变policy则要求重新预检；不要并发不同目标的轮换。工具不会自动更新其他进程内的keyring，必须完成消费者重启。

正式切换顺序：维护窗口停止所有旧写入者/播放，备份DB/旧Cookie/专用密钥；升级0041，显式分类导入并审核隔离行；所有API/worker配置同一keyring和新模式，统一重启，再验证system来源和个人范围。旧表仍有明文兼容数据及备份，清理须另做确认，不能凭结构迁移删除。普通用户准入、私人资产发布与自动GC仍关闭。

范围消费者最终隔离验证（2026-10-15）：SQLite全量1078 passed/28 skipped，PostgreSQL专项37 passed；模型迁移一致，全仓pre-commit通过。新模式默认false，生产SQLite、旧Cookie、密钥文件和用户准入未修改。发布计划仍须完成P4–P8；本阶段未做真实账户网站或真实共享worker验收。
