"""Explicit local-network gateways for the P7 real-worker acceptance script only."""

from dataclasses import asdict
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import django
from django.conf import settings

django.setup()

if not getattr(settings, "TASK_CONTROL_ACCEPTANCE", False):
    raise RuntimeError("This worker fixture requires isolated acceptance settings")

from django_project.celery import app as app
from nassav import composition
from nassav.resource_data import AVDownloadInfo
from nassav.m3u8downloader import N_m3u8DL_RE

_original_download = composition.build_controlled_download
_original_scrape = composition.build_controlled_scrape
_original_translation = composition.build_controlled_translation
_original_events = composition.build_task_resource_events


class LocalPreparation:
    def __init__(self, control):
        self.control = control

    def fetch(self, route, *, seconds=20):
        with self.control.phase(seconds):
            response = self.control.request(
                "GET", settings.P7_BASE_URL + route, timeout=seconds
            )
            response.raise_for_status()
            return response.content

    def source(self, avid, source):
        page = self.fetch(f"/fixture/source?avid={avid}")
        return {
            "info": asdict(
                AVDownloadInfo(
                    avid=avid,
                    source="fixture",
                    source_title=f"来源标题 {avid}",
                    m3u8=settings.P7_BASE_URL + "/media/index.m3u8",
                )
            ),
            "source_name": "fixture",
        }, page

    def scrape(self, avid):
        import json

        return {
            "metadata": json.loads(self.fetch(f"/fixture/metadata?avid={avid}")),
            "scraped_by": "fixture",
        }

    def cover(self, prepared, path):
        data = self.fetch(f"/fixture/cover?avid={prepared['info']['avid']}")
        self.control.write(path, data)
        return True

    @staticmethod
    def avatars(prepared):
        avid = prepared["info"]["avid"]
        return [
            ("Shared Actor", "/fixture/avatar?avid=shared"),
            (f"Actor {avid}", f"/fixture/avatar?avid={avid}"),
        ]

    def avatar(self, url, path):
        self.control.write(path, self.fetch(url))
        return True


def download(lease):
    runner = _original_download(lease)
    runner.resolver = SimpleNamespace(
        resolve=lambda avid, **kwargs: SimpleNamespace(
            info=SimpleNamespace(m3u8=settings.P7_BASE_URL + "/media/index.m3u8"),
            domain="localhost",
        )
    )
    native = N_m3u8DL_RE(proxy=None)
    native.tool_path = settings.P7_BINARY
    runner.downloader = SimpleNamespace(
        download=partial(native.download, thread_count=1, retry_count=0),
        ensure_mp4=native.ensure_mp4,
    )
    return runner


def scrape():
    runner = _original_scrape()
    runner.preparation = LocalPreparation
    return runner


def events():
    adapter = _original_events()
    original = adapter.publish

    def publish(event, avid, event_id):
        if (Path(settings.P7_ROOT) / "fail-event").exists():
            raise RuntimeError("P7 isolated event delivery interruption")
        original(event, avid, event_id)

    adapter.publish = publish
    return adapter


def translation():
    runner = _original_translation()

    class LocalTranslator:
        def __init__(self, control):
            self.control = control

        def translate(self, title):
            response = self.control.request(
                "POST",
                settings.P7_BASE_URL + "/fixture/translation",
                timeout=20,
                json={"title": title},
            )
            response.raise_for_status()
            return response.json()["translated"]

    runner.translator = LocalTranslator
    return runner


composition.build_controlled_download = download
composition.build_controlled_scrape = scrape
composition.build_controlled_translation = translation

composition.build_task_resource_events = events
