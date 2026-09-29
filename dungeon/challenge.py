"""副本挑战与星级系统。

修复点：
1. 星级条件按副本类型区分（时间 / 死亡次数 / 被击数 / 特殊目标）。
2. 星级奖励按星级阶梯发放，满星有额外奖励。
3. 每日 / 每周挑战次数限制，超限后需消耗门票。
4. 星级按时间 + 死亡 + 被击 + 目标完成多维度综合评价。
5. 难度影响星级条件，难度越高要求越严格。
6. 保存历史最佳记录，可与历史成绩对比提升。
7. 组队副本按团队表现评价，任何队员死亡都影响团队星级。
"""
from dataclasses import dataclass, field, replace

DAILY_LIMIT = 10
WEEKLY_LIMIT = 30

# 各星级基础奖励（1~3 星递增）。
STAR_REWARDS = {
    1: {"gold": 100, "exp": 20},
    2: {"gold": 250, "exp": 60},
    3: {"gold": 500, "exp": 150},
}
# 满星额外奖励。
FULL_STAR_BONUS = {"gold": 200, "items": ["star_chest"]}

# 难度系数：越高档的难度，条件越严格（时间上限按系数缩短，
# 死亡 / 被击容许次数按系数缩减）。
DIFFICULTY_MULTIPLIER = {
    "easy": 0.8,
    "normal": 1.0,
    "hard": 1.5,
    "nightmare": 2.0,
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
    objectives_completed: int = 0
    objectives_total: int = 0


@dataclass(frozen=True)
class DungeonConfig:
    kind: str  # timed / survival / defense / objective
    team: bool
    # 三个星级（1/2/3）各自的达标门槛，由松到严。
    time_limits: tuple[float, float, float]
    death_limits: tuple[int, int, int]
    hit_limits: tuple[int, int, int]
    objective_targets: tuple[int, int, int] = (0, 0, 0)


# 不同副本类型侧重不同维度：
# timed 竞速、survival 少死亡、defense 少被击、objective 特殊目标。
DUNGEON_CONFIGS: dict[str, DungeonConfig] = {
    "dungeon_a": DungeonConfig(
        kind="timed", team=False,
        time_limits=(300, 210, 150),
        death_limits=(5, 2, 0),
        hit_limits=(40, 20, 10),
    ),
    "dungeon_b": DungeonConfig(
        kind="survival", team=False,
        time_limits=(600, 480, 360),
        death_limits=(3, 1, 0),
        hit_limits=(30, 15, 5),
    ),
    "dungeon_c": DungeonConfig(
        kind="defense", team=False,
        time_limits=(480, 360, 240),
        death_limits=(5, 2, 1),
        hit_limits=(20, 10, 3),
    ),
    "dungeon_d": DungeonConfig(
        kind="objective", team=False,
        time_limits=(600, 480, 360),
        death_limits=(5, 2, 0),
        hit_limits=(40, 20, 10),
        objective_targets=(1, 2, 3),
    ),
    "team_dungeon": DungeonConfig(
        kind="survival", team=True,
        time_limits=(600, 480, 360),
        death_limits=(5, 2, 0),
        hit_limits=(40, 20, 10),
    ),
}

# 未注册副本使用的默认配置（综合型）。
DEFAULT_CONFIG = DungeonConfig(
    kind="balanced", team=False,
    time_limits=(300, 210, 150),
    death_limits=(5, 2, 0),
    hit_limits=(40, 20, 10),
)


class ChallengeSystem:
    def __init__(self):
        self.records: list[RunRecord] = []
        self.daily_runs: dict[str, int] = {}
        self.weekly_runs: dict[str, int] = {}
        self.tickets: dict[str, int] = {}
        self.tickets_used: dict[str, int] = {}
        self.best_records: dict[str, RunRecord] = {}
        self.history_records: dict[str, list[RunRecord]] = {}
        # 组队副本中每名队员的死亡次数，团队星级汇总计算。
        self.team_deaths: dict[str, int] = {}

    # ---- 副本配置 -------------------------------------------------

    def _get_config(self, dungeon: str) -> DungeonConfig:
        if dungeon in DUNGEON_CONFIGS:
            return DUNGEON_CONFIGS[dungeon]
        if "team" in dungeon:
            return DUNGEON_CONFIGS["team_dungeon"]
        return DEFAULT_CONFIG

    def get_difficulty_multiplier(self, difficulty: str) -> float:
        # 难度系数大于 1 表示条件更严格（时间上限缩短、容错次数减少）。
        return DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)

    def get_star_conditions(self, dungeon: str, difficulty: str = "normal") -> list[dict]:
        """返回 1/2/3 星各自的达标条件，随副本类型与难度变化。"""
        config = self._get_config(dungeon)
        multiplier = self.get_difficulty_multiplier(difficulty)
        conditions = []
        for star in (1, 2, 3):
            idx = star - 1
            time_limit = config.time_limits[idx] / multiplier
            death_limit = 0 if config.death_limits[idx] == 0 else int(
                config.death_limits[idx] // multiplier
            )
            hit_limit = 0 if config.hit_limits[idx] == 0 else int(
                config.hit_limits[idx] // multiplier
            )
            conditions.append({
                "star": star,
                "dungeon": dungeon,
                "type": config.kind,
                "difficulty": difficulty,
                "time_seconds": round(time_limit, 1),
                "max_deaths": death_limit,
                "max_hits_taken": hit_limit,
                "objectives": config.objective_targets[idx],
            })
        return conditions

    # ---- 奖励 -----------------------------------------------------

    def get_star_reward(self, stars: int) -> dict:
        stars = max(1, min(3, stars))
        reward = dict(STAR_REWARDS[stars])
        if stars == 3:
            # 满星额外奖励。
            reward["gold"] += FULL_STAR_BONUS["gold"]
            reward["bonus_items"] = list(FULL_STAR_BONUS["items"])
        return reward

    # ---- 次数限制 -------------------------------------------------

    def can_run(self, player: str, use_ticket: bool = False) -> bool:
        if self.daily_runs.get(player, 0) >= DAILY_LIMIT:
            return self._consume_ticket(player) if use_ticket else False
        if self.weekly_runs.get(player, 0) >= WEEKLY_LIMIT:
            return self._consume_ticket(player) if use_ticket else False
        return True

    def _consume_ticket(self, player: str) -> bool:
        if self.tickets.get(player, 0) > 0:
            self.tickets[player] -= 1
            self.tickets_used[player] = self.tickets_used.get(player, 0) + 1
            return True
        return False

    def record_run_attempt(self, player: str, use_ticket: bool = False) -> bool:
        """尝试开启一次挑战；成功放行时累加当日 / 当周次数。"""
        if not self.can_run(player, use_ticket=use_ticket):
            return False
        self.daily_runs[player] = self.daily_runs.get(player, 0) + 1
        self.weekly_runs[player] = self.weekly_runs.get(player, 0) + 1
        return True

    def reset_daily(self) -> None:
        self.daily_runs.clear()

    def reset_weekly(self) -> None:
        self.weekly_runs.clear()

    # ---- 星级评价 -------------------------------------------------

    def _meets_tier(self, record: RunRecord, tier: dict) -> bool:
        if record.time_seconds > tier["time_seconds"]:
            return False
        if record.deaths > tier["max_deaths"]:
            return False
        if record.hits_taken > tier["max_hits_taken"]:
            return False
        target = tier["objectives"]
        if target > 0 and record.objectives_completed < target:
            return False
        return True

    def calculate_stars(self, record: RunRecord) -> int:
        """综合时间、死亡、被击、特殊目标四维评价，取满足的最高星级。"""
        conditions = self.get_star_conditions(record.dungeon, record.difficulty)
        stars = 0
        for tier in conditions:
            if self._meets_tier(record, tier):
                stars = tier["star"]
        record.stars = stars
        return stars

    def is_team_star(self, record: RunRecord) -> bool:
        # 仅组队副本按团队表现评星，单人副本仍按个人表现。
        return self._get_config(record.dungeon).team

    def calculate_team_stars(self, record: RunRecord, player: str | None = None) -> int:
        """团队星级：汇总全队死亡次数，任何队员阵亡都会拉低团队星级。"""
        teammate_deaths = sum(
            deaths for member, deaths in self.team_deaths.items()
            if member != player
        )
        team_record = replace(record, deaths=record.deaths + teammate_deaths)
        stars = self.calculate_stars(team_record)
        record.stars = stars
        return stars

    def evaluate(self, record: RunRecord, player: str | None = None) -> int:
        if self.is_team_star(record):
            return self.calculate_team_stars(record, player)
        return self.calculate_stars(record)

    # ---- 历史最佳 -------------------------------------------------

    def save_record(self, record: RunRecord) -> bool:
        """保存一次挑战记录；若刷新历史最佳则返回 True。"""
        self.records.append(record)
        self.history_records.setdefault(record.dungeon, []).append(record)
        best = self.best_records.get(record.dungeon)
        if best is None or self._is_better(record, best):
            self.best_records[record.dungeon] = record
            return True
        return False

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
        return list(self.history_records.get(dungeon, []))

    def compare_to_best(self, dungeon: str, record: RunRecord) -> dict:
        """将一次成绩与历史最佳对比，便于玩家看到提升差距。"""
        best = self.best_records.get(dungeon)
        if best is None:
            return {"has_best": False, "improved": True}
        return {
            "has_best": True,
            "improved": self._is_better(record, best),
            "stars_delta": record.stars - best.stars,
            "time_delta": round(best.time_seconds - record.time_seconds, 1),
            "deaths_delta": best.deaths - record.deaths,
            "hits_delta": best.hits_taken - record.hits_taken,
            "best_rid": best.rid,
        }
