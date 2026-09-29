"""副本挑战与星级系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dungeon.challenge import ChallengeSystem, RunRecord

class TestStarConditions:
    def test_different_dungeons_have_different_conditions(self):
        cs = ChallengeSystem()
        c1 = cs.get_star_conditions("dungeon_a")
        c2 = cs.get_star_conditions("dungeon_b")
        assert c1 != c2 or len(c1) > 1

class TestStarReward:
    def test_more_stars_better_reward(self):
        cs = ChallengeSystem()
        r1 = cs.get_star_reward(1)
        r3 = cs.get_star_reward(3)
        assert r3["gold"] > r1["gold"]

class TestRunLimit:
    def test_daily_run_limit(self):
        cs = ChallengeSystem()
        cs.daily_runs["p1"] = 10
        assert cs.can_run("p1") == False

class TestMultiDimStars:
    def test_deaths_affect_stars(self):
        cs = ChallengeSystem()
        r1 = RunRecord("r1", "d1", "normal", 120, deaths=0, hits_taken=10)
        r2 = RunRecord("r2", "d1", "normal", 120, deaths=5, hits_taken=10)
        s1 = cs.calculate_stars(r1)
        s2 = cs.calculate_stars(r2)
        assert s1 > s2

class TestDifficultyMultiplier:
    def test_hard_difficulty_has_stricter_conditions(self):
        cs = ChallengeSystem()
        m_normal = cs.get_difficulty_multiplier("normal")
        m_hard = cs.get_difficulty_multiplier("hard")
        assert m_hard > m_normal

class TestBestRecord:
    def test_best_record_saved(self):
        cs = ChallengeSystem()
        rec = RunRecord("r1", "d1", "normal", 100, 0, 5, stars=3)
        cs.records.append(rec)
        cs.best_records["d1"] = rec
        best = cs.get_best_record("d1")
        assert best is not None and best.stars == 3

class TestTeamStar:
    def test_team_deaths_affect_team_star(self):
        cs = ChallengeSystem()
        # 组队星级应该看团队
        assert hasattr(cs, "team_deaths")
        cs.team_deaths = {"p1": 0, "p2": 3}
        rec = RunRecord("r1", "d1", "normal", 100, 0, 5)
        # 团队有人死应该影响星级
        assert hasattr(cs, "calculate_team_stars")
