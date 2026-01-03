# 测试文件状态分析

## ✅ 已重构完成（使用 pytest + fixtures）

1. **test_actors_api.py** - 演员 API 测试
2. **test_genres_api.py** - 类别 API 测试
3. **test_resources_list.py** - 资源列表测试
4. **test_views_resource.py** - 资源视图测试
5. **test_serializers.py** - 序列化器测试
6. **test_actor_avatar_api.py** - 演员头像 API 测试（已存在）
7. **test_actors_list_filter.py** - 演员列表过滤测试（已存在）

## 📦 保留（已使用 pytest，无需修改）

8. **test_source_cookie_api.py** - Source Cookie API 测试
   - 状态：已使用 pytest，代码规范
   - 操作：保留

9. **test_user_settings.py** - 用户设置 API 测试
   - 状态：已使用 pytest，代码规范
   - 操作：保留

10. **test_actor_avatar_extraction.py** - 演员头像提取单元测试
    - 状态：纯单元测试，不依赖数据库
    - 操作：保留

11. **test_actor_avatar_placeholder.py** - 头像占位符测试
    - 状态：已使用 pytest
    - 操作：保留

## 🔄 建议重构（使用 Django TestCase）

12. **test_fix_actor_names.py** - 演员名称修复测试
    - 状态：使用 Django TestCase
    - 优先级：中
    - 操作：可重构为 pytest

13. **test_javbus_actor_parsing.py** - Javbus 演员解析测试
    - 状态：使用 Django TestCase
    - 优先级：中
    - 操作：可重构为 pytest

14. **test_video_time_sort_filter.py** - 视频时间排序过滤测试
    - 状态：使用 Django TestCase
    - 优先级：中
    - 操作：可重构为 pytest

15. **test_ws.py** - WebSocket 测试
    - 状态：使用 Django TransactionTestCase
    - 优先级：低（WebSocket 测试较特殊）
    - 操作：暂时保留，功能测试优先

## 🗑️ 建议删除或归档

16. **demo_javbus_fix.py** - Javbus 修复演示脚本
    - 状态：演示脚本，非正式测试
    - 操作：**可删除**（功能已在 test_javbus_actor_parsing.py 中测试）

17. **test_genres_filtering.py** - 类别过滤独立脚本
    - 状态：独立脚本，功能已被 test_genres_api.py 覆盖
    - 操作：**可删除**（功能重复）

## 🔧 工具脚本测试（保留）

18. **test_javbus_avatar_integration.py** - Javbus 头像集成测试
19. **test_javbus_cover_extraction.py** - Javbus 封面提取测试
20. **test_cover_download_priority.py** - 封面下载优先级测试
21. **test_scraper_download_cover.py** - 爬虫下载封面测试
22. **test_translation_cleaning.py** - 翻译清理测试
23. **test_translator.py** - 翻译器测试（需要 Ollama）
24. **test_translator_manager.py** - 翻译管理器测试

**状态**: 这些是功能测试/工具测试脚本，用于测试特定功能模块
**操作**: 保留，但可考虑标准化为 pytest 格式

## 📜 Shell 脚本（保留）

25. **test_api.sh** - API 综合测试脚本
26. **test_mock_download.sh** - 模拟下载测试
27. **test_websocket.sh** - WebSocket 测试脚本
28. **test_full_task_queue.sh** - 任务队列测试
29. **test_progress_display.sh** - 进度显示测试

**状态**: Shell 脚本，用于集成测试和手动测试
**操作**: 保留

---

## 推荐行动方案

### 立即操作

1. **删除冗余文件**:
   ```bash
   rm tests/demo_javbus_fix.py
   rm tests/test_genres_filtering.py
   ```
   理由：功能已被其他测试覆盖

### 可选后续操作（Phase 3）

2. **重构中优先级文件**（3个文件，约2-3小时）:
   - test_fix_actor_names.py
   - test_javbus_actor_parsing.py
   - test_video_time_sort_filter.py

### 保持现状

3. **以下文件保持现状**:
   - 所有 Shell 脚本（集成测试）
   - 工具测试脚本（功能验证）
   - 已使用 pytest 的测试
   - WebSocket 测试（特殊场景）

---

## 总结

- ✅ **已完成重构**: 7个文件
- 🗑️ **可删除**: 2个文件（demo_javbus_fix.py, test_genres_filtering.py）
- 🔄 **可选重构**: 3个文件（中优先级）
- 📦 **保留**: 其余所有文件

**删除建议**: demo_javbus_fix.py 和 test_genres_filtering.py 是冗余的，可以安全删除。
