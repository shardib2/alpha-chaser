"""Load and validate the arena configuration."""

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "arena_config.json"


@dataclass
class Competitor:
    id: str
    display: str
    model: str
    strategy: str


@dataclass
class ArenaConfig:
    starting_cash: float
    benchmark: str
    universe: list[str]
    competitors: list[Competitor]
    max_orders_per_cycle: int = 8
    max_position_pct: float = 0.35
    extras: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "ArenaConfig":
        raw = json.loads(Path(path).read_text())
        competitors = [Competitor(**c) for c in raw.pop("competitors")]
        ids = [c.id for c in competitors]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate competitor ids in config: {ids}")
        known = {"starting_cash", "benchmark", "universe", "max_orders_per_cycle", "max_position_pct"}
        kwargs = {k: raw[k] for k in known if k in raw}
        extras = {k: v for k, v in raw.items() if k not in known}
        return cls(competitors=competitors, extras=extras, **kwargs)
