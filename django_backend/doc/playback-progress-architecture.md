# 个人播放进度架构

数据库拥有持久进度；PlaybackSession 拥有当前登录的短期播放授权。进度不进入资源事实缓存，不改变共享 watched，不派发 Celery。多用户扩展见[路线](multi-user-roadmap.md)。

## 模型和媒体身份

迁移0032新增 nassav_playback_progress，唯一(user, avid, media_key)。用户外键删除级联；avid 为字符串，不随资源/会话删除。会话回收不清进度。个人历史首版保留至手动清除或用户删除，无定期自动过期。

local 的 media_key 是既有描述（发布 marker/文件指纹）的规范化摘要；替换/重发布/文件搬迁可能使身份变化，保守视作新视频，不自动套旧位置。source 使用模式、AVID、来源组成账本键，仅用于保存同来源最近位置，不承诺原站字节身份；新会话均要求确认位置。同一会话的受控刷新仍执行原有兼容检查，旧 generation 的进度写入拒绝。

position/duration 为有限秒数，0<=position<=duration<=604800；duration 必须大于0。completed 由播放器 ended 决定，不依据百分比自动完成。重新播放提交 completed=false，允许向后拖动保存。

## 写入协议

GET当前会话progress返回不含凭证的用户/媒体账本摘要ledger_key、位置、时长、完成标志、version、writer_generation、restore_policy及时间，不返回媒体描述/来源URL。local必须复核当前文件，source仅在ready有效授权时访问。

claim携带session_generation、expected_writer_generation、UUID request_id；短事务先锁用户写入fence，再锁播放会话，检查有效期与归属。最近成功领取者拥有写入权，增加writer_generation、保存writer_session、重置序号。同命令重试仅在仍拥有写入权时幂等；旧命令不能抢回已转让或清除的权利。

PUT携带session_generation、writer_generation、sequence、expected_version、UUID request_id、position_seconds、duration_seconds、completed。用户/当前登录/会话代次/写入代次检查后更新，乱序/版本冲突409。同序号同完整payload幂等，改写同序号拒绝。网络与文件核查不进入短DB事务。

DELETE资源progress只清当前用户该AVID的所有媒体版本。保留零值墓碑并递增version/writer_generation、撤销writer_session，禁止删除重建造成token复用。重新播放需重新领取，不自动抢权。

## 接口

| 方法   | 路径                                              | 参数                                                       |
| ------ | ------------------------------------------------- | ---------------------------------------------------------- |
| GET    | /nassav/api/playback-sessions/{id}/progress       | 当前登录所属ready会话                                      |
| POST   | /nassav/api/playback-sessions/{id}/progress/claim | session_generation、expected_writer_generation、request_id |
| PUT    | /nassav/api/playback-sessions/{id}/progress       | 归属/版本/序号与位置字段                                   |
| DELETE | /nassav/api/resources/{avid}/playback-progress    | 仅当前用户                                                 |

使用现有operator权限、CSRF、PLAYBACK_ENABLED与no-store；跨登录会话404，关闭/到期410，冲突409，参数错误400。将来开放多用户须先实施权限矩阵，不直接放宽所有业务API。

## 验证边界

专项覆盖幂等、乱序、回退、完成、清除与旧claim重试、多标签、用户隔离、关闭/到期/更换代次、文件版本、CSRF与接口契约。0031↔0032需验证可逆及SQLite/PostgreSQL关系保持；正式数据库迁移和浏览器/真实环境验收分别记录。前端接入后补充保存生命周期。
