#!/usr/bin/env python3
"""
导出 Jable 首页标签

功能：
1. 请求 Jable 首页
2. 解析首页中的标签和分类链接
3. 将标签名与对应 URL 保存到本地临时文件

使用方法：
    uv run python scripts/export_jable_home_tags.py [--output PATH] [--verbose]

选项：
    --output PATH  输出文件路径，默认 /tmp/nassav_jable_home_tags.json
    --verbose      显示详细日志
"""

import argparse
from dataclasses import asdict, dataclass
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import django
from bs4 import BeautifulSoup

script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

from django.conf import settings
from loguru import logger
from nassav.source import Jable

DEFAULT_OUTPUT_PATH = Path("/tmp/nassav_jable_home_tags.json")


@dataclass(frozen=True)
class JableHomeTag:
    name: str
    url: str
    kind: str


def configure_logger(verbose: bool) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level="DEBUG" if verbose else "INFO",
    )


def get_proxy() -> str | None:
    if getattr(settings, "PROXY_ENABLED", False):
        return getattr(settings, "PROXY_URL", None)
    return None


def normalize_jable_tag_name(raw_name: str) -> str:
    name = str(raw_name or "").strip()
    name = re.sub(r"\s+\d+\s*部影片\s*$", "", name)
    return name.strip()


def parse_jable_home_tags(
    html: str,
    *,
    base_url: str = "https://jable.tv/",
) -> list[JableHomeTag]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[JableHomeTag] = []
    seen_urls: set[str] = set()
    allowed_hosts = {"", urlparse(base_url).netloc.casefold()}

    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        if parsed.netloc.casefold() not in allowed_hosts:
            continue

        path = parsed.path.rstrip("/")
        kind = ""
        if path.startswith("/tags/"):
            kind = "tag"
        elif path.startswith("/categories/"):
            kind = "category"
        else:
            continue

        name = normalize_jable_tag_name(anchor.get_text(" ", strip=True))
        if not name:
            continue

        normalized_url = parsed._replace(fragment="").geturl()
        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)
        items.append(
            JableHomeTag(
                name=name,
                url=normalized_url,
                kind=kind,
            )
        )

    return items


def dump_jable_home_tags(tags: list[JableHomeTag]) -> list[dict[str, str]]:
    return [asdict(tag) for tag in tags]


def fetch_homepage_html(jable: Jable) -> str:
    home_url = f"https://{jable.domain}/"
    html = jable.fetch_html(home_url, referer=home_url)
    if html:
        return html

    logger.warning("首次抓取 Jable 首页失败，尝试刷新 cookie 后重试")
    jable.set_cookie_auto(force_refresh=True)
    html = jable.fetch_html(home_url, referer=home_url)
    if not html:
        raise RuntimeError(f"抓取 Jable 首页失败: {home_url}")
    return html


def export_jable_home_tags(
    *,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    verbose: bool = False,
) -> dict[str, object]:
    configure_logger(verbose)

    jable = Jable(proxy=get_proxy())
    jable.load_cookie_from_db()

    html = fetch_homepage_html(jable)
    tags = parse_jable_home_tags(html, base_url=f"https://{jable.domain}/")
    payload = {
        "source": "Jable",
        "homepage_url": f"https://{jable.domain}/",
        "total": len(tags),
        "items": dump_jable_home_tags(tags),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    logger.info(f"已导出 {len(tags)} 个首页标签到: {output_path}")
    return {
        "output_path": str(output_path),
        "total": len(tags),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="导出 Jable 首页中的标签与分类链接",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 使用默认临时文件输出
  uv run python scripts/export_jable_home_tags.py

  # 指定输出路径
  uv run python scripts/export_jable_home_tags.py --output /tmp/jable-tags.json

  # 输出详细日志
  uv run python scripts/export_jable_home_tags.py --verbose
        """,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"输出文件路径，默认 {DEFAULT_OUTPUT_PATH}",
    )
    parser.add_argument("--verbose", action="store_true", help="显示详细日志")
    args = parser.parse_args()

    try:
        export_jable_home_tags(output_path=args.output, verbose=args.verbose)
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(0)
    except Exception as exc:
        logger.exception(f"执行失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
