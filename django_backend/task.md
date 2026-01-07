# 任务 - 重构代码

## 主要工作

- 起因：现在的SourceManager职责繁杂，本质上其应该只具有两个功能：根据avid获取source_title和m3u8_url。但是现在职责冗余，既负责save_all_resources，又负责其他的数据库操作，违背了单一职责原则
- 改进：新构建一个ProxyManager，负责组合M3u8DownloaderManager, ScraperManager和SourceManager，使得接口可以直接使用ProxyManager提供的方法。（顺便说一句，现在的接口的职责也并不单一，这个我们之后再拆解）
- 具体要点：
1. 判断哪些地方应当用单例模式（目前看来m3u8下载器需要使用，因为下载器实现了多线程，速度已经足够快），注意考虑asgi异步应用的调用情况
2. ProxyManager应当整合对Source, Scraper, M3u8Downloader，数据库和对实际资源的操作（因为需要同步数据库），使用组合+委托的模式
3. ProxyManager可以直接实现，不用声明基类

## 实现步骤
1. 实现ProxyManager类，组合其他Manager，实现其应有的方法，编写并通过单元测试
2. 在views中使用ProxyManager实现原有的功能，并通过集成测试
3. 删除SourceManager冗余的职责，并通过集成测试
4. 更新文档
