# 来源凭证与刷新快照

## 当前实施边界

P3分为存储协议和消费者切换两个提交。当前首先完成存储协议：0040新增凭证和刷新快照，提供盲写HTTP、显式旧数据导入和有界重加密命令。旧SourceCookie和抓取消费者尚未切换；普通用户登录继续关闭。不能把个人凭证已保存当成现有推荐、刮削或播放已使用该凭证。

运行代理证据见[代理凭证核查](source-credential-proxy-research.md)。当前匿名浏览器不会注入账户Cookie/UA，私人结果必须通过独立直连会话重放并验证，不能提交匿名页面。业务调度继续消费ProxyServer能力，不按具体provider分支。

## 数据与密钥

- SourceCredential：每来源一个system凭证、每用户每来源一个personal凭证。UUID、范围、owner、原站host、kind和version组成AEAD附加认证上下文；凭证不能换用户、换站点或换版本后解密。个人凭证不自动公开。
- SourceSessionSnapshot：按credential/version/host/出口摘要/browser_context唯一。加密Cookie及UA，owner/generation/lease形成刷新写入权。快照版本纳入认证上下文；不在Redis保存明文秘密。
- 使用AES-256-GCM，每次随机nonce。专用keyring文件格式为`{"active_key_id":"k1","keys":{"k1":"<32字节密钥的base64>"}}`；Unix权限必须为0600或更严格。密钥加载、解密失败返回明确不可用，不使用SECRET_KEY或明文兜底。
- `NASSAV_SOURCE_CREDENTIAL_KEYRING_FILE`指向该文件。当前只供新凭证HTTP/导入/轮换消费，未设置时盲写返回503；列表仍可只读查看状态。隔离测试强制清空该环境变量。
- 备份包括数据库和受保护密钥。密钥不能提交Git、写日志、放入任务参数或复制给浏览器；DB备份不等于密钥备份。

## 人工写入与刷新

POST创建使用expected_version=0；PUT/DELETE必须携带现有version。撤销保留行和递增版本，后续恢复须再次CAS写入，不删除身份。HTTP只返回source/scope/kind/state/host/version/时间，不返回Cookie、UA、密文或key_id。

个人写入只操作当前用户；system写入要求应用admin，包含reason代码及request_id，沿用独立审计和幂等回执。Django staff/superuser不自动授权。原站host来自服务端Source配置，不接受HTTP自由输入。系统活跃凭证只允许明确分类的挑战Cookie；未知账户Cookie只能在导入中隔离，不能成为公共鉴权信息。

刷新在事务外进行网络与加密。领取检查凭证当前版本和启用owner，再锁快照；租约忙时不抢占，过期后新owner和generation取代。提交同时检查凭证仍有效、快照context、generation、owner、未过期lease及执行check。人工写入清除旧快照秘密及租约并递增generation；旧刷新不能复活。释放必须匹配owner和generation。

人工账户Cookie不能被挑战刷新改变；账户UA也不能静默替换。只允许挑战Cookie更新，且必须完成业务验证；出口摘要只是配置身份，不能证明浏览器与直连的实际出口相同。生产验证仍须检查真实代理路线。

锁顺序：system管理先AccountControl，再actor user，再credential，再snapshot；个人写入user→credential→snapshot；刷新personal owner user→credential→snapshot。网络、文件读取和加密在这些锁外。后续任务/缓存发布须把凭证fence与现有用户/池/work锁顺序一起装配，不能在长期网络事务中持锁。

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
