"""Bounded HLS URI graph parsing, preserving ranges, IV and signed queries."""

import re
from dataclasses import dataclass
from urllib.parse import urljoin
from .policy import PlaybackGatewayError

URI_TAGS = {
    "#EXT-X-KEY": "key",
    "#EXT-X-SESSION-KEY": "key",
    "#EXT-X-MAP": "init",
    "#EXT-X-MEDIA": "manifest",
    "#EXT-X-I-FRAME-STREAM-INF": "manifest",
    "#EXT-X-SESSION-DATA": "data",
}


@dataclass(frozen=True)
class ManifestReference:
    line: int
    start: int
    end: int
    url: str
    kind: str


@dataclass(frozen=True)
class ParsedManifest:
    lines: tuple[str, ...]
    references: tuple[ManifestReference, ...]

    def render(self, replacements):
        by_line = {}
        for ref, replacement in zip(self.references, replacements, strict=True):
            by_line.setdefault(ref.line, []).append((ref.start, ref.end, replacement))
        lines = list(self.lines)
        for index, edits in by_line.items():
            for start, end, replacement in sorted(edits, reverse=True):
                lines[index] = lines[index][:start] + replacement + lines[index][end:]
        return ("\n".join(lines) + "\n").encode()


def parse_manifest(body, base, policy):
    if len(body) > 1024 * 1024:
        raise PlaybackGatewayError("manifest_too_large")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeError as error:
        raise PlaybackGatewayError("invalid_manifest") from error
    lines = text.splitlines()
    if not lines or lines[0].strip() != "#EXTM3U" or len(lines) > 20000:
        raise PlaybackGatewayError("invalid_manifest")
    master = any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
    if not master and "#EXT-X-ENDLIST" not in lines:
        raise PlaybackGatewayError("unsupported_live_playlist", 422)
    references = []
    variant = False
    for index, line in enumerate(lines):
        if "{$" in line or "\x00" in line:
            raise PlaybackGatewayError("unsupported_manifest_extension", 422)
        if not line or line.startswith("#"):
            tag = line.split(":", 1)[0]
            if tag in {
                "#EXT-X-PART",
                "#EXT-X-PRELOAD-HINT",
                "#EXT-X-RENDITION-REPORT",
                "#EXT-X-DEFINE",
                "#EXT-X-CONTENT-STEERING",
            }:
                raise PlaybackGatewayError("unsupported_manifest_extension", 422)
            if tag in {"#EXT-X-KEY", "#EXT-X-SESSION-KEY"}:
                method = re.search(r"(?:^|,)METHOD=([^,]+)", line.split(":", 1)[-1])
                keyformat = re.search(
                    r'(?:^|,)KEYFORMAT="([^"]+)"', line.split(":", 1)[-1]
                )
                if (
                    not method
                    or method[1] not in {"NONE", "AES-128"}
                    or (keyformat and keyformat[1] != "identity")
                ):
                    raise PlaybackGatewayError("unsupported_encryption", 422)
                if method[1] == "AES-128" and 'URI="' not in line:
                    raise PlaybackGatewayError("invalid_key")
            if tag in URI_TAGS:
                # Attribute scanning excludes commas inside quoted URI values.
                attrs = list(
                    re.finditer(
                        r'(?:^|,)([A-Z0-9-]+)=("[^"\r\n]*"|[^,\r\n]*)',
                        line.split(":", 1)[-1],
                    )
                )
                if len({a[1] for a in attrs}) != len(attrs):
                    raise PlaybackGatewayError("duplicate_attribute")
                matches = list(
                    re.finditer(r'(?:^|,)URI="([^"]+)"', line.split(":", 1)[-1])
                )
                if (
                    tag in {"#EXT-X-MAP", "#EXT-X-I-FRAME-STREAM-INF"}
                    or re.search(r"\bURI\s*=", line)
                ) and len(matches) != 1:
                    raise PlaybackGatewayError("invalid_uri_attribute")
                for match in matches:
                    offset = line.index(":") + 1
                    url = urljoin(base, match[1])
                    policy.validate(url)
                    references.append(
                        ManifestReference(
                            index,
                            offset + match.start(1),
                            offset + match.end(1),
                            url,
                            URI_TAGS[tag],
                        )
                    )
            elif re.search(r"\bURI\s*=", line):
                raise PlaybackGatewayError("unsupported_uri_tag", 422)
            if tag == "#EXT-X-STREAM-INF":
                variant = True
            continue
        url = urljoin(base, line.strip())
        policy.validate(url)
        references.append(
            ManifestReference(
                index, 0, len(line), url, "manifest" if variant else "segment"
            )
        )
        variant = False
    if not references or variant or len(references) > 10000:
        raise PlaybackGatewayError("invalid_manifest")
    return ParsedManifest(tuple(lines), tuple(references))
