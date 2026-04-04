from nassav.m3u8downloader.N_m3u8DL_RE import N_m3u8DL_RE


def test_speed_pattern_matches_classic_speed_unit():
    line = "已下载: 45.2% | 速度: 5.2MB/s"

    match = __import__("re").search(
        N_m3u8DL_RE.SPEED_PATTERN, line, __import__("re").IGNORECASE
    )

    assert match is not None
    assert match.group(1) == "5.2MB/s"


def test_speed_pattern_matches_binary_speed_unit():
    line = "45.2% 122.3MiB/s eta 00:10"

    match = __import__("re").search(
        N_m3u8DL_RE.SPEED_PATTERN, line, __import__("re").IGNORECASE
    )

    assert match is not None
    assert match.group(1) == "122.3MiB/s"


def test_speed_pattern_matches_ps_suffix():
    line = "下载进度 91.4% speed=8.8 MBps"

    match = __import__("re").search(
        N_m3u8DL_RE.SPEED_PATTERN, line, __import__("re").IGNORECASE
    )

    assert match is not None
    assert match.group(1) == "8.8 MBps"
