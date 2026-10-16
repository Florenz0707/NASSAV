# 推荐与外部搜索的本人结果图片

## 边界与所有者

SOURCE_CREDENTIALS_ENABLED开启后，图片请求只接受`cover_handle`，不再接受调用方自选的url/source。句柄仅由服务器投影本人已持久化推荐Item或本人Redis搜索结果时签发；不是可转交给别人的授权。读取仍需当前登录、用户/账号代次、原结果及来源上下文有效。普通多账号准入仍由统一门禁控制。

`discovery_image_handles`是签发/解析Adapter；HTTP选择入口并生成私有FileResponse；RecommendationImages消费来源scope、actor和结果检查能力；composition装配来源、网络控制、缓存与安全文件打开。业务推荐流程只通过注入的image_contexts回调取得结果范围，不读取HTTP或默认ORM。

## 证据与存储

推荐在来源执行结束、发布fence之前取得`[domain, sha256(scope_key)]`，随原有短事务写入RecommendationSnapshot.request_payload的内部版本键`_image_contexts_v1`。按来源名保存，不保存Cookie、UA或签名播放URL；公开effective_request不返回该内部键。此改动复用JSON列，无DDL或数据回填。没有证据的历史快照不推测原凭证范围，图片暂用占位；后续新推荐生成有效句柄。

外部搜索沿用query.source_context与owner_id/owner_epoch，原始图片字段是thumbnail_url；前端映射cover_url时保留cover_handle。详情缓存仅在摘要缺图时补图，句柄解析重走同一只读详情投影核对，不抓取详情、不改写Redis结果，不把缓存数据提升成新的搜索结果授权。

句柄签名引用结果身份、用户/账号代次以及来源/图片/上下文摘要，不编码图片URL。推荐按Item主键解析，批量签发只查询本人所需快照；搜索引用task UUID和AVID，随Redis快照删除/到期失效。句柄没有独立的保活机制：推荐随原Item生命周期，搜索随原任务TTL；历史重置不会被旧句柄恢复。客户端结果缓存丢失句柄时不得退回任意URL代理。

## 读取与失效

1. HTTP核查参数及当前登录，签名/归属/结果/账号代次不匹配按不存在处理。
2. 在当前用户独立来源中比对原domain/scope摘要；凭证撤销、更新、来源域名或代理/浏览器上下文变化不能使用旧图片范围。
3. 结果检查注入现有TaskNetworkControl，来源取图仍走全局Proxy.url及既有CDN策略，不携带第三方Cookie、不跟随重定向，并保持MIME/大小/超时限制。
4. 缓存命中也检查结果与来源。每次流读取前后检查；历史删除/搜索快照过期/账号变化停止后续块，已发送内容不能撤回。传输途中失效停止临时文件发布。
5. 复用已有NOFOLLOW/dirfd安全打开，不清理锁、正式资产或他人的缓存。缓存生命周期仍由独立缓存清理负责，句柄失效不以目录删除代替授权。

HTTP保持private/no-store、Vary Cookie及nosniff。原URL-only代理只留在旧operator兼容模式；不能据兼容接口开放普通用户。界面遇到没有有效句柄或读取失败显示原有占位，重新搜索/推荐才取得新结果，不自动启动抓取。

同一结果/图片/范围证据的签名稳定，不随轮询时间改变URL；每次读取核查原授权，不通过换签延长结果寿命。避免部分结果轮询让已展示图片反复请求或闪烁。
