"""副本挑战与星级系统 - 含7个bug"""
from dataclasses import dataclass, field

@dataclass
class RunRecord:
    rid: str
    dungeon: str
    difficulty: str
    time_seconds: float
    deaths: int
    hits_taken: int
    stars: int = 0

class ChallengeSystem:
    def __init__(self):
        self.records: list[RunRecord] = []
        self.daily_runs: dict[str, int] = {}  # bug3: 无次数限制
        self.best_records: dict[str, RunRecord] = {}  # bug6: 无历史最佳

    def get_star_conditions(self, dungeon: str) -> list:
        # bug1: 固定条件
        return ["clear_under_180s"]

    def get_star_reward(self, stars: int) -> dict:
        # bug2: 固定奖励
        return {"gold": 100}

    def can_run(self, player: str) -> bool:
        # bug3: 无次数限制
        return True

    def calculate_stars(self, record: RunRecord) -> int:
        # bug4: 只看时间
        if record.time_seconds < 180:
            return 3
        return 1

    def get_difficulty_multiplier(self, difficulty: str) -> float:
        # bug5: 难度不影响
        return 1.0

    def get_best_record(self, dungeon: str) -> RunRecord | None:
        # bug6: 无历史最佳
        return None

    def is_team_star(self, record: RunRecord) -> bool:
        # bug7: 个人星级
        return True
