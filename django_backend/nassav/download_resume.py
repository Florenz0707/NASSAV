"""Validate cached HLS bytes against fresh media before native CLI reuse.

Only closed, single-track MPEG-TS VOD has a verified cache index contract.
Other input may download, but requires explicit restart after interruption.
"""

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from curl_cffi import requests, CurlOpt
from curl_cffi.curl import CURL_WRITEFUNC_ERROR


class DownloadRestartRequired(RuntimeError):
    pass


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def checked_cache_path(workspace: Path, output_name: str, relative: str) -> Path:
    parts = Path(relative).parts
    if (
        len(parts) != 4
        or parts[:2] != ("temp", output_name)
        or any(part in {".", ".."} for part in parts)
        or not Path(parts[-1]).stem.isdigit()
    ):
        raise DownloadRestartRequired("分片路径不再属于工作区")
    current = workspace
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise DownloadRestartRequired("分片路径包含符号链接")
    return current


class HLSResumeGuard:
    def __init__(self, *, proxy: str | None = None, fetch: Callable | None = None):
        self.proxy = proxy
        self.fetch = fetch or self._fetch

    def _fetch(self, url: str, headers: dict, check: Callable) -> bytes:
        check()
        chunks, size, errors = [], 0, []

        def receive(chunk):
            nonlocal size
            try:
                check()
                size += len(chunk)
                if size > 64 * 1024 * 1024:
                    raise DownloadRestartRequired("分片超出校验上限，不能安全续传")
                chunks.append(chunk)
                return len(chunk)
            except Exception as error:
                errors.append(error)
                return CURL_WRITEFUNC_ERROR

        with requests.Session(
            curl_options={
                CurlOpt.PROXY: self.proxy or "",
                CurlOpt.NOPROXY: "" if self.proxy else "*",
            }
        ) as session:
            session.trust_env = False
            try:
                # Non-stream curl applies a 20s total deadline, including slow trickle.
                response = session.get(
                    url, headers=headers, timeout=(5, 15), content_callback=receive
                )
                response.raise_for_status()
            except Exception:
                if errors:
                    raise errors[0]
                raise
        check()
        return b"".join(chunks)

    def describe(
        self, url: str, headers: dict, check: Callable, depth: int = 0
    ) -> dict:
        if depth > 3:
            raise DownloadRestartRequired("播放列表嵌套超出校验上限")
        text = self.fetch(url, headers, check).decode("utf-8-sig")
        if not text.startswith("#EXTM3U"):
            raise ValueError("不是有效的 HLS 播放列表")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if any(line.startswith("#EXT-X-STREAM-INF:") for line in lines):
            variants = []
            for index, line in enumerate(lines[:-1]):
                if line.startswith("#EXT-X-STREAM-INF:"):
                    bandwidth = re.search(
                        r"(?:^|,)BANDWIDTH=(\d+)", line.split(":", 1)[1]
                    )
                    variants.append(
                        (
                            int(bandwidth.group(1)) if bandwidth else 0,
                            urljoin(url, lines[index + 1]),
                        )
                    )
            result = self.describe(max(variants)[1], headers, check, depth + 1)
            if any(line.startswith("#EXT-X-MEDIA:") for line in lines):
                result["safe"] = False
            return result
        urls = [urljoin(url, line) for line in lines if not line.startswith("#")]
        normalized = [
            canonical_url(urljoin(url, line)) if not line.startswith("#") else line
            for line in lines
        ]
        keys, current, key_cache, supported = [], None, {}, True
        sequence = next(
            (
                int(line.split(":", 1)[1])
                for line in lines
                if line.startswith("#EXT-X-MEDIA-SEQUENCE:")
            ),
            0,
        )
        for index, line in enumerate(lines):
            if line.startswith("#EXT-X-KEY:"):
                attributes = dict(
                    re.findall(r'([A-Z-]+)=("[^"]*"|[^,]+)', line.split(":", 1)[1])
                )
                method = attributes.get("METHOD")
                if method == "NONE":
                    current = None
                elif (
                    method == "AES-128"
                    and attributes.get("KEYFORMAT", '"identity"') == '"identity"'
                ):
                    key_url = urljoin(url, attributes["URI"].strip('"'))
                    if key_url not in key_cache:
                        key_cache[key_url] = self.fetch(key_url, headers, check)
                    key = key_cache[key_url]
                    if len(key) != 16:
                        raise ValueError("AES-128 密钥长度无效")
                    current = {"key": key.hex(), "iv": attributes.get("IV")}
                    normalized[index] = (
                        f"AES-128:{canonical_url(key_url)}:{hashlib.sha256(key).hexdigest()}:{attributes.get('IV')}"
                    )
                else:
                    supported = False
            elif not line.startswith("#"):
                keys.append(
                    {**current, "sequence": sequence + len(keys)} if current else None
                )
        return {
            "url": url,
            "identity": hashlib.sha256("\n".join(normalized).encode()).hexdigest(),
            "urls": urls,
            "keys": keys,
            "duration": sum(
                float(line.split(":", 1)[1].split(",", 1)[0])
                for line in lines
                if line.startswith("#EXTINF:")
            ),
            "safe": supported
            and "#EXT-X-ENDLIST" in lines
            and bool(urls)
            and all(urlsplit(item).path.lower().endswith(".ts") for item in urls)
            and not any(
                line.startswith(
                    ("#EXT-X-MAP:", "#EXT-X-BYTERANGE:", "#EXT-X-DISCONTINUITY")
                )
                for line in lines
            ),
        }

    @staticmethod
    def snapshot(
        workspace: Path, output_name: str, check: Callable | None = None
    ) -> dict:
        result = {}
        for file in workspace.glob(f"temp/{output_name}/*/*.ts"):
            if check:
                check()
            checked_cache_path(workspace, output_name, str(file.relative_to(workspace)))
            if file.stat().st_size > 64 * 1024 * 1024:
                raise DownloadRestartRequired("分片超出校验上限，请终止后重新下载")
            result[str(file.relative_to(workspace))] = hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
        return result

    def prepare(
        self,
        workspace: Path,
        output_name: str,
        manifest: dict,
        checkpoint: dict | None,
        headers: dict,
        check: Callable,
    ) -> None:
        if checkpoint:
            previous = checkpoint["manifest"]
            if (
                not previous["safe"]
                or not manifest["safe"]
                or previous["identity"] != manifest["identity"]
            ):
                raise DownloadRestartRequired(
                    "播放内容或轨道无法确认，请终止后重新下载"
                )
            expected = checkpoint.get("segments", {})
            for relative, digest in expected.items():
                file = checked_cache_path(workspace, output_name, relative)
                if not file.exists():
                    continue
                if file.is_symlink() or file not in workspace.glob(
                    f"temp/{output_name}/*/*.ts"
                ):
                    raise DownloadRestartRequired("分片路径不再属于工作区")
                index = int(file.stem)
                if index >= len(manifest["urls"]):
                    raise DownloadRestartRequired("分片编号超出轨道范围")
                remote = self.fetch(manifest["urls"][index], headers, check)
                key = manifest.get("keys", [None] * len(manifest["urls"]))[index]
                if key:
                    from cryptography.hazmat.primitives.ciphers import (
                        Cipher,
                        algorithms,
                        modes,
                    )
                    from cryptography.hazmat.primitives.padding import PKCS7

                    iv = (
                        int(key["iv"], 16).to_bytes(16, "big")
                        if key["iv"]
                        else key["sequence"].to_bytes(16, "big")
                    )
                    decryptor = Cipher(
                        algorithms.AES(bytes.fromhex(key["key"])), modes.CBC(iv)
                    ).decryptor()
                    padded = decryptor.update(remote) + decryptor.finalize()
                    unpadder = PKCS7(128).unpadder()
                    remote = unpadder.update(padded) + unpadder.finalize()
                if hashlib.sha256(remote).hexdigest() != digest:
                    raise DownloadRestartRequired(
                        "缓存分片与当前源内容不一致，请终止后重新下载"
                    )
                if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
                    file.unlink()  # Only verified source bytes may be downloaded again.
            # Unknown/unrecorded cache is never reused; .tmp files are incomplete.
            for file in workspace.glob(f"temp/{output_name}/*/*"):
                if file.is_symlink():
                    raise DownloadRestartRequired("缓存包含符号链接")
                if (
                    file.is_file()
                    and file.suffix in {".ts", ".tmp"}
                    and str(file.relative_to(workspace)) not in expected
                ):
                    file.unlink()
        elif (workspace / "temp").exists():
            raise DownloadRestartRequired("缓存没有可信检查点，请终止后重新下载")
        # An interrupted merge/output is private and must not be mistaken for success.
        for suffix in (".mp4", ".mkv", ".ts"):
            path = workspace / f"{output_name}{suffix}"
            if path.is_symlink():
                raise DownloadRestartRequired("输出路径包含符号链接")
            path.unlink(missing_ok=True)
