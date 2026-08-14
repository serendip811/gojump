from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.houstat import HoustatObservation
from backend.ecos import EcosObservation
from backend.trade_store import DEFAULT_DB_PATH
from backend.subscription import SubscriptionObservation
from backend.kb_supply import SupplyObservation


class MacroStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS khai_observations (
                period TEXT PRIMARY KEY,
                value REAL NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS unsold_observations (
                period TEXT PRIMARY KEY,
                value REAL NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS subscription_observations (
                period TEXT PRIMARY KEY,
                general_supply INTEGER NOT NULL,
                general_applications INTEGER NOT NULL,
                special_supply INTEGER NOT NULL,
                special_applications INTEGER NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS mortgage_rate_observations (
                period TEXT PRIMARY KEY,
                value REAL NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS base_rate_observations (
                period TEXT PRIMARY KEY,
                value REAL NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for table in ("kb_move_in_observations", "kb_pre_sale_observations"):
            self.connection.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    period TEXT PRIMARY KEY,
                    value INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS composite_score_observations (
                period TEXT PRIMARY KEY,
                score INTEGER NOT NULL,
                calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS dual_score_observations (
                period TEXT PRIMARY KEY,
                price_burden_score INTEGER,
                transition_score INTEGER,
                calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS seoul_apartment_price_observations (
                period TEXT PRIMARY KEY,
                value REAL NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.connection.commit()

    def upsert_khai(self, observations: list[HoustatObservation]) -> None:
        self.connection.executemany("""
            INSERT INTO khai_observations(period, value) VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                value=excluded.value, fetched_at=CURRENT_TIMESTAMP
        """, [(row.time, row.value) for row in observations])
        self.connection.commit()

    def khai_series(self) -> list[HoustatObservation]:
        rows = self.connection.execute(
            "SELECT period, value FROM khai_observations ORDER BY period"
        ).fetchall()
        return [HoustatObservation(time=row[0], value=float(row[1])) for row in rows]

    def upsert_unsold(self, observations: list[EcosObservation]) -> None:
        self.connection.executemany("""
            INSERT INTO unsold_observations(period, value) VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                value=excluded.value, fetched_at=CURRENT_TIMESTAMP
        """, [(row.time, row.value) for row in observations])
        self.connection.commit()

    def unsold_series(self) -> list[tuple[str, float]]:
        rows = self.connection.execute(
            "SELECT period, value FROM unsold_observations ORDER BY period"
        ).fetchall()
        return [(str(row[0]), float(row[1])) for row in rows]

    def upsert_subscription(self, observations: list[SubscriptionObservation]) -> None:
        self.connection.executemany("""
            INSERT INTO subscription_observations(
                period, general_supply, general_applications,
                special_supply, special_applications
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(period) DO UPDATE SET
                general_supply=excluded.general_supply,
                general_applications=excluded.general_applications,
                special_supply=excluded.special_supply,
                special_applications=excluded.special_applications,
                fetched_at=CURRENT_TIMESTAMP
        """, [
            (
                row.time, row.general_supply, row.general_applications,
                row.special_supply, row.special_applications,
            )
            for row in observations
        ])
        self.connection.commit()

    def subscription_series(self) -> list[SubscriptionObservation]:
        rows = self.connection.execute("""
            SELECT period, general_supply, general_applications,
                   special_supply, special_applications
            FROM subscription_observations ORDER BY period
        """).fetchall()
        return [SubscriptionObservation(*row) for row in rows]

    def upsert_rates(
        self,
        mortgage: list[EcosObservation],
        base: list[EcosObservation],
    ) -> None:
        for table, observations in (
            ("mortgage_rate_observations", mortgage),
            ("base_rate_observations", base),
        ):
            self.connection.executemany(f"""
                INSERT INTO {table}(period, value) VALUES (?, ?)
                ON CONFLICT(period) DO UPDATE SET
                    value=excluded.value, fetched_at=CURRENT_TIMESTAMP
            """, [(row.time, row.value) for row in observations])
        self.connection.commit()

    def rate_series(self, table: str) -> list[tuple[str, float]]:
        if table not in {"mortgage_rate_observations", "base_rate_observations"}:
            raise ValueError("Unknown rate table")
        rows = self.connection.execute(
            f"SELECT period, value FROM {table} ORDER BY period"
        ).fetchall()
        return [(str(period), float(value)) for period, value in rows]

    def upsert_kb_supply(
        self,
        move_in: list[SupplyObservation],
        pre_sale: list[SupplyObservation],
    ) -> None:
        for table, observations in (
            ("kb_move_in_observations", move_in),
            ("kb_pre_sale_observations", pre_sale),
        ):
            self.connection.executemany(f"""
                INSERT INTO {table}(period, value) VALUES (?, ?)
                ON CONFLICT(period) DO UPDATE SET
                    value=excluded.value, fetched_at=CURRENT_TIMESTAMP
            """, [(str(row.year), row.units) for row in observations])
        self.connection.commit()

    def kb_supply_series(self, table: str) -> list[SupplyObservation]:
        if table not in {"kb_move_in_observations", "kb_pre_sale_observations"}:
            raise ValueError("Unknown KB supply table")
        rows = self.connection.execute(
            f"SELECT period, value FROM {table} ORDER BY period"
        ).fetchall()
        return [SupplyObservation(int(period), int(value)) for period, value in rows]

    def upsert_composite_scores(self, observations: list[tuple[str, int]]) -> None:
        self.connection.executemany("""
            INSERT INTO composite_score_observations(period, score) VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                score=excluded.score, calculated_at=CURRENT_TIMESTAMP
        """, observations)
        self.connection.commit()

    def composite_scores(self, limit: int = 12) -> list[tuple[str, int]]:
        rows = self.connection.execute("""
            SELECT period, score FROM composite_score_observations
            ORDER BY period DESC LIMIT ?
        """, (limit,)).fetchall()
        return [(str(period), int(score)) for period, score in reversed(rows)]

    def upsert_price_burden_scores(self, observations: list[tuple[str, int]]) -> None:
        self.connection.executemany("""
            INSERT INTO dual_score_observations(period, price_burden_score)
            VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                price_burden_score=excluded.price_burden_score,
                calculated_at=CURRENT_TIMESTAMP
        """, observations)
        self.connection.commit()

    def upsert_transition_scores(self, observations: list[tuple[str, int]]) -> None:
        self.connection.executemany("""
            INSERT INTO dual_score_observations(period, transition_score)
            VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                transition_score=excluded.transition_score,
                calculated_at=CURRENT_TIMESTAMP
        """, observations)
        self.connection.commit()

    def dual_scores(
        self,
        column: str,
        limit: int = 240,
    ) -> list[tuple[str, int]]:
        if column not in {"price_burden_score", "transition_score"}:
            raise ValueError("Unknown dual score column")
        rows = self.connection.execute(f"""
            SELECT period, {column} FROM dual_score_observations
            WHERE {column} IS NOT NULL
            ORDER BY period DESC LIMIT ?
        """, (limit,)).fetchall()
        return [(str(period), int(score)) for period, score in reversed(rows)]

    def upsert_seoul_apartment_prices(self, observations: list[EcosObservation]) -> None:
        self.connection.executemany("""
            INSERT INTO seoul_apartment_price_observations(period, value) VALUES (?, ?)
            ON CONFLICT(period) DO UPDATE SET
                value=excluded.value, fetched_at=CURRENT_TIMESTAMP
        """, [(row.time, row.value) for row in observations])
        self.connection.commit()

    def seoul_apartment_prices(self, limit: int = 240) -> list[tuple[str, float]]:
        rows = self.connection.execute("""
            SELECT period, value FROM seoul_apartment_price_observations
            ORDER BY period DESC LIMIT ?
        """, (limit,)).fetchall()
        return [(str(period), float(value)) for period, value in reversed(rows)]
