import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List, Tuple
import sqlite3
import shutil
import aiohttp

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

# ====== ENV ======
# Varför använder vi .strip(), är det något jag missar?
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "0"))
TARGET_STEAM64 = os.getenv("TARGET_STEAM64", "").strip()  # Anton Steam64
ANTON_KILLS_MAX = int(os.getenv("ANTON_KILLS_MAX", "12"))
BOT_OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0"))  # ditt Discord User ID
# DEV_MODE: om sann värde tillåts alla köra owner-only kommandon (användbart för test)
DEV_MODE = str(os.getenv("DEV_MODE", "0")).strip().lower() in ("1", "true", "yes")
# Optional TEST_GUILD_ID for fast guild-level slash command sync during development
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID", "").strip() or None
LEETIFY_TOKEN = os.getenv("LEETIFY_TOKEN", "")

if not DISCORD_TOKEN or TARGET_CHANNEL_ID == 0:
    raise RuntimeError("Saknar DISCORD_TOKEN eller TARGET_CHANNEL_ID i .env")

# ====== FILES ======
HISTORY_FILE = "anton_history.jsonl"  # ligger i samma mapp som scriptet
DB_FILE = "anton.db"  # SQLite database för historik

# ====== DISCORD BOT ======
# Slash commands kräver inte message_content intent
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ====== ROASTS (mild satir) ======
ROASTS_BRUTAL = [
    "Anton got more job interviews than kills this match.",
    "Anton, even Volvo would reject you after this performance.",
    "Anton, you have more failed interviews than headshots.",
    "Anton, your gameplay is so bad even Volvo HR is laughing.",
    "Anton, you should apply to Volvo – they love people who never hit their targets.",
    "Anton, you missed more shots than you missed job offers from Volvo.",
]
ROASTS_MEDIUM = [
    "Anton, du hade kunnat vinna fler dueller om du spelade med fötterna.",
    "Anton, du är som en eco-runda – ingen förväntar sig något.",
    "Anton, du är så tyst på servern att till och med Discord undrar om du lever.",
    "Anton, du är som en smoke – försvinner när det gäller.",
    "Anton, du är som en decoy – ingen bryr sig.",
]
ROASTS_MILD = [
    "Anton, det var en match. Mer än så var det inte.",
    "Anton, du var där. Det är ändå något.",
    "Anton, ibland är det bättre att bara titta på.",
    "Anton, du försökte i alla fall. Tror vi.",
    "Anton, det är tanken som räknas. Kanske.",
]

# Vanliga CS2-kartor för autocompletion (värden normaliseras internt)
MAPS = [
    "mirage",
    "dust2",
    "inferno",
    "ancient",
    "nuke",
    "overpass",
    "anubis",
    "vertigo",
    "train",
    "cache",
]

def pick_roast(kills: int) -> str:
    import random
    if kills <= 3:
        return random.choice(ROASTS_BRUTAL)
    elif kills <= 8:
        return random.choice(ROASTS_MEDIUM)
    else:
        return random.choice(ROASTS_MILD)

# ====== STATE ======
latest_payload: Dict[str, Any] = {}
last_post_sig: Optional[str] = None
posting_lock: bool = False

last_anton_kills: Optional[int] = None
last_map: Optional[str] = None
last_phase: Optional[str] = None

# ====== HELPERS ======
def _get(d: Dict[str, Any], *keys, default=None):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def _players(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ap = _get(payload, "allplayers", default=None)
    return ap if isinstance(ap, dict) else None

def _kills(p: Dict[str, Any]) -> Optional[int]:
    ms = p.get("match_stats")
    if isinstance(ms, dict) and "kills" in ms:
        try:
            return int(ms["kills"])
        except Exception:
            return None
    return None

def _match_signature(payload: Dict[str, Any]) -> str:
    ts = _get(payload, "provider", "timestamp", default=None)
    if ts is not None:
        return f"ts:{ts}"
    map_name = str(_get(payload, "map", "name", default="")).strip()
    phase = str(_get(payload, "map", "phase", default="")).strip()
    rnd = str(_get(payload, "map", "round", default="")).strip()
    return f"{map_name}|p:{phase}|r:{rnd}"

async def _post_to_channel(text: Optional[str] = None, embed: Optional[discord.Embed] = None):
    try:
        ch = await bot.fetch_channel(TARGET_CHANNEL_ID)
        if embed is not None:
            # send embed (with optional content)
            await ch.send(content=text if text else None, embed=embed)
        else:
            if text is None:
                text = ""
            await ch.send(text)
    except Exception as e:
        print("Kunde inte posta i kanalen:", repr(e))

def _owner_only(interaction: discord.Interaction) -> bool:
    # If DEV_MODE is enabled allow all users to run owner-only commands (for testing)
    if DEV_MODE:
        return True
    return BOT_OWNER_ID != 0 and interaction.user.id == BOT_OWNER_ID

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _db_execute(query: str, params: tuple = ()): 
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur
    finally:
        if conn:
            conn.close()


def _db_query(query: str, params: tuple = ()) -> list:
    conn = sqlite3.connect(DB_FILE)
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def _insert_match_db(ts_iso: str, ts_epoch: int, kills: int, source: str, map_name: Optional[str], stats: Optional[Dict[str, Any]], sig: Optional[str]):
    stats_json = json.dumps(stats, ensure_ascii=False) if stats else None
    try:
        _db_execute(
            """INSERT INTO matches (ts_iso, ts_epoch, kills, source, map, stats_json, sig)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ts_iso, ts_epoch, kills, source, map_name, stats_json, sig),
        )
    except sqlite3.IntegrityError:
        # duplicate sig or other integrity issue
        raise
    except Exception as e:
        print("DB insert error:", repr(e))


def init_db():
    """Create DB file and matches table if not exists."""
    _db_execute(
        """CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_iso TEXT NOT NULL,
            ts_epoch INTEGER,
            kills INTEGER,
            source TEXT,
            map TEXT,
            stats_json TEXT,
            sig TEXT UNIQUE
        )""",
        (),
    )
    _db_execute("CREATE INDEX IF NOT EXISTS idx_matches_ts ON matches(ts_epoch)", ())


def migrate_jsonl_to_db():
    """Migrate existing JSONL history into DB if DB is empty and JSONL exists."""
    try:
        rows = _db_query("SELECT COUNT(*) FROM matches", ())
        count = rows[0][0] if rows else 0
    except Exception:
        count = 0

    if count > 0:
        return  # already have data

    if not os.path.exists(HISTORY_FILE):
        return

    # backup
    bak = HISTORY_FILE + ".bak"
    try:
        shutil.copyfile(HISTORY_FILE, bak)
    except Exception:
        pass

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts")
                    if not ts:
                        continue
                    try:
                        dt = datetime.fromisoformat(ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        dt = _utc_now()
                    ts_iso = dt.isoformat()
                    ts_epoch = int(dt.timestamp())
                    kills = int(rec.get("kills", 0))
                    source = rec.get("source", "jsonl")
                    map_name = rec.get("map")
                    stats = rec.get("stats")
                    sig = f"ts:{ts_iso}"
                    try:
                        _insert_match_db(ts_iso, ts_epoch, kills, source, map_name, stats, sig)
                    except sqlite3.IntegrityError:
                        continue
                except Exception:
                    continue
    except Exception as e:
        print("Migration error:", repr(e))


def _append_history(kills: int, source: str, map_name: Optional[str], ts: Optional[datetime] = None, stats: Optional[Dict[str, Any]] = None, sig: Optional[str] = None):
    """Persist match both to SQLite and append to JSONL as backup."""

    ts_dt = ts if isinstance(ts, datetime) else _utc_now()
    ts_iso = ts_dt.isoformat()
    ts_epoch = int(ts_dt.timestamp())

    # Insert into DB (sig may be None)
    try:
        _insert_match_db(ts_iso, ts_epoch, int(kills), source, map_name, stats, sig)
    except sqlite3.IntegrityError:
        # already exists
        print("Duplicate match sig, skipping DB insert.")
    except Exception:
        pass

    # Also append to JSONL (as backup/human-readable)
    rec: Dict[str, Any] = {
        "ts": ts_iso,
        "kills": int(kills),
        "source": source,
        "map": map_name or None,
    }
    if stats:
        rec["stats"] = stats
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        print("History write error:", repr(e))

def _read_history(days: int = 7) -> List[Dict[str, Any]]:
    """Reads history from SQLite if available, otherwise falls back to JSONL."""
    cutoff = _utc_now() - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    out: List[Dict[str, Any]] = []

    # Prefer DB
    try:
        rows = _db_query("SELECT ts_iso, kills, source, map, stats_json FROM matches WHERE ts_iso >= ? ORDER BY ts_iso ASC", (cutoff_iso,))
        for ts_iso, kills, source, map_name, stats_json in rows:
            rec: Dict[str, Any] = {"ts": ts_iso, "kills": int(kills), "source": source, "map": map_name}
            if stats_json:
                try:
                    rec["stats"] = json.loads(stats_json)
                except Exception:
                    rec["stats"] = None
            out.append(rec)
        return out
    except Exception:
        # fallback to JSONL
        pass

    # Fallback if DB not available or error
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("ts")
                    if not ts:
                        continue
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt >= cutoff:
                        out.append(rec)
                except Exception:
                    continue
    except FileNotFoundError:
        return []
    except Exception as e:
        print("History read error:", repr(e))
        return []
    return out

def _sparkline(values: List[int]) -> str:
    # enkel unicode-sparkline: ▁▂▃▄▅▆▇█
    if not values:
        return "(no data)"
    blocks = "▁▂▃▄▅▆▇█"
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return blocks[0] * len(values)
    res = []
    for v in values:
        idx = int((v - vmin) * (len(blocks) - 1) / (vmax - vmin))
        idx = max(0, min(len(blocks) - 1, idx))
        res.append(blocks[idx])
    return "".join(res)

def _group_by_day(recs: List[Dict[str, Any]], days: int) -> List[Tuple[str, Optional[float], int]]:
    # return: [(YYYY-MM-DD, avg_kills_or_None, matches_count)]
    now = _utc_now()
    start = (now - timedelta(days=days-1)).date()
    buckets: Dict[str, List[int]] = {}
    counts: Dict[str, int] = {}

    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        buckets[d] = []
        counts[d] = 0

    for r in recs:
        try:
            dt = datetime.fromisoformat(r["ts"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            d = dt.date().isoformat()
            if d in buckets:
                k = int(r["kills"])
                buckets[d].append(k)
                counts[d] += 1
        except Exception:
            continue

    result: List[Tuple[str, Optional[float], int]] = []
    for d in buckets:
        vals = buckets[d]
        if vals:
            result.append((d, sum(vals)/len(vals), counts[d]))
        else:
            result.append((d, None, 0))
    return result

def _normalize_map_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.lower().replace('-', '_')
    if n.startswith('de_'):
        n = n[3:]
    return n

def _filter_by_map(recs: List[Dict[str, Any]], map_name: Optional[str]) -> List[Dict[str, Any]]:
    if not map_name:
        return recs
    nm = _normalize_map_name(map_name)
    out: List[Dict[str, Any]] = []
    for r in recs:
        m = r.get('map')
        if not m:
            continue
        mn = _normalize_map_name(m)
        if mn == nm:
            out.append(r)
    return out

def _aggregate_stats(recs: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
    """Aggregates stats from a list of history records."""
    matches = len(recs)
    kills = [int(r.get('kills', 0)) for r in recs]
    avg_kills = (sum(kills) / len(kills)) if kills else 0.0

    stats_keys = ('adr', 'hs_percent', 'deaths', 'score', 'damage', 'kd')
    sums = {k: 0.0 for k in stats_keys}
    counts = {k: 0 for k in stats_keys}

    for r in recs:
        s = r.get('stats') or {}
        for k in stats_keys:
            if k in s and s[k] is not None:
                try:
                    v = float(s[k])
                    sums[k] += v
                    counts[k] += 1
                except Exception:
                    pass

    avgs: Dict[str, Optional[float]] = {}
    for k in stats_keys:
        avgs[k] = (sums[k] / counts[k]) if counts[k] else None

    top_matches = sorted(recs, key=lambda r: int(r.get('kills', 0)), reverse=True)[:3]
    bottom_matches = sorted(recs, key=lambda r: int(r.get('kills', 0)))[:3]

    daily = _group_by_day(recs, days=days)
    daily_avgs = [int(round(x[1])) if x[1] is not None else 0 for x in daily]
    spark = _sparkline(daily_avgs)

    return {
        'matches': matches,
        'avg_kills': avg_kills,
        'avgs': avgs,
        'top': top_matches,
        'bottom': bottom_matches,
        'spark': spark,
    }

def _update_cached_info(payload: Dict[str, Any]):
    global last_anton_kills, last_map, last_phase
    last_map = str(_get(payload, "map", "name", default=last_map)).strip() or last_map
    last_phase = str(_get(payload, "map", "phase", default=last_phase)).strip() or last_phase

    ap = _players(payload)
    if ap and TARGET_STEAM64:
        anton = ap.get(TARGET_STEAM64)
        if isinstance(anton, dict):
            k = _kills(anton)
            if k is not None:
                last_anton_kills = k

def _set_fake_payload(kills: int, map_name: str = "de_fake", timestamp: Optional[int] = None, stats: Optional[Dict[str, Any]] = None):
    """Förbered latest_payload och mappa till en gameover-match för fake-kommando.

    timestamp: Unix epoch seconds (int). Om None används nuvarande tid.
    stats: optional dict med kompletterande match_stats.
    """
    global latest_payload, last_map, last_phase
    last_map = map_name
    last_phase = "gameover"
    ts_val = int(timestamp) if timestamp is not None else int(_utc_now().timestamp())
    match_stats = {"kills": kills}
    if stats and isinstance(stats, dict):
        # slå ihop - låt explicit 'kills' från param överstyra
        for k, v in stats.items():
            if k == "kills":
                continue
            match_stats[k] = v

    latest_payload = {
        "provider": {"timestamp": ts_val},
        "map": {"name": last_map, "phase": last_phase},
        "allplayers": {
            TARGET_STEAM64: {
                "name": "Anton",
                "team": "T",
                "match_stats": match_stats,
            }
        },
    }
def _extract_player_stats(payload: Dict[str, Any], steam64: str) -> Dict[str, Any]:
    """Extrahera möjliga statistikfält från payload för given spelare.

    Returnerar dict med exempelvis: deaths, score, damage, adr, rounds, hs_percent, kd, kills
    """
    out: Dict[str, Any] = {}
    ap = _players(payload)
    if not ap or not steam64:
        return out
    p = ap.get(steam64)
    if not isinstance(p, dict):
        return out

    ms = p.get("match_stats")
    if not isinstance(ms, dict):
        return out

    # direkta fält som ofta förekommer
    for key in ("deaths", "score", "damage", "adr", "rounds", "assists", "mvps"):
        if key in ms:
            try:
                out[key] = int(ms[key]) if isinstance(ms[key], (int, str)) and str(ms[key]).isdigit() else float(ms[key])
            except Exception:
                out[key] = ms[key]

    # headshot procent
    if "headshot_percent" in ms:
        try:
            out["hs_percent"] = float(ms["headshot_percent"])
        except Exception:
            pass
    elif "headshots" in ms and "kills" in ms:
        try:
            out["hs_percent"] = round(int(ms.get("headshots", 0)) / max(1, int(ms.get("kills", 0))) * 100, 1)
        except Exception:
            pass

    # kills + kd
    if "kills" in ms:
        try:
            k = int(ms["kills"])
            out["kills"] = k
            d = int(ms.get("deaths", 0))
            out["kd"] = round(k / d, 2) if d > 0 else None
        except Exception:
            pass

    return out
# ====== CORE: ONLY ANTON, ONLY IF <= LIMIT ======
async def _sig_exists(sig: str) -> bool:
    try:
        rows = _db_query("SELECT 1 FROM matches WHERE sig = ? LIMIT 1", (sig,))
        return len(rows) > 0
    except Exception:
        return False


async def send_postmatch_roast(source: str = "gsi"):
    ap = _players(latest_payload)
    if not ap or not TARGET_STEAM64:
        return

    anton = ap.get(TARGET_STEAM64)
    if not isinstance(anton, dict):
        return

    kills = _kills(anton)
    if kills is None:
        return

    # compute signature and deduplicate
    sig = _match_signature(latest_payload)
    if await _sig_exists(sig):
        print("Match already posted (sig exists), skipping.")
        return

    # cache + logga ALLTID till history (även om ingen roast)
    global last_anton_kills
    last_anton_kills = kills

    provider_ts = _get(latest_payload, "provider", "timestamp", default=None)
    try:
        if provider_ts is not None:
            provider_ts = int(provider_ts)
            dt = datetime.fromtimestamp(provider_ts, timezone.utc)
        else:
            dt = _utc_now()
    except Exception:
        dt = _utc_now()

    stats = _extract_player_stats(latest_payload, TARGET_STEAM64)
    # use sig when appending history so migration and dedup work
    _append_history(kills, source=source, map_name=last_map, ts=dt, stats=stats, sig=sig)

    # Posta alltid alla matcher till Discord. Om kills är över limit loggas det, men vi postar ändå.
    if kills > ANTON_KILLS_MAX:
        print(f"Anton hade {kills} kills – över limit ({ANTON_KILLS_MAX}), postar ändå.")

    when_str = dt.isoformat()
    map_str = last_map or 'unknown'

    stats_parts = []
    if stats:
        if stats.get("kd") is not None:
            stats_parts.append(f"K/D: {stats.get('kd')}")
        if "adr" in stats:
            stats_parts.append(f"ADR: {stats.get('adr')}")
        if "hs_percent" in stats:
            try:
                stats_parts.append(f"HS%: {float(stats.get('hs_percent')):.0f}%")
            except Exception:
                stats_parts.append(f"HS%: {stats.get('hs_percent')}")
        if "deaths" in stats:
            stats_parts.append(f"Deaths: {stats.get('deaths')}")
        if "score" in stats:
            stats_parts.append(f"Score: {stats.get('score')}")
        if "damage" in stats:
            stats_parts.append(f"Damage: {stats.get('damage')}")

    stats_line = (" | ".join(stats_parts)) if stats_parts else ""

    # Beslut: roast inkluderas om kills <= ANTON_KILLS_MAX, eller om kills < 5 (explicit krav)
    include_roast = (kills <= ANTON_KILLS_MAX) or (kills < 5)


    # Special-case: för very poor games (kills < 5) använd en embed med bild + roast
    if kills < 5:
        img_url = "https://image.pngaaa.com/489/1623489-middle.png"
        roast = pick_roast(kills) if include_roast else ""
        embed = discord.Embed(title=f"Post-match: Anton finished with {kills} kills on {map_str}", description=roast, color=discord.Color.dark_red())
        if stats_line:
            embed.add_field(name="Stats", value=stats_line, inline=False)
        if kills > 20:
            embed.add_field(name="Special", value="Nu spelar knullbengan", inline=False)
        try:
            embed.set_image(url=img_url)
        except Exception:
            pass
        await _post_to_channel(embed=embed)
        return

    # Special-case: Anton spelar galet bra (över 20 kills) – använd embed med din bild
    if kills > 20:
        img_url = "https://media.discordapp.net/attachments/639855776126468106/1458842815298539613/7c2eebe1-c371-4eaa-bdab-0078f7e5699d.jpg?ex=69611cbf&is=695fcb3f&hm=ef9142056bfd0e73de29fced8940377687bd818e8ac5bc6a52a6b7ab81a03269&=&format=webp&width=1053&height=702"
        msg = f"**Post-match:** Anton finished with **{kills} kills** on **{map_str}** at `{when_str} UTC`.\n\nNu spelar knullbengan"
        if stats_line:
            msg += "\n" + "Stats: " + stats_line
        embed = discord.Embed(title=f"🔥 Anton dominerar!", description=msg, color=discord.Color.gold())
        try:
            embed.set_image(url=img_url)
        except Exception:
            pass
        await _post_to_channel(embed=embed)
        return

    # Normal case: text message (roast only if include_roast)
    msg = f"**Post-match:** Anton finished with **{kills} kills** on **{map_str}** at `{when_str} UTC`."
    if include_roast:
        roast = pick_roast(kills)
        msg += "\n" + roast
    if stats_line:
        msg += "\n" + "Stats: " + stats_line

    # Om Anton spelar galet bra (över 20 kills), lägg till specialmeddelande
    if kills > 20:
        msg += "\n\nNu spelar knullbengan"

    await _post_to_channel(msg)

# ====== GSI SERVER ======
async def gsi_handler(request: web.Request):
    global latest_payload, last_post_sig, posting_lock

    try:
        data = await request.json()
    except Exception:
        return web.Response(text="bad json", status=400)

    latest_payload = data
    _update_cached_info(data)

    sig = _match_signature(data)
    phase = str(_get(data, "map", "phase", default="")).strip()

    if phase == "gameover":
        if last_post_sig != sig and not posting_lock:
            posting_lock = True
            asyncio.create_task(_delayed_post(sig))
    else:
        posting_lock = False

    return web.Response(text="ok")

async def _delayed_post(sig: str):
    global last_post_sig, posting_lock
    await asyncio.sleep(2.5)
    try:
        await send_postmatch_roast(source="gsi")
        last_post_sig = sig
    except Exception as e:
        print("Post error:", repr(e))
    finally:
        posting_lock = False

async def start_gsi_server():
    app = web.Application()
    app.router.add_post("/", gsi_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 3000)
    await site.start()
    print("GSI listening on http://127.0.0.1:3000/")

# ====== SLASH COMMANDS ======
@bot.tree.command(name="status", description="Visar botstatus, gräns och senaste kända info")
async def status(interaction: discord.Interaction):
    msg = (
        f"✅ **Status**\n"
        f"• Channel: `{TARGET_CHANNEL_ID}`\n"
        f"• Anton Steam64: `{TARGET_STEAM64 or 'NOT SET'}`\n"
        f"• Roast if Anton kills ≤ **{ANTON_KILLS_MAX}**\n"
        f"• Last map: `{last_map or 'unknown'}`\n"
        f"• Last phase: `{last_phase or 'unknown'}`\n"
        f"• Last Anton kills: `{last_anton_kills if last_anton_kills is not None else 'unknown'}`"
    )
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="whoami", description="Debug: visar ditt user-id, owner-status och DEV_MODE")
async def whoami(interaction: discord.Interaction):
    ok = _owner_only(interaction)
    dm = "ON" if DEV_MODE else "OFF"
    msg = (
        f"Your id: `{interaction.user.id}`\n"
        f"BOT_OWNER_ID: `{BOT_OWNER_ID}`\n"
        f"DEV_MODE: `{dm}`\n"
        f"Owner allowed: `{ok}`"
    )
    await interaction.response.send_message(msg, ephemeral=True)

# Fallback prefix command for quick testing if slash commands don't appear yet
@bot.command(name="whoami")
async def whoami_prefix(ctx: commands.Context):
    ok = DEV_MODE or (BOT_OWNER_ID != 0 and ctx.author.id == BOT_OWNER_ID)
    dm = "ON" if DEV_MODE else "OFF"
    msg = (
        f"Your id: `{ctx.author.id}`\n"
        f"BOT_OWNER_ID: `{BOT_OWNER_ID}`\n"
        f"DEV_MODE: `{dm}`\n"
        f"Owner allowed: `{ok}`"
    )
    try:
        await ctx.author.send(msg)
        await ctx.send("Debug info DM:ad to you.")
    except Exception:
        await ctx.send(msg)

@bot.command(name="clearhistory")
async def clearhistory_prefix(ctx: commands.Context, confirm: Optional[str] = None):
    """Owner-only prefix command to clear history. Usage: `!clearhistory confirm`"""
    ok = DEV_MODE or (BOT_OWNER_ID != 0 and ctx.author.id == BOT_OWNER_ID)
    if not ok:
        return await ctx.send("❌ Owner only.")
    if confirm != "confirm":
        return await ctx.send("⚠️ This will delete ALL history. Run `!clearhistory confirm` to proceed.")

    try:
        # Count before
        rows = _db_query("SELECT COUNT(*) FROM matches", ())
        before = rows[0][0] if rows else 0

        # Backup JSONL if present and truncate
        if os.path.exists(HISTORY_FILE):
            bak = HISTORY_FILE + ".bak"
            try:
                shutil.copyfile(HISTORY_FILE, bak)
            except Exception:
                pass
            try:
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    f.truncate(0)
            except Exception:
                pass

        # Delete DB rows and vacuum
        _db_execute("DELETE FROM matches", ())
        _db_execute("VACUUM", ())

        await ctx.send(f"✅ Historik rensad. Rader borttagna: {before}. JSONL backad upp till `{HISTORY_FILE}.bak`.")
    except Exception as e:
        await ctx.send(f"❌ Fel vid rensning: {e}")

@bot.tree.command(name="setkills", description="Sätt kill-gränsen (endast du)")
async def setkills(interaction: discord.Interaction, value: int):
    global ANTON_KILLS_MAX
    if not _owner_only(interaction):
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    if value < 0 or value > 50:
        return await interaction.response.send_message("❌ Välj ett rimligt tal (0–50).", ephemeral=True)
    ANTON_KILLS_MAX = value
    await interaction.response.send_message(f"🔧 Anton kill-limit set to **{value}**.", ephemeral=True)

@bot.tree.command(name="fakegame", description="Simulera en avslutad match (owner only)")
async def fakegame(interaction: discord.Interaction, kills: int):
    """Backward-compatible alias to queue a fake match (use /fakekills)."""
    if not _owner_only(interaction):
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    if kills < 0 or kills > 50:
        return await interaction.response.send_message("❌ Välj ett rimligt tal (0–50).", ephemeral=True)

    _set_fake_payload(kills)
    await interaction.response.send_message(f"🧪 Fake game queued: Anton = **{kills} kills**.", ephemeral=True)
    # kör posten asynkront så interaction inte hinner time out
    asyncio.create_task(send_postmatch_roast(source="fake"))

@bot.tree.command(name="fakekills", description="Simulera en avslutad match med specificerade kills (owner only)")
async def fakekills(interaction: discord.Interaction, kills: int, map_name: str = "de_fake", when: Optional[str] = None, stats_json: Optional[str] = None):
    """Param `when` kan vara epoch-sekunder (t.ex. 1700000000) eller ISO 8601 (t.ex. 2025-12-31T20:00:00). Om inte angivet används nu.

    `stats_json` är valfritt och bör vara en JSON-sträng med exempelvis: {"deaths":4, "adr":85, "hs_percent":45}
    """
    if not _owner_only(interaction):
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    if kills < 0 or kills > 50:
        return await interaction.response.send_message("❌ Välj ett rimligt tal (0–50).", ephemeral=True)

    ts_val: Optional[int] = None
    if when:
        # försök tolka som epoch int eller ISO 8601
        try:
            ts_val = int(when)
        except Exception:
            try:
                dt = datetime.fromisoformat(when)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts_val = int(dt.timestamp())
            except Exception:
                return await interaction.response.send_message(
                    "❌ Ogiltigt tidsformat. Använd epoch (sek) eller ISO 8601, t.ex. '2025-12-31T20:00:00'.",
                    ephemeral=True,
                )

    stats_obj: Optional[Dict[str, Any]] = None
    if stats_json:
        try:
            stats_obj = json.loads(stats_json)
            if not isinstance(stats_obj, dict):
                raise ValueError("stats must be an object")
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Ogiltig stats-JSON: {e}", ephemeral=True
            )

    _set_fake_payload(kills, map_name, timestamp=ts_val, stats=stats_obj)

    # bekräfta vad som valdes
    confirm = f"🧪 Fake kills queued: Anton = **{kills} kills** on **{map_name}**"
    if ts_val is not None:
        dt_used = datetime.fromtimestamp(ts_val, timezone.utc).isoformat()
        confirm += f" at `{dt_used} UTC`"
    if stats_obj:
        sparts = []
        if "deaths" in stats_obj:
            sparts.append(f"Deaths: {stats_obj.get('deaths')}")
        if "adr" in stats_obj:
            sparts.append(f"ADR: {stats_obj.get('adr')}")
        if "hs_percent" in stats_obj:
            sparts.append(f"HS%: {stats_obj.get('hs_percent')}")
        if "score" in stats_obj:
            sparts.append(f"Score: {stats_obj.get('score')}")
        if sparts:
            confirm += " | " + " | ".join(sparts)

    await interaction.response.send_message(confirm + ".", ephemeral=True)

    asyncio.create_task(send_postmatch_roast(source="fake"))

@bot.tree.command(name="history", description="Visar Antons kills senaste veckan (syns för alla)")
async def history(interaction: discord.Interaction):
    days = 7
    recs = _read_history(days=days)

    if not recs:
        return await interaction.response.send_message("📉 Inga matchdata sparade ännu.", ephemeral=False)

    # Summering
    kills_list = [int(r["kills"]) for r in recs]
    avg = sum(kills_list) / len(kills_list)
    mn = min(kills_list)
    mx = max(kills_list)

    # Graf per dag (7 punkter)
    daily = _group_by_day(recs, days=days)
    daily_avgs = [int(round(x[1])) if x[1] is not None else 0 for x in daily]
    spark = _sparkline(daily_avgs)

    # Bygg fin text
    lines = []
    lines.append("📊 **Anton kills – senaste 7 dagar**")
    lines.append(f"Matches: **{len(kills_list)}** | Avg: **{avg:.1f}** | Min: **{mn}** | Max: **{mx}**")
    lines.append(f"`{spark}`")
    lines.append("```")
    for d, a, c in daily:
        if c == 0:
            lines.append(f"{d}  -")
        else:
            lines.append(f"{d}  avg {a:.1f}  ({c} match{'es' if c != 1 else ''})")
    lines.append("```")

    await interaction.response.send_message("\n".join(lines), ephemeral=False)

@bot.tree.command(name="stats", description="Visar aggregerad statistik. Ex: /stats eller /stats mirage")
async def stats(interaction: discord.Interaction, map_name: Optional[str] = None, days: int = 30, detail: bool = False):
    """Visa statistik för Anton. `map_name` filtrerar per bana, `days` styr tidsfönster."""
    if days < 1 or days > 365:
        return await interaction.response.send_message("❌ Ange ett antal dagar mellan 1 och 365.", ephemeral=True)

    recs = _read_history(days=days)
    if map_name:
        recs = _filter_by_map(recs, map_name)

    if not recs:
        return await interaction.response.send_message("📉 Inga matchdata för denna förfrågan.", ephemeral=False)

    agg = _aggregate_stats(recs, days)

    lines = []
    title_map = map_name or "alla banor"
    lines.append(f"📊 **Anton statistik — {title_map} — senaste {days} dagar**")
    lines.append(f"Matches: **{agg['matches']}** | Avg kills: **{agg['avg_kills']:.2f}**")

    avgs = agg['avgs']
    if avgs.get('adr') is not None:
        lines.append(f"ADR: **{avgs['adr']:.1f}**")
    if avgs.get('hs_percent') is not None:
        lines.append(f"HS%: **{avgs['hs_percent']:.1f}%**")
    if avgs.get('kd') is not None:
        lines.append(f"K/D: **{avgs['kd']:.2f}**")

    lines.append(f"`{agg['spark']}`")

    # Top matches
    if agg['top']:
        lines.append("\nTop matches:")
        for r in agg['top']:
            dt = r.get('ts')
            k = int(r.get('kills', 0))
            m = r.get('map') or 'unknown'
            s = r.get('stats') or {}
            s_parts = []
            if 'adr' in s:
                s_parts.append(f"ADR {s.get('adr')}")
            if 'hs_percent' in s:
                s_parts.append(f"HS% {s.get('hs_percent')}")
            if 'deaths' in s:
                s_parts.append(f"D {s.get('deaths')}")
            lines.append(f"• {dt} | {m} | **{k} kills** {'| ' + ' | '.join(s_parts) if s_parts else ''}")

    if detail:
        lines.append("\n(Detaljvy aktiverad)")

    await interaction.response.send_message("\n".join(lines), ephemeral=False)

@stats.autocomplete('map_name')
async def stats_map_autocomplete(interaction: discord.Interaction, current: str):
    """Autocompletion för `map_name` i /stats"""
    cur = (current or "").lower()
    choices = []
    if cur == "":
        # visa några populära kartor om inget skrivit ännu
        choices = [app_commands.Choice(name=m, value=m) for m in MAPS[:10]]
    else:
        for m in MAPS:
            if cur in m.lower():
                choices.append(app_commands.Choice(name=m, value=m))
    return choices[:25]

@bot.tree.command(name="help", description="Visar kommandon")
async def help_cmd(interaction: discord.Interaction):
    msg = (
        "🛠️ **Commands**\n"
        "• `/status` – visar status (bara du ser)\n"
        "• `/setkills <tal>` – ändra limit (owner only)\n"
        "(För test: sätt `DEV_MODE=1` i .env för att tillåta owner-kommandon till alla)\n"        "• `/fakekills <kills> [map_name] [when:ISO/epoch] [stats_json]` – simulera matchslut (owner only). `when` format: epoch eller ISO 8601. `stats_json` ex: '{\"deaths\":4,\"adr\":85,\"hs_percent\":45}'\n"
        "• `/stats [map_name] [days]` – aggregerad statistik, valfri bana (autocompletion finns för karta)\n"
        "• `/history` – senaste 7 dagar (syns för alla)\n\n"
        "Botten postar automatiskt i kanalen **endast** när matchen slutar och Anton har ≤ limit."
    )
    await interaction.response.send_message(msg, ephemeral=True)

@bot.tree.command(name="clearhistory", description="Rensa historik (DB + JSONL). Kräver confirm=true — owner only)")
async def clearhistory(interaction: discord.Interaction, confirm: bool = False):
    """Rensa all sparad historik. Detta tar bort alla rader i `anton.db` och tömmer `anton_history.jsonl`.

    Av säkerhetsskäl krävs `confirm=true` för att utföra rensningen.
    """
    if not _owner_only(interaction):
        return await interaction.response.send_message("❌ Owner only.", ephemeral=True)
    if not confirm:
        return await interaction.response.send_message(
            "⚠️ Detta kommer radera ALL match-historik (DB + anton_history.jsonl). Kör kommandot igen med `confirm: true` för att bekräfta.",
            ephemeral=True,
        )

    try:
        # Count before
        rows = _db_query("SELECT COUNT(*) FROM matches", ())
        before = rows[0][0] if rows else 0

        # Backup JSONL if present and truncate
        if os.path.exists(HISTORY_FILE):
            bak = HISTORY_FILE + ".bak"
            try:
                shutil.copyfile(HISTORY_FILE, bak)
            except Exception:
                pass
            try:
                with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                    f.truncate(0)
            except Exception:
                pass

        # Delete DB rows and vacuum
        _db_execute("DELETE FROM matches", ())
        _db_execute("VACUUM", ())

        await interaction.response.send_message(f"✅ Historik rensad. Rader borttagna: {before}. JSONL backad upp till `{HISTORY_FILE}.bak`.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Fel vid rensning: {e}", ephemeral=True)

@setkills.error
async def setkills_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    await interaction.response.send_message(f"❌ Fel: `{type(error).__name__}`", ephemeral=True)

# ====== READY ======
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # Init DB and migrate existing JSONL if needed
    try:
        init_db()
        migrate_jsonl_to_db()
        print("DB initialized and migration (if any) done.")
    except Exception as e:
        print("DB init/migrate error:", repr(e))

    try:
        if TEST_GUILD_ID:
            try:
                await bot.tree.sync(guild=discord.Object(id=int(TEST_GUILD_ID)))
                print(f"Slash commands synced to guild {TEST_GUILD_ID}.")
            except Exception as e:
                print("Guild sync error, falling back to global sync:", repr(e))
                await bot.tree.sync()
                print("Slash commands synced globally.")
        else:
            await bot.tree.sync()
            print("Slash commands synced globally.")
    except Exception as e:
        print("Slash sync error:", repr(e))

    await start_gsi_server()


async def fetch_leetify_api():
    """Penis"""
    url = "https://api-public.cs-prod.leetify.com"

    headers = {
        "Authorization": "Bearer {LEETIFY_TOKEN}"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{url}/v3/profile/matches") as r1:
            r1.raise_for_status()
            matches = await r1.json()

        if not matches:
            print("No matches found")
            return

        match_id = matches[0]["matchId"]

        async with session.get(f"{url}/v2/matches/{match_id}") as r2:
            if r2.status == 200:
                data = await r2.json()
                print(data)

                return data
            else:
                print("Error fetching match:", r2.status)

bot.run(DISCORD_TOKEN)
