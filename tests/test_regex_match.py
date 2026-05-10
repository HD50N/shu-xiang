"""Unit tests for the regex enum extractor."""

from __future__ import annotations

import pytest

from voice.regex_match import extract_enum


@pytest.mark.parametrize(
    "transcript, expected",
    [
        ("我自己运营", "member-managed"),
        ("我自己", "member-managed"),
        ("我一个人来管", "member-managed"),
        ("成员管理", "member-managed"),
        ("member-managed", "member-managed"),
        ("Member Managed", "member-managed"),
        ("雇个经理", "manager-managed"),
        ("找人来管理", "manager-managed"),
        ("请人来运营", "manager-managed"),
        ("manager-managed", "manager-managed"),
    ],
)
def test_management_structure_hits(transcript, expected):
    r = extract_enum("management_structure", transcript)
    assert r.value == expected
    assert r.source == "regex"
    assert r.confidence >= 0.65
    assert r.elapsed_ms < 5  # sub-5ms target


@pytest.mark.parametrize(
    "transcript, expected",
    [
        ("永久", "perpetual"),
        ("长期", "perpetual"),
        ("一直经营", "perpetual"),
        ("perpetual", "perpetual"),
        ("固定日期", "fixed"),
        ("5年后结束", "fixed"),
        ("临时项目", "fixed"),
    ],
)
def test_duration_hits(transcript, expected):
    r = extract_enum("duration", transcript)
    assert r.value == expected
    assert r.source == "regex"


@pytest.mark.parametrize(
    "transcript",
    [
        "",
        "嗯哎呀",
        "我不知道",
        "随便",
    ],
)
def test_misses(transcript):
    r = extract_enum("management_structure", transcript)
    assert r.value is None
    assert r.source == "miss"


def test_unknown_field_misses():
    r = extract_enum("not_a_field", "我自己")
    assert r.value is None
    assert r.source == "miss"
