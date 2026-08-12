from __future__ import annotations

import dataclasses
import datetime as dt
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable


SEOUL_DISTRICTS = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}

BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"


@dataclasses.dataclass(frozen=True)
class Trade:
    district_code: str
    deal_year: int
    deal_month: int
    deal_day: int
    amount_10k_krw: int
    apartment: str
    legal_dong: str
    land_lot: str
    area_sqm: float
    floor: int
    built_year: int | None
    apartment_sequence: str
    cancelled: bool


def _text(item: ET.Element, *names: str) -> str:
    for name in names:
        node = item.find(name)
        if node is not None and node.text:
            return node.text.strip()
    return ""


def parse_trade_xml(payload: bytes, district_code: str) -> tuple[list[Trade], int]:
    root = ET.fromstring(payload)
    result_code = root.findtext(".//resultCode", default="00").strip()
    if result_code not in {"00", "000"}:
        message = root.findtext(".//resultMsg", default="Unknown public API error")
        raise RuntimeError(f"MOLIT API {result_code}: {message}")

    total_count = int(root.findtext(".//totalCount", default="0") or 0)
    trades: list[Trade] = []
    for item in root.findall(".//item"):
        amount = _text(item, "dealAmount", "거래금액").replace(",", "")
        if not amount:
            continue
        cancel_day = _text(item, "cdealDay", "해제사유발생일")
        trades.append(Trade(
            district_code=district_code,
            deal_year=int(_text(item, "dealYear", "년")),
            deal_month=int(_text(item, "dealMonth", "월")),
            deal_day=int(_text(item, "dealDay", "일")),
            amount_10k_krw=int(amount),
            apartment=_text(item, "aptNm", "아파트"),
            legal_dong=_text(item, "umdNm", "법정동"),
            land_lot=_text(item, "jibun", "지번"),
            area_sqm=float(_text(item, "excluUseAr", "전용면적") or 0),
            floor=int(_text(item, "floor", "층") or 0),
            built_year=int(value) if (value := _text(item, "buildYear", "건축년도")) else None,
            apartment_sequence=_text(item, "aptSeq", "단지일련번호"),
            cancelled=bool(cancel_day),
        ))
    return trades, total_count


class MolitTradeClient:
    def __init__(
        self,
        service_key: str,
        transport: Callable[[str], bytes] | None = None,
        page_size: int = 1_000,
    ) -> None:
        self.service_key = service_key
        self.transport = transport or self._download
        self.page_size = page_size

    @staticmethod
    def _download(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "GoJump/0.1"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 4:
                    raise
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(8, 2 ** attempt)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
                time.sleep(min(8, 2 ** attempt))
        raise RuntimeError("MOLIT request retry exhausted")

    def _url(self, district_code: str, year_month: str, page: int) -> str:
        params = urllib.parse.urlencode({
            "serviceKey": self.service_key,
            "LAWD_CD": district_code,
            "DEAL_YMD": year_month,
            "pageNo": page,
            "numOfRows": self.page_size,
        }, safe="%")
        return f"{BASE_URL}?{params}"

    def fetch_month(self, district_code: str, year_month: str) -> list[Trade]:
        all_trades: list[Trade] = []
        page = 1
        while True:
            payload = self.transport(self._url(district_code, year_month, page))
            trades, total_count = parse_trade_xml(payload, district_code)
            all_trades.extend(trades)
            if len(all_trades) >= total_count or not trades:
                break
            page += 1
        return [trade for trade in all_trades if not trade.cancelled]

    def fetch_seoul_month(self, year_month: str) -> list[Trade]:
        trades: list[Trade] = []
        for district_code in SEOUL_DISTRICTS:
            trades.extend(self.fetch_month(district_code, year_month))
        return trades


def previous_month(year_month: str) -> str:
    return shift_month(year_month, -1)


def shift_month(year_month: str, offset: int) -> str:
    year, month = int(year_month[:4]), int(year_month[4:])
    absolute = year * 12 + month - 1 + offset
    return f"{absolute // 12:04d}{absolute % 12 + 1:02d}"
