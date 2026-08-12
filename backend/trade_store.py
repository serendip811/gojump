from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from backend.collector import Trade


DEFAULT_DB_PATH = Path(__file__).parent / "data" / "gojump.sqlite3"


class TradeStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_key TEXT PRIMARY KEY,
                district_code TEXT NOT NULL,
                deal_date TEXT NOT NULL,
                year_month TEXT NOT NULL,
                amount_10k_krw INTEGER NOT NULL,
                apartment TEXT NOT NULL,
                legal_dong TEXT NOT NULL,
                land_lot TEXT NOT NULL,
                area_sqm REAL NOT NULL,
                area_bucket INTEGER NOT NULL,
                floor INTEGER NOT NULL,
                built_year INTEGER,
                apartment_sequence TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trades_month ON trades(year_month);
            CREATE INDEX IF NOT EXISTS idx_trades_group
                ON trades(district_code, apartment_sequence, legal_dong, apartment, area_bucket);
            CREATE TABLE IF NOT EXISTS collected_months (
                district_code TEXT NOT NULL,
                year_month TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (district_code, year_month)
            );
            CREATE TABLE IF NOT EXISTS liquidity_score_observations (
                period TEXT PRIMARY KEY,
                score INTEGER NOT NULL,
                calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.connection.commit()

    @staticmethod
    def _key(trade: Trade, occurrence: int) -> str:
        raw = "|".join(str(value) for value in (
            trade.district_code, trade.deal_year, trade.deal_month, trade.deal_day,
            trade.apartment_sequence, trade.legal_dong, trade.apartment,
                trade.land_lot, trade.area_sqm, trade.floor, trade.amount_10k_krw, occurrence,
        ))
        return hashlib.sha256(raw.encode()).hexdigest()

    def replace_district_month(self, district_code: str, year_month: str, trades: list[Trade]) -> None:
        self.connection.execute(
            "DELETE FROM trades WHERE district_code = ? AND year_month = ?",
            (district_code, year_month),
        )
        occurrences: dict[tuple, int] = {}
        rows = []
        for trade in trades:
            identity = (
                trade.deal_day, trade.apartment_sequence, trade.legal_dong, trade.apartment,
                trade.area_sqm, trade.floor, trade.amount_10k_krw,
            )
            occurrence = occurrences.get(identity, 0)
            occurrences[identity] = occurrence + 1
            rows.append((
                self._key(trade, occurrence), trade.district_code,
                f"{trade.deal_year:04d}-{trade.deal_month:02d}-{trade.deal_day:02d}",
                year_month, trade.amount_10k_krw, trade.apartment, trade.legal_dong,
                trade.land_lot, trade.area_sqm, round(trade.area_sqm / 10) * 10, trade.floor,
                trade.built_year, trade.apartment_sequence,
            ))
        self.connection.executemany("""
            INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        self.connection.execute("""
            INSERT INTO collected_months(district_code, year_month, trade_count)
            VALUES (?, ?, ?)
            ON CONFLICT(district_code, year_month) DO UPDATE SET
                trade_count=excluded.trade_count, collected_at=CURRENT_TIMESTAMP
        """, (district_code, year_month, len(trades)))
        self.connection.commit()

    def is_collected(self, district_code: str, year_month: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM collected_months WHERE district_code=? AND year_month=?",
            (district_code, year_month),
        ).fetchone()
        return row is not None

    def month_count(self, year_month: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM trades WHERE year_month=?", (year_month,)
        ).fetchone()
        return int(row["count"])

    def monthly_counts(self, limit: int = 24) -> list[tuple[str, int]]:
        rows = self.connection.execute("""
            SELECT year_month, COUNT(*) AS count
            FROM trades
            GROUP BY year_month
            ORDER BY year_month DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [(str(row["year_month"]), int(row["count"])) for row in reversed(rows)]

    def is_seoul_month_complete(self, year_month: str, district_count: int = 25) -> bool:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM collected_months WHERE year_month=?",
            (year_month,),
        ).fetchone()
        return int(row["count"]) == district_count

    def coverage(self, start_month: str, end_month: str) -> tuple[int, int]:
        row = self.connection.execute("""
            SELECT COUNT(DISTINCT year_month) AS months, COUNT(*) AS districts
            FROM collected_months WHERE year_month BETWEEN ? AND ?
        """, (start_month, end_month)).fetchone()
        return int(row["months"]), int(row["districts"])

    def trades_between(self, start_month: str, end_month: str) -> list[sqlite3.Row]:
        return self.connection.execute("""
            SELECT * FROM trades
            WHERE year_month BETWEEN ? AND ?
            ORDER BY deal_date, trade_key
        """, (start_month, end_month)).fetchall()

    def upsert_liquidity_score(self, period: str, score: int) -> None:
        self.connection.execute("""
            INSERT INTO liquidity_score_observations(period, score) VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                score=excluded.score, calculated_at=CURRENT_TIMESTAMP
        """, (period, score))
        self.connection.commit()

    def liquidity_scores(self, end_month: str, limit: int = 240) -> list[tuple[str, int]]:
        rows = self.connection.execute("""
            SELECT period, score FROM liquidity_score_observations
            WHERE period <= ? ORDER BY period DESC LIMIT ?
        """, (end_month, limit)).fetchall()
        return [(str(row["period"]), int(row["score"])) for row in reversed(rows)]
