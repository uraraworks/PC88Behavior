#!/usr/bin/env python3
"""bit6帰属検査の、実測に依存しない判定部分。"""
from __future__ import annotations

import search_error_response_candidate as search


EXPECTED_SCREEN = (
    10,
    215,
    "cca99cfdfdc10336346467523d8d8e5bda8096fda4d9c34ab5f457364bef7379",
)


def screen_tuple(result: search.AbstractResult) -> tuple[int, int, str]:
    return (result.screen_line_count, result.screen_char_count,
            result.screen_sha256)


def judge_measurements(reference_measurement, default_measurement,
                       broken_measurement):
    """measure_onceの新しい(result, receipts)型を展開して判定する。"""
    reference, _reference_receipts = reference_measurement
    default, _default_receipts = default_measurement
    broken, _broken_receipts = broken_measurement
    default_metric = search.compare_result(reference, default, 0)
    broken_metric = search.compare_result(reference, broken, 1)
    default_ok = (len(default.exchange) == 60
                  and default_metric.exchange_prefix == 60
                  and default_metric.exchange_exact
                  and screen_tuple(default) == EXPECTED_SCREEN
                  and all((default_metric.screen_lines_match,
                           default_metric.screen_chars_match,
                           default_metric.screen_sha256_match)))
    broken_ok = (broken_metric.exchange_prefix == 38
                 and not broken_metric.exchange_exact
                 and not any((broken_metric.screen_lines_match,
                              broken_metric.screen_chars_match,
                              broken_metric.screen_sha256_match)))
    return default_ok and broken_ok, default_metric, broken_metric
