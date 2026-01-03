# TODO_LIST

## 前端

- 增加设置页，主要迁移cookie设置，并加入cookie展示功能
- `avid: title`缓存有时太顽固，无法及时更新

## 后端

- 接口`GET /nassav/api/resources/?sort_by=video_create_time`被调用时，未下载的视频也会被返回
- 元数据刮削时的女优名问题：以[https://www.javbus.com/JUR-448]为例，"めぐり（藤浦めぐ）"会刮削成"めぐり（藤"
- 另外，当使用javbus刮削元数据时，html会附带如下内容：`<img src="/pics/actress/305_a.jpg" title="めぐり（藤浦めぐ）">`，因此可以用于获取女优头像
- 使用javbus获取封面图
- 增强配置的灵活性，尽量可以做到不重启热更新，增强前端配置功能
