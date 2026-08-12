from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from backend.ecos import calculate_unsold_score


PRICE_URL = "https://land.seoul.go.kr/land/rtms/getAptDealPriceAvgList.do"
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Row:
    month: str
    price: float
    unsold: float
    score: int


def fetch_prices() -> dict[str, float]:
    body = urllib.parse.urlencode(
        {
            "selectSigungu": "11000",
            "changeBgnde": "202001",
            "changeEndde": "202608",
            "selectKind": "S",
        }
    ).encode()
    request = urllib.request.Request(
        PRICE_URL, data=body, headers={"User-Agent": "GoJump/0.1"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return {
        row["statYm"]: float(row["avgAmt"])
        for row in payload["result"]
        if row["trGbnNm"].strip() == "매매"
    }


def load_rows() -> list[Row]:
    prices = fetch_prices()
    with sqlite3.connect(ROOT / "data/gojump.sqlite3") as connection:
        unsold = connection.execute(
            "SELECT period, value FROM unsold_observations ORDER BY period"
        ).fetchall()

    months = [month for month, _ in unsold]
    values = [float(value) for _, value in unsold]
    scores: dict[str, int] = {}
    for index, month in enumerate(months):
        # Production uses at most the latest 10 years. Each historical score only
        # sees observations that were available in that month.
        history = values[max(0, index - 120) : index + 1]
        scores[month] = calculate_unsold_score(history)

    common = [month for month in months if month in prices]
    price_values = [prices[month] for month in common]
    smoothed = {
        month: sum(price_values[max(0, i - 2) : i + 1]) / min(3, i + 1)
        for i, month in enumerate(common)
    }
    unsold_by_month = dict(unsold)
    return [
        Row(month, smoothed[month], float(unsold_by_month[month]), scores[month])
        for month in common
    ]


def confusion(rows: list[Row], horizon: int, decline: float, threshold: int) -> dict:
    evaluated = rows[:-horizon]
    actual = [
        min(item.price for item in rows[i + 1 : i + horizon + 1])
        <= row.price * (1 - decline)
        for i, row in enumerate(evaluated)
    ]
    predicted = [row.score >= threshold for row in evaluated]
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(not p and a for p, a in zip(predicted, actual))
    tn = sum(not p and not a for p, a in zip(predicted, actual))
    return {
        "months": len(evaluated),
        "positives": sum(actual),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
    }


def peak_episodes(rows: list[Row], horizon: int = 12, decline: float = 0.10) -> list[dict]:
    candidates = []
    for i, row in enumerate(rows[:-horizon]):
        future_low = min(item.price for item in rows[i + 1 : i + horizon + 1])
        if future_low <= row.price * (1 - decline):
            candidates.append(i)
    groups: list[list[int]] = []
    for index in candidates:
        if not groups or index > groups[-1][-1] + 1:
            groups.append([index])
        else:
            groups[-1].append(index)

    episodes = []
    for group in groups:
        peak_index = max(group, key=lambda index: rows[index].price)
        peak = rows[peak_index]
        signal_index = next(
            (
                i
                for i in range(max(0, peak_index - 6), min(len(rows), peak_index + 13))
                if rows[i].score >= 65
            ),
            None,
        )
        episodes.append(
            {
                "peak": peak.month,
                "price": round(peak.price),
                "unsold": round(peak.unsold),
                "score": peak.score,
                "first_signal": rows[signal_index].month if signal_index is not None else None,
                "offset_months": signal_index - peak_index if signal_index is not None else None,
            }
        )
    return episodes


def past_drawdown(rows: list[Row], threshold: int = 65) -> dict:
    evaluated = rows[12:]
    actual = [
        row.price <= max(item.price for item in rows[i : i + 12]) * 0.90
        for i, row in enumerate(evaluated)
    ]
    predicted = [row.score >= threshold for row in evaluated]
    tp = sum(p and a for p, a in zip(predicted, actual))
    fp = sum(p and not a for p, a in zip(predicted, actual))
    fn = sum(not p and a for p, a in zip(predicted, actual))
    return {
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
    }


if __name__ == "__main__":
    rows = load_rows()
    result = {
        "range": [rows[0].month, rows[-1].month],
        "rows": len(rows),
        "latest": rows[-1].__dict__,
        "future_6m_drop_10": confusion(rows, 6, 0.10, 65),
        "future_12m_drop_10": confusion(rows, 12, 0.10, 65),
        "future_12m_drop_15": confusion(rows, 12, 0.15, 65),
        "past_12m_drawdown_10": past_drawdown(rows),
        "episodes": peak_episodes(rows),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
