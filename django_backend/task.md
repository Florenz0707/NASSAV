# Django_backend

本项目是通过`django + celery`构建原项目（NASSAV）的后端版本。

# 原项目

阅读`D:\NASSAV\src\*`，理解原项目代码结构和功能。

# 本项目

使用uv包管理器，python=3.12。

## 目录结构说明

```
- config/
    - config.yaml       : 主要配置文件
- log/
    - *                 : 日志文件
- resource/
    - cover/            : 视频封面图，使用avid命名
        - ssis-456.jpg
    - video/            : 下载的视频，使用avid命名
        - ssis-456/
            - ssis-456.json     : 视频元数据说明，应该含有下载源，下载时间，视频体积和视频时长信息
            - ssis-456.mp4      : 视频文件
- django_backend
- django_project
- db.sqlite3
```

## 数据结构说明

```
av_info: (id, avid, title, source)
```

## 配置文件说明

与原项目配置基本一致，但是网址额外添加cookie配置。

## 接口说明

前置url应为"/nassav"，不需要任何鉴权机制。

- `GET /api/resource/list` ：获取数据库中的所有(avid, title)
- `GET /api/resource/cover?avid=` ：根据avid获取封面图片
- `GET /api/resource/downloads/list` ： 获取已下载的所有视频的avid
- `GET /api/resource/downloads/metadata?avid=` ：根据avid获取视频元数据
- `POST /api/resource/new` ：通过avid获取title并下载cover，若遍历所有的源都无法获取，则删去该数据条目并返回错误信息
- `POST /api/resource/downloads/new` 通过avid下载视频，此avid必须已经验证可获取，即存在于数据库中

# 任务说明

1. 搭建django后端框架，给出接口声明，不需要实现，并给出需要下载的库
2. 使用同步任务机制实现接口
3. 使用celery + redis的异步机制实现异步下载
