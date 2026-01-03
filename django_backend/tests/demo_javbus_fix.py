#!/usr/bin/env python
"""
演示 Javbus 女优名解析修复

展示修复前后的对比效果
"""
import re
from pathlib import Path


def old_method(html: str) -> list:
    """旧方法：从 span 标签提取（会被截断）"""
    actor_matches = re.findall(
        r'<a class="avatar-box"[^>]*>\s*<div[^>]*>\s*'
        r"<img[^>]*>\s*</div>\s*<span>([^<]+)</span>",
        html,
    )
    return actor_matches


def new_method(html: str) -> list:
    """新方法：从 img title 属性提取（完整名字）"""
    actor_matches = re.findall(
        r'<a class="avatar-box"[^>]*>\s*<div[^>]*>\s*'
        r'<img[^>]*title="([^"]+)"[^>]*>',
        html,
    )
    return actor_matches


def main():
    # 读取测试 HTML
    html_path = Path(__file__).parent.parent / "JUR-448.html"
    if not html_path.exists():
        print("❌ JUR-448.html 文件不存在")
        return

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    print("=" * 70)
    print("Javbus 女优名解析修复对比")
    print("=" * 70)
    print()

    # 旧方法
    print("🔴 修复前（从 <span> 标签提取）:")
    old_actors = old_method(html)
    for actor in old_actors:
        print(f"   - {actor}")
        if "（" in actor and "）" not in actor:
            print(f"     ⚠️  名字被截断！缺少右括号")

    print()
    print("-" * 70)
    print()

    # 新方法
    print("✅ 修复后（从 <img title> 属性提取）:")
    new_actors = new_method(html)
    for actor in new_actors:
        print(f"   - {actor}")
        if "（" in actor:
            if "）" in actor:
                print(f"     ✓ 括号完整，名字未被截断")
            else:
                print(f"     ⚠️  仍然存在截断问题")

    print()
    print("=" * 70)
    print()

    # 统计
    old_truncated = sum(1 for a in old_actors if "（" in a and "）" not in a)
    new_truncated = sum(1 for a in new_actors if "（" in a and "）" not in a)

    print(f"📊 统计结果:")
    print(f"   旧方法截断数: {old_truncated}/{len(old_actors)}")
    print(f"   新方法截断数: {new_truncated}/{len(new_actors)}")
    print()

    if new_truncated == 0 and old_truncated > 0:
        print("🎉 修复成功！所有女优名都完整提取")
    elif new_truncated < old_truncated:
        print("✅ 修复部分有效，减少了截断情况")
    else:
        print("❌ 修复未生效")


if __name__ == "__main__":
    main()
