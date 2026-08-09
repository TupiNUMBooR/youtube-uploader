from __future__ import annotations

from datetime import timezone

from youtube_uploader.time_utils import iso_utc, parse_iso_utc


def test_parse_iso_utc_z_suffix() -> None:
    dt = parse_iso_utc("2026-05-09T05:12:44Z")

    assert dt.tzinfo is not None
    assert dt.utcoffset() == timezone.utc.utcoffset(dt)


def test_iso_utc_outputs_z_suffix() -> None:
    dt = parse_iso_utc("2026-05-09T05:12:44+00:00")

    assert iso_utc(dt) == "2026-05-09T05:12:44Z"


def test_parse_naive_datetime_as_utc() -> None:
    dt = parse_iso_utc("2026-05-09T05:12:44")

    assert iso_utc(dt) == "2026-05-09T05:12:44Z"
