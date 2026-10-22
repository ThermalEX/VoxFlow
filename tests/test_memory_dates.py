from datetime import date

import pytest

from voxflow.memory_dates import describe_date, resolve

TUESDAY = date(2026, 10, 20)


@pytest.mark.parametrize("phrase, expected", [
    ("今天下午四点", date(2026, 10, 20)),
    ("今晚八点", date(2026, 10, 20)),
    ("明天上午十点", date(2026, 10, 21)),
    ("后天下午两点", date(2026, 10, 22)),
    ("大后天", date(2026, 10, 23)),
    ("周三下午三点", date(2026, 10, 21)),
    ("星期五晚上七点", date(2026, 10, 23)),
    ("周一", date(2026, 10, 26)),  # this week's Monday has passed
    ("周二", date(2026, 10, 20)),
    ("这周日", date(2026, 10, 25)),
    ("下周一", date(2026, 10, 26)),
    ("下周三", date(2026, 10, 28)),
    ("下下周五", date(2026, 11, 6)),
    ("礼拜天", date(2026, 10, 25)),
    ("10月28日之前", date(2026, 10, 28)),
    ("十一月三号", date(2026, 11, 3)),
    ("12月31日", date(2026, 12, 31)),
    ("下个月三号", date(2026, 11, 3)),
    ("1月5号", date(2027, 1, 5)),
    ("tomorrow at 9", date(2026, 10, 21)),
    ("Thursday at 2pm", date(2026, 10, 22)),
    ("next Monday", date(2026, 10, 26)),
    ("next Thursday", date(2026, 10, 29)),
    ("November 3rd", date(2026, 11, 3)),
    ("Nov 3", date(2026, 11, 3)),
])
def test_spoken_times_point_to_one_day(phrase, expected):
    assert resolve(phrase, TUESDAY) == expected


@pytest.mark.parametrize("phrase", ["每周一早上九点", "every Monday", "下午三点", "月底", "2月30日", "soon", ""])
def test_times_that_name_no_single_day_resolve_to_nothing(phrase):
    assert resolve(phrase, TUESDAY) is None


def test_a_month_and_day_long_past_means_next_year():
    assert resolve("3月1日", TUESDAY) == date(2027, 3, 1)
    assert resolve("9月1日", TUESDAY) == date(2026, 9, 1)  # recent: still this year


def test_december_rolls_next_month_into_january():
    assert resolve("下个月五号", date(2026, 12, 10)) == date(2027, 1, 5)


def test_dates_are_described_with_their_weekday():
    assert describe_date(date(2026, 10, 21)) == "10月21日周三"
    assert describe_date(date(2026, 10, 21), "en") == "Wed 21 Oct"
