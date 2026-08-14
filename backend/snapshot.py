from __future__ import annotations

import copy
import datetime as dt
import json
import statistics
from pathlib import Path

from backend.ecos import RateSnapshot, UnsoldHousingSnapshot
from backend.houstat import AffordabilitySnapshot
from backend.seoul_supply import REFERENCE_ANNUAL_UNITS, SupplySnapshot
from backend.kb_supply import KBSupplySnapshot, calculate_supply_score as calculate_kb_supply_score
from backend.liquidity import LiquiditySnapshot
from backend.subscription import SubscriptionSnapshot


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "snapshot.json"
WEIGHTS = {"pir": .25, "volume": .20, "subscription": .15, "rate": .15, "supply": .15}
PRICE_BURDEN_WEIGHTS = {"pir": .75, "rate": .25}
TRANSITION_WEIGHTS = {"volume": .55, "subscription": .45}
COMPOSITE_FIXTURE_SCORES = [
    57, 52, 53, 55, 56, 56, 60, 71, 72, 70, 72, 79,
    85, 89, 90, 91, 88, 84, 86, 82, 87, 88, 88, 88,
    86, 79, 64, 59, 58, 56, 52, 44, 45, 44, 44, 47,
    49, 45, 45, 35, 40, 34, 36, 41, 40, 42, 47, 52,
    52, 54, 50, 47, 48, 50, 49, 56, 56, 58, 50, 50,
    49, 54, 56, 62, 56, 57, 67, 71,
]
PRICE_FIXTURE_VALUES = [
    81.857, 83.169, 84.499, 85.625, 86.44, 87.311, 88.76, 89.898,
    91.33, 92.876, 93.848, 94.842, 95.279, 95.501, 95.589, 95.641,
    95.746, 95.949, 96.077, 96.111, 95.971, 95.785, 95.145, 93.798,
    92.454, 90.52, 89.436, 88.389, 87.532, 86.767, 86.52, 86.323,
    86.274, 86.503, 86.703, 86.736, 86.644, 86.477, 86.373, 86.245,
    86.102, 86.075, 86.182, 86.664, 87.436, 88.199, 88.64, 88.893,
    89.107, 89.164, 89.22, 89.797, 90.681, 91.236, 92.539, 93.727,
    94.285, 95.055, 96.441, 98.096, 99.138, 100, 101.336, 102.784,
    103.817, 104.68, 105.798, 106.913,
]


def load_fixture() -> dict:
    snapshot = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    expansion = next(
        (item for item in snapshot["indicators"] if item.get("id") == "unpopular"),
        None,
    )
    if expansion:
        phase_score, bonus, stage = expansion_signal(expansion)
        expansion["change"] = stage
        expansion["insight"] = (
            f"현재 단계는 ‘{stage}’이에요. 확산 파생점수는 {phase_score}점이며 "
            "검증 중인 실험 지표라 두 핵심 점수에는 반영하지 않아요."
        )
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    fixture_history = []
    for index, score in enumerate(COMPOSITE_FIXTURE_SCORES):
        absolute_month = 2020 * 12 + 11 + index
        fixture_history.append((
            f"{absolute_month // 12:04d}{absolute_month % 12 + 1:02d}", score,
        ))
    snapshot = with_composite_history(snapshot, fixture_history)
    snapshot = with_price_history(snapshot, [
        (period, PRICE_FIXTURE_VALUES[index])
        for index, (period, _) in enumerate(fixture_history)
    ])
    return with_dual_scores(snapshot)


def _weighted_indicator_score(indicators: list[dict], weights: dict[str, float]) -> int:
    scores = {item.get("id"): int(item["score"]) for item in indicators}
    missing = weights.keys() - scores.keys()
    if missing:
        raise ValueError(f"Missing dual-score indicators: {', '.join(sorted(missing))}")
    return round(sum(scores[key] * weight for key, weight in weights.items()))


def verdict_for(price_burden_score: int, transition_score: int) -> str:
    if price_burden_score >= 65 and transition_score >= 65:
        return "고점 경계"
    if price_burden_score >= 65:
        return "가격 부담 높음"
    if transition_score >= 65:
        return "수요 위축 관찰"
    return "안정 구간"


def with_dual_scores(
    snapshot: dict,
    price_burden_history: list[tuple[str, int]] | None = None,
    transition_history: list[tuple[str, int]] | None = None,
) -> dict:
    """Attach the two decision scores while preserving the legacy composite score."""
    result = copy.deepcopy(snapshot)
    indicators = result["indicators"]
    burden = _weighted_indicator_score(indicators, PRICE_BURDEN_WEIGHTS)
    transition = _weighted_indicator_score(indicators, TRANSITION_WEIGHTS)
    result["priceBurdenScore"] = burden
    result["transitionScore"] = transition
    result["verdict"] = verdict_for(burden, transition)

    # Fixtures have score-only indicator histories. Align their tails to the legacy
    # monthly labels without inventing a shared timeline for the two new series.
    if price_burden_history is None:
        price_burden_history = _fixture_dual_history(result, PRICE_BURDEN_WEIGHTS)
    if transition_history is None:
        transition_history = _fixture_dual_history(result, TRANSITION_WEIGHTS)
    result["priceBurdenHistory"] = [score for _, score in price_burden_history]
    result["priceBurdenHistoryLabels"] = [
        f"{period[:4]} {int(period[4:])}월" for period, _ in price_burden_history
    ]
    result["transitionHistory"] = [score for _, score in transition_history]
    result["transitionHistoryLabels"] = [
        f"{period[:4]} {int(period[4:])}월" for period, _ in transition_history
    ]
    return result


def _fixture_dual_history(snapshot: dict, weights: dict[str, float]) -> list[tuple[str, int]]:
    legacy_periods = [_month_key(label) for label in snapshot.get("historyLabels", [])]
    by_id = {item["id"]: item for item in snapshot["indicators"]}
    length = min(len(by_id[key].get("history", [])) for key in weights)
    if not legacy_periods or not length:
        return []
    periods = legacy_periods[-length:]
    series = {key: by_id[key]["history"][-length:] for key in weights}
    return [
        (period, round(sum(series[key][index] * weight for key, weight in weights.items())))
        for index, period in enumerate(periods)
    ]


def calculate_score(indicators: list[dict]) -> int:
    weighted = [(item["score"], WEIGHTS[item["id"]]) for item in indicators if item["id"] in WEIGHTS]
    total_weight = sum(weight for _, weight in weighted)
    if not total_weight:
        raise ValueError("No scoreable indicators")
    base_score = round(sum(score * weight for score, weight in weighted) / total_weight)
    expansion = next((item for item in indicators if item.get("id") == "unpopular"), None)
    bonus = expansion_signal(expansion)[1] if expansion else 0
    return min(100, round(base_score + bonus))


def expansion_signal(indicator: dict | None) -> tuple[int, float, str]:
    if not indicator:
        return 50, 0, "관찰 중"
    history = indicator.get("rawHistory") or indicator.get("history") or []
    if not history:
        return 50, 0, "관찰 중"
    raw = float(history[-1])
    trailing = [float(value) for value in history[-6:]]
    decline = max(trailing) - raw
    level = max(0, min(100, 50 + (raw - 50) * 2))
    rollover = max(0, min(100, 50 + decline * 8))
    phase_score = round(level * .60 + rollover * .40)
    bonus = max(0, phase_score - 50) * .05
    if decline >= 3 and max(trailing) >= 55:
        stage = "확산 둔화"
    elif raw >= 60:
        stage = "과열 확산"
    elif raw >= 50:
        stage = "확산 중"
    else:
        stage = "제한적 확산"
    return phase_score, bonus, stage


def with_composite_history(snapshot: dict, history: list[tuple[str, int]]) -> dict:
    result = copy.deepcopy(snapshot)
    result["history"] = [score for _, score in history]
    result["historyLabels"] = [
        f"{period[:4]} {int(period[4:])}월" for period, _ in history
    ]
    return result


def _month_key(label: str) -> str:
    year, month = label.replace("월", "").split()
    return f"{year}{int(month):02d}"


def merge_composite_history(snapshot: dict, history: list[tuple[str, int]]) -> dict:
    merged = {
        _month_key(label): score
        for label, score in zip(
            snapshot.get("historyLabels", []), snapshot.get("history", [])
        )
    }
    merged.update(dict(history))
    return with_composite_history(snapshot, sorted(merged.items()))


def with_price_history(snapshot: dict, history: list[tuple[str, float]]) -> dict:
    result = copy.deepcopy(snapshot)
    result["priceHistory"] = [value for _, value in history]
    result["priceHistoryLabels"] = [
        f"{period[:4]} {int(period[4:])}월" for period, _ in history
    ]
    result["priceHistoryUnit"] = "2026.01=100"
    return result


def level_for(score: int) -> str:
    if score < 25: return "stable"
    if score < 45: return "watch"
    if score < 65: return "caution"
    if score < 80: return "alert"
    return "highRisk"


def volume_score(current: int, previous: int) -> int:
    if previous <= 0:
        return 50
    decline = max(-0.5, min(0.5, (previous - current) / previous))
    return max(0, min(100, round(50 + decline * 100)))


def volume_score_from_history(
    monthly_history: list[tuple[str, int]],
) -> tuple[int, float, float, float]:
    """Score liquidity cooling using three-month and seasonal comparisons."""
    rows = sorted(monthly_history)
    if len(rows) < 6:
        current = rows[-1][1] if rows else 0
        previous = rows[-2][1] if len(rows) > 1 else current
        return volume_score(current, previous), 0, 0, 0

    values = dict(rows)
    recent_periods = [period for period, _ in rows[-3:]]
    recent_average = statistics.mean(values[period] for period in recent_periods)
    previous_average = statistics.mean(count for _, count in rows[-6:-3])

    def shift_year(period: str, years: int) -> str:
        return f"{int(period[:4]) + years:04d}{period[4:]}"

    def matching_average(years: int) -> float | None:
        periods = [shift_year(period, -years) for period in recent_periods]
        if not all(period in values for period in periods):
            return None
        return statistics.mean(values[period] for period in periods)

    year_ago_average = matching_average(1) or previous_average
    seasonal_averages = [
        average for years in range(1, 6)
        if (average := matching_average(years)) is not None
    ]
    seasonal_reference = (
        statistics.median(seasonal_averages) if seasonal_averages else year_ago_average
    )

    def risk(reference: float) -> float:
        if reference <= 0:
            return 50
        return max(0, min(100, 50 + (reference - recent_average) / reference * 100))

    previous_risk = risk(previous_average)
    year_ago_risk = risk(year_ago_average)
    seasonal_risk = risk(seasonal_reference)
    score = round(previous_risk * .20 + year_ago_risk * .50 + seasonal_risk * .30)

    def change(reference: float) -> float:
        return (recent_average / reference - 1) * 100 if reference else 0

    return (
        score,
        change(previous_average),
        change(year_ago_average),
        change(seasonal_reference),
    )


def with_live_volume(
    base: dict,
    current: int,
    previous: int,
    observed_at: str,
    monthly_history: list[tuple[str, int]] | None = None,
) -> dict:
    snapshot = copy.deepcopy(base)
    change = ((current - previous) / previous * 100) if previous else 0
    if monthly_history:
        score, change_3m, change_1y, change_seasonal = volume_score_from_history(monthly_history)
    else:
        score, change_3m, change_1y, change_seasonal = volume_score(current, previous), 0, 0, 0
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "volume")
    indicator.update({
        "score": score,
        "value": f"{current:,}건",
        "change": f"전월 {change:+.1f}%",
        "observedAt": observed_at,
        "source": "국토교통부 실거래가 · 잠정치",
        "trend": "up" if change_3m < -.5 else "down" if change_3m > .5 else "flat",
        "explanation": (
            "최근 3개월 거래량을 직전 3개월, 전년 같은 기간, "
            "과거 5년 같은 계절과 비교해 시장 유동성이 식는 정도를 봐요."
        ),
    })
    if monthly_history:
        indicator.update({
            "rawHistory": [count for _, count in monthly_history],
            "historyLabels": [f"{period[:4]} {int(period[4:])}월" for period, _ in monthly_history],
            "historyUnit": "건",
            "insight": (
                f"최근 3개월 거래량은 직전 3개월보다 {change_3m:+.1f}%, "
                f"전년 같은 기간보다 {change_1y:+.1f}% 변했어요. "
                f"과거 같은 계절과 비교하면 {change_seasonal:+.1f}%예요."
            ),
        })
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - base["score"]
    snapshot["deltaLabel"] = "거래량 반영"
    snapshot["confidence"] = 0.72
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = 1
    return snapshot


def with_live_rate(base: dict, rates: RateSnapshot) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "rate")
    change = rates.mortgage_change_3m
    mortgage_time = rates.mortgage_rate.time
    mortgage_rows = rates.mortgage_observations or [rates.mortgage_rate]
    base_rows = sorted(rates.base_observations or [rates.base_rate], key=lambda row: row.time)
    monthly_base: list[float] = []
    base_index = 0
    latest_base = base_rows[0].value
    for mortgage_row in mortgage_rows:
        month_end = f"{mortgage_row.time[:6]}31"
        while base_index < len(base_rows) and base_rows[base_index].time <= month_end:
            latest_base = base_rows[base_index].value
            base_index += 1
        monthly_base.append(latest_base)
    labels = [
        f"{row.time[:4]} {int(row.time[4:6])}월" for row in mortgage_rows
    ]
    indicator.update({
        "score": rates.score,
        "value": f"{rates.mortgage_rate.value:.2f}%",
        "change": f"3개월 {change:+.2f}%p",
        "trend": "up" if change > .005 else "down" if change < -.005 else "flat",
        "observedAt": f"{mortgage_time[:4]}년 {int(mortgage_time[4:])}월",
        "source": "한국은행 ECOS · 신규취급액",
        "insight": (
            f"{mortgage_time[:4]}년 {int(mortgage_time[4:])}월 주택담보대출 금리는 "
            f"{rates.mortgage_rate.value:.2f}%, 당시 기준금리는 {monthly_base[-1]:.2f}%예요. "
            f"현재 기준금리는 {rates.base_rate.value:.2f}%예요."
        ),
        "history": rates.history_scores,
        "rawHistory": [row.value for row in mortgage_rows],
        "historyLabels": labels,
        "historyUnit": "%",
        "secondaryTitle": "한국은행 기준금리",
        "secondaryRawHistory": monthly_base,
        "secondaryHistoryLabels": labels,
        "secondaryHistoryUnit": "%",
    })
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = "거래량·금리 반영"
    snapshot["confidence"] = 0.78
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = 2
    return snapshot


def with_live_unsold(base: dict, unsold: UnsoldHousingSnapshot) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "subscription")
    change = unsold.change_3m_percent
    observed = unsold.latest.time
    indicator.update({
        "title": "서울 미분양 주택",
        "shortTitle": "미분양",
        "score": unsold.score,
        "value": f"{int(unsold.latest.value):,}호",
        "change": f"3개월 {change:+.1f}%",
        "trend": "up" if change > .05 else "down" if change < -.05 else "flat",
        "observedAt": f"{observed[:4]}년 {int(observed[4:])}월",
        "source": "한국은행 ECOS · 국토교통부",
        "explanation": "미분양 주택이 장기 평균보다 많거나 빠르게 증가하면 청약과 신규 주택 수요가 약해진 신호일 수 있어요.",
        "insight": f"서울 미분양은 {int(unsold.latest.value):,}호이며 최근 3개월 {change:+.1f}% 변했어요.",
        "history": unsold.history_scores,
        "rawHistory": [row.value for row in unsold.observations],
        "historyLabels": [f"{row.time[:4]} {int(row.time[4:])}월" for row in unsold.observations],
        "historyUnit": "호",
    })
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = "3개 지표 반영"
    snapshot["summary"] = "거래량 감소와 금리 부담에 더해\n미분양 수준도 높게 나타났어요."
    snapshot["confidence"] = 0.82
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = 3
    return snapshot


def with_live_subscription(
    base: dict,
    subscription: SubscriptionSnapshot,
    unsold: UnsoldHousingSnapshot,
) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "subscription")
    observed = subscription.latest_time
    change = subscription.change_1y_percent
    unsold_change = unsold.change_3m_percent
    indicator.update({
        "title": "서울 청약 수요",
        "shortTitle": "청약 수요",
        "score": subscription.score,
        "value": f"{subscription.latest_rate:.1f} : 1",
        "change": f"전년 대비 {change:+.1f}%",
        "trend": "up" if change < -1 else "down" if change > 1 else "flat",
        "observedAt": f"{observed[:4]}년 {int(observed[4:])}월",
        "source": "한국부동산원 청약홈 · 일반공급",
        "explanation": (
            "최근 3개월 일반공급 접수건수를 공급세대수로 나눈 값이에요. "
            "경쟁률이 빠르게 낮아지면 새 아파트에 대한 미래 수요가 식는 신호일 수 있어요."
        ),
        "insight": (
            f"최근 3개월 공급 {subscription.latest_supply_3m:,}세대의 가중 경쟁률은 "
            f"{subscription.latest_rate:.1f}대 1이며 전년보다 {abs(change):.1f}% "
            f"{'낮아졌어요' if change < 0 else '높아졌어요'}."
        ),
        "history": subscription.history_scores,
        "rawHistory": subscription.history_rates,
        "historyLabels": [
            f"{month[:4]} {int(month[4:])}월" for month in subscription.history_months
        ],
        "historyUnit": ": 1",
        "secondaryTitle": "서울 미분양 주택",
        "secondaryValue": f"{int(unsold.latest.value):,}호",
        "secondaryChange": f"3개월 {unsold_change:+.1f}%",
        "secondaryInsight": (
            f"수요 냉각 이후 실제로 남은 주택은 {int(unsold.latest.value):,}호예요. "
            "미분양은 고점을 예측하기보다 시장 약화를 확인하는 보조 신호로 봐요."
        ),
        "secondaryRawHistory": [row.value for row in unsold.observations],
        "secondaryHistoryLabels": [
            f"{row.time[:4]} {int(row.time[4:])}월" for row in unsold.observations
        ],
        "secondaryHistoryUnit": "호",
        "secondarySource": "한국은행 ECOS · 국토교통부",
        "secondaryObservedAt": f"{unsold.latest.time[:4]}년 {int(unsold.latest.time[4:])}월",
    })
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = "청약 수요 반영"
    snapshot["summary"] = "주택 구입 부담과 금리는 높고\n청약 수요도 약해진 상태예요."
    snapshot["confidence"] = 0.84
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = 3
    return snapshot


def with_live_affordability(base: dict, affordability: AffordabilitySnapshot) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "pir")
    change = affordability.change_1y
    observed = affordability.latest.time
    indicator.update({
        "title": "서울 주택구입부담",
        "shortTitle": "구입부담",
        "score": affordability.score,
        "value": f"{affordability.latest.value:.1f}",
        "change": f"1년 {change:+.1f}p",
        "trend": "up" if change > .05 else "down" if change < -.05 else "flat",
        "observedAt": f"{observed[:4]}년 {int(observed[4:])}분기",
        "source": "한국주택금융공사 HOUSTAT · 분기",
        "explanation": "K-HAI는 중위소득 가구가 표준대출로 중위가격 주택을 살 때의 원리금 상환 부담을 보여줘요. 100을 넘으면 부담이 큰 구간이에요.",
        "insight": f"서울 주택구입부담지수는 {affordability.latest.value:.1f}이며 1년 전보다 {change:+.1f}p 변했어요.",
        "history": affordability.history_scores,
        "rawHistory": [row.value for row in affordability.observations],
        "historyLabels": [f"{row.time[:4]} {int(row.time[4:])}Q" for row in affordability.observations],
        "historyUnit": "K-HAI",
        "historyReferenceValue": 100,
        "historyReferenceLabel": "부담 기준 100",
    })
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = "4개 지표 반영"
    snapshot["summary"] = "주택 구입 부담과 금리 수준이 높고\n거래량도 감소한 상태예요."
    snapshot["confidence"] = 0.86
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = 4
    return snapshot


def with_live_supply(base: dict, supply: SupplySnapshot) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "supply")
    annual_average = supply.total_units / 2
    reference_change = (annual_average / REFERENCE_ANNUAL_UNITS - 1) * 100
    indicator.update({
        "score": supply.score,
        "value": f"{supply.total_units / 10_000:.1f}만호",
        "change": f"연평균 {reference_change:+.1f}%",
        "trend": "up" if reference_change > 2 else "down" if reference_change < -2 else "flat",
        "observedAt": f"{supply.first_year}~{supply.second_year}년",
        "source": "서울주택 정보마당 · 입주예정",
        "explanation": "서울시가 정비사업과 비정비사업을 합산한 당해연도 포함 2년간 아파트 입주예정물량이에요.",
        "insight": (
            f"2년 합계 {supply.total_units:,}호로, 연평균은 {annual_average:,.0f}호예요. "
            f"최근 공식 연평균보다 {abs(reference_change):.1f}% {'적어요' if reference_change < 0 else '많아요'}."
        ),
        "history": supply.history_scores,
        "rawHistory": [supply.first_year_units, supply.second_year_units],
        "historyLabels": [str(supply.first_year), str(supply.second_year)],
        "historyUnit": "호",
        "historyReferenceValue": REFERENCE_ANNUAL_UNITS,
        "historyReferenceLabel": f"최근 연평균 {REFERENCE_ANNUAL_UNITS / 10_000:.1f}만호",
    })
    live_count = int(snapshot.get("liveIndicatorCount", 0)) + 1
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = f"{live_count}개 지표 반영"
    snapshot["summary"] = "주택 구입 부담과 금리는 높지만\n향후 입주 물량은 적은 편이에요."
    snapshot["confidence"] = min(.92, float(snapshot.get("confidence", .70)) + .04)
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "partialLive"
    snapshot["liveIndicatorCount"] = live_count
    return snapshot


def with_live_kb_supply(
    base: dict,
    supply: KBSupplySnapshot,
    seoul_supply: SupplySnapshot | None = None,
) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "supply")
    forecast = [
        row for row in supply.move_in
        if supply.forecast_start_year <= row.year <= supply.forecast_start_year + 1
    ]
    forecast_total = sum(row.units for row in forecast)
    reference_change = (supply.forecast_average_units / supply.reference_annual_units - 1) * 100
    comparison = ""
    if seoul_supply is not None:
        comparison = (
            f" 서울시 공식 2년 전망은 {seoul_supply.total_units:,}호로 "
            "집계 범위에 따라 차이가 있어요."
        )
    indicator.update({
        "score": supply.score,
        "value": f"{forecast_total / 10_000:.1f}만호",
        "change": f"10년 평균 {reference_change:+.1f}%",
        "trend": "up" if reference_change > 2 else "down" if reference_change < -2 else "flat",
        "observedAt": f"{supply.forecast_start_year}~{supply.forecast_start_year + 1}년",
        "source": "KB부동산 데이터허브·프롭티어 · 입주물량",
        "explanation": "서울 아파트의 과거 입주 실적과 향후 입주 예정물량을 같은 기준으로 비교해요.",
        "insight": (
            f"향후 2년 합계 {forecast_total:,}호, 연평균 {supply.forecast_average_units:,.0f}호로 "
            f"직전 10년 평균 {supply.reference_annual_units:,.0f}호보다 {abs(reference_change):.1f}% "
            f"{'적어요' if reference_change < 0 else '많아요'}.{comparison}"
        ),
        "history": [
            calculate_kb_supply_score(row.units, supply.reference_annual_units)
            for row in supply.move_in[-8:]
        ],
        "rawHistory": [row.units for row in supply.move_in],
        "historyLabels": [str(row.year) for row in supply.move_in],
        "historyUnit": "호",
        "historyReferenceValue": supply.reference_annual_units,
        "historyReferenceLabel": f"직전 10년 평균 {supply.reference_annual_units / 10_000:.1f}만호",
        "historyForecastStartLabel": str(supply.forecast_start_year),
        "secondaryTitle": "서울 아파트 분양물량",
        "secondaryRawHistory": [row.units for row in supply.pre_sale],
        "secondaryHistoryLabels": [str(row.year) for row in supply.pre_sale],
        "secondaryHistoryUnit": "호",
        "secondarySource": "KB부동산 데이터허브·프롭티어 · 분양물량",
    })
    live_count = int(snapshot.get("liveIndicatorCount", 0)) + 1
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = f"{live_count}개 지표 반영"
    snapshot["confidence"] = min(.92, float(snapshot.get("confidence", .70)) + .04)
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "live" if live_count == 6 else "partialLive"
    snapshot["liveIndicatorCount"] = live_count
    return snapshot


def with_live_liquidity(base: dict, liquidity: LiquiditySnapshot) -> dict:
    snapshot = copy.deepcopy(base)
    indicator = next(item for item in snapshot["indicators"] if item["id"] == "unpopular")
    change = liquidity.recent_share_percent - liquidity.baseline_share_percent
    existing_history = {
        _month_key(label): score
        for label, score in zip(
            indicator.get("historyLabels", []),
            indicator.get("rawHistory") or indicator.get("history", []),
        )
    }
    existing_history.update(zip(liquidity.history_months, liquidity.history_scores))
    merged_history = sorted(existing_history.items())
    indicator.update({
        "title": "비인기 거래 확산도 Beta",
        "shortTitle": "확산도 Beta",
        "score": liquidity.score,
        "value": f"{liquidity.recent_share_percent:.1f}%",
        "change": f"평소 대비 {change:+.1f}%p",
        "trend": "up" if change > .2 else "down" if change < -.2 else "flat",
        "observedAt": liquidity.observed_at,
        "source": "국토교통부 실거래가 · 자체 분석 Beta",
        "explanation": "최근 21개월 동안 거래 빈도가 하위 20%인 단지·면적군까지 매수세가 확산되는지 확인해요.",
        "insight": (
            f"최근 3개월 저유동성 거래 비중은 {liquidity.recent_share_percent:.1f}%이며, "
            f"그중 {liquidity.record_high_share_percent:.1f}%가 이전 21개월 최고가 이상이에요. "
            "백테스트 검증 전까지 종합 고점점수에는 반영하지 않아요."
        ),
        "history": [score for _, score in merged_history],
        "rawHistory": [score for _, score in merged_history],
        "historyLabels": [
            f"{month[:4]} {int(month[4:])}월" for month, _ in merged_history
        ],
        "historyUnit": "확산지수",
    })
    phase_score, bonus, stage = expansion_signal(indicator)
    indicator["change"] = stage
    indicator["insight"] = (
        f"현재 단계는 ‘{stage}’이에요. 최근 3개월 저유동성 거래 비중은 "
        f"{liquidity.recent_share_percent:.1f}%이고, 확산 파생점수는 {phase_score}점이에요. "
        "검증 중인 실험 지표라 두 핵심 점수에는 반영하지 않아요."
    )
    live_count = int(snapshot.get("liveIndicatorCount", 0)) + 1
    snapshot["score"] = calculate_score(snapshot["indicators"])
    snapshot["level"] = level_for(snapshot["score"])
    snapshot["delta7d"] = snapshot["score"] - load_fixture()["score"]
    snapshot["deltaLabel"] = f"{live_count}개 지표 반영"
    snapshot["summary"] = "여섯 지표의 공식·실거래 데이터를 바탕으로\n서울 시장의 고점 신호를 계산했어요."
    snapshot["confidence"] = min(.95, float(snapshot.get("confidence", .70)) + .03)
    snapshot["asOf"] = dt.date.today().strftime("%Y.%m.%d")
    snapshot["dataMode"] = "live" if live_count == 6 else "partialLive"
    snapshot["liveIndicatorCount"] = live_count
    return snapshot
