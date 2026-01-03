"""测试Javbus演员头像URL提取功能"""
import re

import pytest


def test_avatar_url_extraction():
    """测试从Javbus HTML提取演员头像URL"""
    # 模拟Javbus HTML片段
    html = """
    <a class="avatar-box" href="/ja/star/okq">
        <div class="photo-frame">
            <img src="/pics/actress/305_a.jpg" title="めぐり（藤浦めぐ）">
        </div>
    </a>
    <a class="avatar-box" href="/ja/star/abc">
        <div class="photo-frame">
            <img src="/pics/actress/123_a.jpg" title="波多野結衣">
        </div>
    </a>
    """

    # 提取演员名和头像URL
    actor_pattern = re.compile(
        r'<a class="avatar-box"[^>]*>\s*<div[^>]*>\s*'
        r'<img[^>]*src="([^"]+)"[^>]*title="([^"]+)"[^>]*>',
        re.DOTALL,
    )
    matches = actor_pattern.findall(html)

    assert len(matches) == 2

    # 第一个演员
    src1, name1 = matches[0]
    assert name1 == "めぐり（藤浦めぐ）"
    assert src1 == "/pics/actress/305_a.jpg"

    # 第二个演员
    src2, name2 = matches[1]
    assert name2 == "波多野結衣"
    assert src2 == "/pics/actress/123_a.jpg"


def test_avatar_url_conversion():
    """测试相对路径转完整URL"""
    domain = "www.javbus.com"
    relative_url = "/pics/actress/305_a.jpg"

    # 转为完整URL
    if relative_url.startswith("/"):
        full_url = f"https://{domain}{relative_url}"
    else:
        full_url = relative_url

    assert full_url == "https://www.javbus.com/pics/actress/305_a.jpg"


def test_avatar_dict_creation():
    """测试创建演员-头像URL字典"""
    domain = "www.javbus.com"
    matches = [
        ("/pics/actress/305_a.jpg", "めぐり（藤浦めぐ）"),
        ("/pics/actress/123_a.jpg", "波多野結衣"),
    ]

    actor_avatars = {}
    for src, name in matches:
        if src.startswith("/"):
            avatar_url = f"https://{domain}{src}"
        else:
            avatar_url = src
        actor_avatars[name] = avatar_url

    assert len(actor_avatars) == 2
    assert actor_avatars["めぐり（藤浦めぐ）"] == "https://www.javbus.com/pics/actress/305_a.jpg"
    assert actor_avatars["波多野結衣"] == "https://www.javbus.com/pics/actress/123_a.jpg"


def test_filename_extraction():
    """测试从URL提取文件名"""
    url = "https://www.javbus.com/pics/actress/305_a.jpg"
    filename = url.rstrip("/").split("/")[-1]

    assert filename == "305_a.jpg"
