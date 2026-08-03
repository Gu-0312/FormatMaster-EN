# -*- coding: utf-8 -*-
"""utils/format_helpers.py 纯函数测试。

覆盖 extract_urls / format_size / parse_time / format_time。
"""
import pytest
from utils.format_helpers import extract_urls, format_size, parse_time, format_time


# ── extract_urls ──────────────────────────────────────────
class TestExtractUrls:
    def test_single_url(self):
        assert extract_urls("https://example.com") == ["https://example.com"]

    def test_multiple_urls(self):
        text = "看 https://a.com 和 http://b.com 两个"
        result = set(extract_urls(text))
        assert result == {"https://a.com", "http://b.com"}

    def test_dedup(self):
        text = "https://a.com https://a.com https://a.com"
        assert extract_urls(text) == ["https://a.com"]

    def test_no_url(self):
        assert extract_urls("这里没有任何链接，纯中文文本") == []

    def test_url_with_path_and_query(self):
        text = "https://example.com/path?x=1&y=2"
        assert extract_urls(text) == ["https://example.com/path?x=1&y=2"]

    def test_excludes_chinese_punctuation(self):
        # URL 后跟中文逗号/句号不应被包含
        text = "https://example.com，继续"
        result = extract_urls(text)
        assert len(result) == 1
        assert result[0] == "https://example.com"


# ── format_size ───────────────────────────────────────────
class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(1023) == "1023 B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 512) == "512.0 MB"

    def test_gigabytes(self):
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1024 * 1024 * 1024 * 5) == "5.0 GB"

    def test_boundary_values(self):
        # 刚好低于各阈值边界
        assert format_size(1023) == "1023 B"
        assert format_size(1024 * 1024 - 1) == "1024.0 KB"


# ── parse_time ────────────────────────────────────────────
class TestParseTime:
    def test_hms(self):
        assert parse_time("01:30:45") == 5445  # 3600+1800+45

    def test_mmss(self):
        assert parse_time("05:30") == 330  # 300+30

    def test_ss(self):
        assert parse_time("90") == 90.0

    def test_decimal_seconds(self):
        assert parse_time("1.5") == 1.5

    def test_invalid_returns_zero(self):
        assert parse_time("") == 0
        assert parse_time("abc") == 0
        assert parse_time(":::") == 0

    def test_zero(self):
        assert parse_time("00:00:00") == 0


# ── format_time ──────────────────────────────────────────
class TestFormatTime:
    def test_zero(self):
        assert format_time(0) == "00:00:00.000"

    def test_standard(self):
        assert format_time(3661) == "01:01:01.000"

    def test_with_milliseconds(self):
        assert format_time(1.5) == "00:00:01.500"

    def test_large(self):
        # 超过 1 小时
        assert format_time(3600 * 10 + 60 * 5 + 3) == "10:05:03.000"
