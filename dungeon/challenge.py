"""副本挑战与星级系统。

按副本类型区分星级条件，多维度综合评价，难度影响门槛，
奖励按星级阶梯发放，每日/每周次数限制（超出消耗门票），
保存历史最佳记录，组队副本按团队表现评星。
纯标准库实现。
"""
from dataclasses import dataclass, field
from datetime import date


DAILY_FREE_LIMIT = 3
WEEKLY_FREE_LIMIT = 12

# 难度严格系数：越高，星级条件越严格（时间更短、容错更少）
DIFFICULTY_MULTIPLIER = {
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.5,
    "nightmare": 2.0,
}

# 星级基础奖励（普通难度），高星级阶梯式递增，满星有额外奖励
BASE_REWARD = {
    1: {"gold": 100, "exp": 50},
    2: {"gold": 200, "exp": 120},
    3: {"gold": 350, "exp": 240, "gem": 10},  # 满星额外宝石
}


@dataclass
class StarThresholds:
    """1/2/3 星各维度的上限门槛（含）。"""
    time: tuple
    deaths: tuple
    hits: tuple
    requires_objective: bool = False


# 副本类型 -> (普通难度下 1/2/3 星的门槛)
# timed:     竞速型，时间要求最严
# survival:  生存型，看死亡次数
# flawless:  无伤型，看被击数
# objective: 目标型，必须完成特殊目标才能满星
DUNGEON_TYPES = {
    "timed": StarThresholds(
        time=(300, 210, 150), deaths=(3, 1, 0), hits=(40, 20, 10)
    ),
    "survival": StarThresholds(
        time=(420, 300, 210), deaths=(5, 2, 0), hits=(50, 30, 15)
    ),
    "flawless": StarThresholds(
        time=(360, 270, 200), deaths=(3, 1, 0), hits=(25, 10, 0)
    ),
    "objective": StarThresholds(
        time=(420, 300, 240), deaths=(3, 1, 0), hits=(40, 20, 10),
        requires_objective=True,
    ),
}

# 已知副本登记，未登记的副本按名称稳定映射到类型
DUNGEON_REGISTRY = {
    "dungeon_a": "timed",
    "dungeon_b": "survival",
    "dungeon_c": "flawless",
    "dungeon_d": "objective",
}

_CONDITION_LABELS = {
    "time": "clear_time",
    "deaths": "death_count",
    "hits": "hits_taken",
    "objective": "special_objective",
}


@dataclass
class RunRecord:
    rid: str
    dungeon: str
    difficulty: str
    time_seconds: float
    deaths: int
    hits_taken: int
    stars: int = 0
    objective_completed: bool = False
    is_team: bool = False
    team_size: int = 1


class ChallengeSystem:
    def __init__(self):
        self.records: list[RunRecord] = []
        self.daily_runs: dict[str, int] = {}
        self.weekly_runs: dict[str, int] = {}
        self.tickets: dict[str, int] = {}
        self.best_records: dict[str, RunRecord] = {}
        self.history: dict[str, list[RunRecord]] = {}
        self.team_deaths: dict[str, int] = {}
        self._daily_key: str | None = self.current_day_key()
        self._weekly_key: str | None = self.current_week_key()

    # ---------- 副本类型与星级条件（bug1） ----------

    def get_dungeon_type(self, dungeon: str) -> str:
        if dungeon in DUNGEON_REGISTRY:
            return DUNGEON_REGISTRY[dungeon]
        type_names = list(DUNGEON_TYPES)
        return type_names[self._stable_index(dungeon) % len(type_names)]

    @staticmethod
    def _stable_index(text: str) -> int:
        total = 0
        for ch in text:
            total = (total * 31 + ord(ch)) & 0xFFFFFFFF
        return total

    def get_thresholds(self, dungeon: str, difficulty: str = "normal") -> StarThresholds:
        base = DUNGEON_TYPES[self.get_dungeon_type(dungeon)]
        mult = self.get_difficulty_multiplier(difficulty)

        def scale_time(values):
            return tuple(round(value / mult) for value in values)

        def scale_count(values):
            scaled = []
            for value in values:
                if value == 0:
                    scaled.append(0)
                else:
                    scaled.append(max(0, round(value / mult)))
            return tuple(scaled)

        return StarThresholds(
            time=scale_time(base.time),
            deaths=scale_count(base.deaths),
            hits=scale_count(base.hits),
            requires_objective=base.requires_objective,
        )

    def get_star_conditions(self, dungeon: str, difficulty: str = "normal") -> list[dict]:
        """返回该副本各星级的多维度条件（时间/死亡/被击/特殊目标）。"""
        thresholds = self.get_thresholds(dungeon, difficulty)
        conditions = []
        for star in (1, 2, 3):
            idx = star - 1
            conditions.append({
                "stars": star,
                _CONDITION_LABELS["time"]: thresholds.time[idx],
                _CONDITION_LABELS["deaths"]: thresholds.deaths[idx],
                _CONDITION_LABELS["hits"]: thresholds.hits[idx],
                _CONDITION_LABELS["objective"]: (
                    True if not thresholds.requires_objective else star == 3
                ),
            })
        return conditions

    # ---------- 星级奖励（bug2） ----------

    def get_star_reward(self, stars: int, difficulty: str = "normal") -> dict:
        stars = max(1, min(3, stars))
        reward = dict(BASE_REWARD[stars])
        mult = self.get_difficulty_multiplier(difficulty)
        reward["gold"] = round(reward["gold"] * mult)
        reward["exp"] = round(reward["exp"] * mult)
        if stars == 3:
            reward["bonus"] = "full_star_bonus"
        return reward

    # ---------- 次数限制与门票（bug3） ----------

    def get_difficulty_multiplier(self, difficulty: str) -> float:
        return DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)

    @staticmethod
    def current_day_key() -> str:
        return date.today().isoformat()

    @staticmethod
    def current_week_key() -> str:
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    def _reset_if_new_period(self) -> None:
        day_key = self.current_day_key()
        if self._daily_key != day_key:
            self._daily_key = day_key
            self.daily_runs = {}
        week_key = self.current_week_key()
        if self._weekly_key != week_key:
            self._weekly_key = week_key
            self.weekly_runs = {}

    def free_runs_remaining(self, player: str) -> int:
        self._reset_if_new_period()
        daily_left = DAILY_FREE_LIMIT - self.daily_runs.get(player, 0)
        weekly_left = WEEKLY_FREE_LIMIT - self.weekly_runs.get(player, 0)
        return max(0, min(daily_left, weekly_left))

    def can_run(self, player: str) -> bool:
        if self.free_runs_remaining(player) > 0:
            return True
        return self.tickets.get(player, 0) > 0

    def consume_run(self, player: str) -> None:
        """结算一次挑战次数：优先消耗免费次数，否则消耗门票。"""
        self._reset_if_new_period()
        if self.free_runs_remaining(player) > 0:
            self.daily_runs[player] = self.daily_runs.get(player, 0) + 1
            self.weekly_runs[player] = self.weekly_runs.get(player, 0) + 1
            return
        if self.tickets.get(player, 0) > 0:
            self.tickets[player] -= 1
            return
        raise RuntimeError("挑战次数已用完，需要门票")

    def give_ticket(self, player: str, count: int = 1) -> None:
        self.tickets[player] = self.tickets.get(player, 0) + count

    # ---------- 多维度综合评星（bug4 + bug5） ----------

    @staticmethod
    def _dimension_stars(value: float, thresholds: tuple) -> int:
        for star in (3, 2, 1):
            if value <= thresholds[star - 1]:
                return star
        return 0

    def calculate_stars(self, record: RunRecord) -> int:
        """时间 + 死亡 + 被击 + 特殊目标的综合评价，取最低维度。

        难度越高，时间/容错门槛越严格。
        """
        thresholds = self.get_thresholds(record.dungeon, record.difficulty)
        time_stars = self._dimension_stars(record.time_seconds, thresholds.time)
        death_stars = self._dimension_stars(record.deaths, thresholds.deaths)
        hit_stars = self._dimension_stars(record.hits_taken, thresholds.hits)
        stars = min(time_stars, death_stars, hit_stars)
        if thresholds.requires_objective and not record.objective_completed:
            stars = min(stars, 2)
        if stars < 1:
            stars = 1
        record.stars = stars
        return stars

    # ---------- 历史最佳（bug6） ----------

    def record_run(self, record: RunRecord) -> dict:
        if record.stars == 0:
            self.calculate_stars(record)
        self.records.append(record)
        self.history.setdefault(record.dungeon, []).append(record)

        previous = self.best_records.get(record.dungeon)
        improved = previous is None or self._is_better(record, previous)
        comparison = self._compare_records(record, previous)
        if improved:
            self.best_records[record.dungeon] = record

        comparison["improved"] = improved
        return comparison

    @staticmethod
    def _is_better(candidate: RunRecord, current: RunRecord) -> bool:
        if candidate.stars != current.stars:
            return candidate.stars > current.stars
        if candidate.time_seconds != current.time_seconds:
            return candidate.time_seconds < current.time_seconds
        if candidate.deaths != current.deaths:
            return candidate.deaths < current.deaths
        return candidate.hits_taken < current.hits_taken

    def get_best_record(self, dungeon: str) -> RunRecord | None:
        return self.best_records.get(dungeon)

    def get_history(self, dungeon: str) -> list[RunRecord]:
        return list(self.history.get(dungeon, []))

    def compare_with_best(self, record: RunRecord) -> dict:
        """对比本次与历史最佳，便于玩家查看提升。"""
        return self._compare_records(record, self.best_records.get(record.dungeon))

    @staticmethod
    def _compare_records(record: RunRecord, best: RunRecord | None) -> dict:
        if best is None:
            return {"stars_delta": record.stars, "time_delta": None,
                    "deaths_delta": None, "hits_delta": None,
                    "is_first_clear": True}
        return {
            "stars_delta": record.stars - best.stars,
            "time_delta": round(record.time_seconds - best.time_seconds, 2),
            "deaths_delta": record.deaths - best.deaths,
            "hits_delta": record.hits_taken - best.hits_taken,
            "is_first_clear": False,
        }

    # ---------- 组队团队星级（bug7） ----------

    def is_team_star(self, record: RunRecord) -> bool:
        return bool(getattr(record, "is_team", False))

    def aggregate_team(self, members: dict) -> RunRecord:
        """汇总团队表现：时间取最慢者，死亡/被击全员累加。"""
        records = list(members.values())
        first = records[0]
        total_deaths = sum(item.deaths for item in records)
        total_hits = sum(item.hits_taken for item in records)
        max_time = max(item.time_seconds for item in records)
        objective = all(getattr(item, "objective_completed", False)
                        for item in records)
        team_record = RunRecord(
            rid=f"team_{first.rid}",
            dungeon=first.dungeon,
            difficulty=first.difficulty,
            time_seconds=max_time,
            deaths=total_deaths,
            hits_taken=total_hits,
            objective_completed=objective,
            is_team=True,
            team_size=len(records),
        )
        self.team_deaths = dict(members) if all(
            isinstance(value, int) for value in members.values()
        ) else {name: item.deaths for name, item in members.items()}
        return team_record

    def calculate_team_stars(self, members) -> int:
        """组队星级按团队表现：任何队员死亡都计入团队星级。

        members 可为 {队员名: RunRecord}，或直接给一份已汇总的 RunRecord。
        """
        if isinstance(members, RunRecord):
            team_record = members
            team_record.is_team = True
        else:
            team_record = self.aggregate_team(members)
        return self.calculate_stars(team_record)
