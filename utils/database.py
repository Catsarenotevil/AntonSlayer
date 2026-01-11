"""
Database helper
"""

from datetime import datetime
import aiosqlite

DB_FILE = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        # State
        await db.execute("""
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await db.execute("""
            INSERT OR IGNORE INTO state (key, value)
            VALUES ('last_match_id', NULL)
        """)

        # Match history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS match_history (
                match_id TEXT NOT NULL,
                steam64_id TEXT NOT NULL,

                finished_at INTEGER NOT NULL,
                data_source TEXT NOT NULL,
                data_source_match_id TEXT,
                map_name TEXT NOT NULL,
                has_banned_player INTEGER NOT NULL,

                initial_team_number INTEGER,
                team_score INTEGER,
                enemy_team_score INTEGER,
                win INTEGER,

                name TEXT,

                total_kills INTEGER,
                total_deaths INTEGER,
                total_assists INTEGER,
                total_hs_kills INTEGER,
                kd_ratio REAL,
                mvps INTEGER,
                score INTEGER,

                total_damage INTEGER,
                dpr REAL,
                rounds_count INTEGER,
                rounds_survived INTEGER,
                rounds_survived_percentage REAL,
                rounds_won INTEGER,
                rounds_lost INTEGER,

                accuracy REAL,
                accuracy_enemy_spotted REAL,
                accuracy_head REAL,
                spray_accuracy REAL,
                preaim REAL,
                reaction_time REAL,

                shots_fired INTEGER,
                shots_fired_enemy_spotted INTEGER,
                shots_hit_foe INTEGER,
                shots_hit_foe_head INTEGER,
                shots_hit_friend INTEGER,
                shots_hit_friend_head INTEGER,

                utility_on_death_avg REAL,
                he_thrown INTEGER,
                he_foes_damage_avg REAL,
                he_friends_damage_avg REAL,
                molotov_thrown INTEGER,
                smoke_thrown INTEGER,
                flashbang_thrown INTEGER,
                flashbang_hit_foe INTEGER,
                flashbang_hit_friend INTEGER,
                flashbang_leading_to_kill INTEGER,
                flashbang_hit_foe_avg_duration REAL,
                flash_assist INTEGER,

                counter_strafing_shots_all INTEGER,
                counter_strafing_shots_good INTEGER,
                counter_strafing_shots_bad INTEGER,
                counter_strafing_shots_good_ratio REAL,

                trade_kill_opportunities INTEGER,
                trade_kill_attempts INTEGER,
                trade_kills_succeed INTEGER,
                trade_kill_attempts_percentage REAL,
                trade_kills_success_percentage REAL,
                trade_kill_opportunities_per_round REAL,

                traded_death_opportunities INTEGER,
                traded_death_attempts INTEGER,
                traded_deaths_succeed INTEGER,
                traded_death_attempts_percentage REAL,
                traded_deaths_success_percentage REAL,
                traded_deaths_opportunities_per_round REAL,

                multi1k INTEGER,
                multi2k INTEGER,
                multi3k INTEGER,
                multi4k INTEGER,
                multi5k INTEGER,

                leetify_rating REAL,
                ct_leetify_rating REAL,
                t_leetify_rating REAL,

                PRIMARY KEY (match_id, steam64_id)
            )
        """)

        # Index for fast /history queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_match_history_steam_time
            ON match_history (steam64_id, finished_at DESC)
        """)

        await db.commit()
        print("initialized database")

async def get_last_match_id():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT value FROM state WHERE key = 'last_match_id'"
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_last_match_id(match_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE state SET value = ? WHERE key = 'last_match_id'",
            (match_id,)
        )
        await db.commit()

async def insert_match(match: dict):
    async with aiosqlite.connect(DB_FILE) as db:
        match_id = match["id"]
        finished_at = iso_to_unix(match["finished_at"])
        data_source = match["data_source"]
        data_source_match_id = match.get("data_source_match_id")
        map_name = match["map_name"]
        has_banned_player = int(match["has_banned_player"])

        # Build team score lookup
        team_scores = {
            team["team_number"]: team["score"]
            for team in match.get("team_scores", [])
        }

        rows = []

        for p in match["stats"]:
            steam64_id = p["steam64_id"]
            initial_team = p.get("initial_team_number")

            team_score = team_scores.get(initial_team)
            enemy_score = None
            win = None

            if team_score is not None and len(team_scores) == 2:
                enemy_score = next(
                    score for team, score in team_scores.items()
                    if team != initial_team
                )
                win = int(team_score > enemy_score)

            rows.append((
                match_id,
                steam64_id,
                finished_at,
                data_source,
                data_source_match_id,
                map_name,
                has_banned_player,

                initial_team,
                team_score,
                enemy_score,
                win,

                p.get("name"),

                p.get("total_kills"),
                p.get("total_deaths"),
                p.get("total_assists"),
                p.get("total_hs_kills"),
                p.get("kd_ratio"),
                p.get("mvps"),
                p.get("score"),

                p.get("total_damage"),
                p.get("dpr"),
                p.get("rounds_count"),
                p.get("rounds_survived"),
                p.get("rounds_survived_percentage"),
                p.get("rounds_won"),
                p.get("rounds_lost"),

                p.get("accuracy"),
                p.get("accuracy_enemy_spotted"),
                p.get("accuracy_head"),
                p.get("spray_accuracy"),
                p.get("preaim"),
                p.get("reaction_time"),

                p.get("shots_fired"),
                p.get("shots_fired_enemy_spotted"),
                p.get("shots_hit_foe"),
                p.get("shots_hit_foe_head"),
                p.get("shots_hit_friend"),
                p.get("shots_hit_friend_head"),

                p.get("utility_on_death_avg"),
                p.get("he_thrown"),
                p.get("he_foes_damage_avg"),
                p.get("he_friends_damage_avg"),
                p.get("molotov_thrown"),
                p.get("smoke_thrown"),
                p.get("flashbang_thrown"),
                p.get("flashbang_hit_foe"),
                p.get("flashbang_hit_friend"),
                p.get("flashbang_leading_to_kill"),
                p.get("flashbang_hit_foe_avg_duration"),
                p.get("flash_assist"),

                p.get("counter_strafing_shots_all"),
                p.get("counter_strafing_shots_good"),
                p.get("counter_strafing_shots_bad"),
                p.get("counter_strafing_shots_good_ratio"),

                p.get("trade_kill_opportunities"),
                p.get("trade_kill_attempts"),
                p.get("trade_kills_succeed"),
                p.get("trade_kill_attempts_percentage"),
                p.get("trade_kills_success_percentage"),
                p.get("trade_kill_opportunities_per_round"),

                p.get("traded_death_opportunities"),
                p.get("traded_death_attempts"),
                p.get("traded_deaths_succeed"),
                p.get("traded_death_attempts_percentage"),
                p.get("traded_deaths_success_percentage"),
                p.get("traded_deaths_opportunities_per_round"),

                p.get("multi1k"),
                p.get("multi2k"),
                p.get("multi3k"),
                p.get("multi4k"),
                p.get("multi5k"),

                p.get("leetify_rating"),
                p.get("ct_leetify_rating"),
                p.get("t_leetify_rating"),
            ))

        await db.executemany("""
            INSERT OR REPLACE INTO match_history (
                match_id,
                steam64_id,
                finished_at,
                data_source,
                data_source_match_id,
                map_name,
                has_banned_player,

                initial_team_number,
                team_score,
                enemy_team_score,
                win,

                name,

                total_kills,
                total_deaths,
                total_assists,
                total_hs_kills,
                kd_ratio,
                mvps,
                score,

                total_damage,
                dpr,
                rounds_count,
                rounds_survived,
                rounds_survived_percentage,
                rounds_won,
                rounds_lost,

                accuracy,
                accuracy_enemy_spotted,
                accuracy_head,
                spray_accuracy,
                preaim,
                reaction_time,

                shots_fired,
                shots_fired_enemy_spotted,
                shots_hit_foe,
                shots_hit_foe_head,
                shots_hit_friend,
                shots_hit_friend_head,

                utility_on_death_avg,
                he_thrown,
                he_foes_damage_avg,
                he_friends_damage_avg,
                molotov_thrown,
                smoke_thrown,
                flashbang_thrown,
                flashbang_hit_foe,
                flashbang_hit_friend,
                flashbang_leading_to_kill,
                flashbang_hit_foe_avg_duration,
                flash_assist,

                counter_strafing_shots_all,
                counter_strafing_shots_good,
                counter_strafing_shots_bad,
                counter_strafing_shots_good_ratio,

                trade_kill_opportunities,
                trade_kill_attempts,
                trade_kills_succeed,
                trade_kill_attempts_percentage,
                trade_kills_success_percentage,
                trade_kill_opportunities_per_round,

                traded_death_opportunities,
                traded_death_attempts,
                traded_deaths_succeed,
                traded_death_attempts_percentage,
                traded_deaths_success_percentage,
                traded_deaths_opportunities_per_round,

                multi1k,
                multi2k,
                multi3k,
                multi4k,
                multi5k,

                leetify_rating,
                ct_leetify_rating,
                t_leetify_rating
            ) 
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?
            )
        """, rows)

        await db.commit()


def iso_to_unix(ts: str) -> int:
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
