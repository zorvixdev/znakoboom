import hashlib
import hmac
import json
import mimetypes
import os
import random
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_DATABASE_PATH = ROOT / "data" / "znakoboom.sqlite3"
LEGACY_DATABASE_PATH = ROOT / "data" / "nomerok.sqlite3"
DATABASE_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(LEGACY_DATABASE_PATH if LEGACY_DATABASE_PATH.exists() and not DEFAULT_DATABASE_PATH.exists() else DEFAULT_DATABASE_PATH),
    )
)
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH

RARITIES = (
    {"id": "обычный", "chance": 81.5, "min": 300, "max": 4_500, "color": "common"},
    {"id": "необычный", "chance": 12, "min": 4_000, "max": 36_000, "color": "uncommon"},
    {"id": "редкий", "chance": 4.5, "min": 36_000, "max": 320_000, "color": "rare"},
    {"id": "эпический", "chance": 1.5, "min": 320_000, "max": 2_000_000, "color": "epic"},
    {"id": "мифический", "chance": 0.45, "min": 2_000_000, "max": 12_000_000, "color": "mythic"},
    {"id": "легендарный", "chance": 0.05, "min": 15_000_000, "max": 50_000_000, "color": "legendary"},
)
COUNTRIES = {
    "ru": {
        "name": "Россия",
        "flag": "🇷🇺",
        "codes": [("77", "Москва"), ("197", "Москва"), ("78", "Санкт-Петербург"), ("66", "Свердловская область"), ("54", "Новосибирская область"), ("16", "Татарстан"), ("25", "Приморский край"), ("65", "Сахалинская область"), ("102", "Республика Башкортостан"), ("23", "Краснодарский край")],
        "letters": "АВЕКМНОРСТУХ",
        "suffix": "RUS",
    },
    "kz": {
        "name": "Казахстан",
        "flag": "🇰🇿",
        "codes": [("02", "Алматы"), ("01", "Астана"), ("17", "Шымкент"), ("05", "Алматинская область"), ("07", "Западно-Казахстанская область")],
        "letters": "ABEKMHOPCTYX",
        "suffix": "KZ",
    },
    "by": {
        "name": "Беларусь",
        "flag": "🇧🇾",
        "codes": [("7", "Минск"), ("1", "Брестская область"), ("2", "Витебская область"), ("5", "Гродненская область"), ("6", "Минская область")],
        "letters": "ABEKMHOPCTYX",
        "suffix": "BY",
    },
}
UPGRADES = {
    "generator": {"name": "Генератор", "base": 30_000, "max": 11, "effect": "Увеличивает шанс редких номеров"},
    "storage": {"name": "Инвентарь", "base": 50_000, "max": 11, "effect": "Больше места для коллекции"},
    "safe": {"name": "Сейф", "base": 75_000, "max": 11, "effect": "Больше защищённых номеров"},
    "showcase": {"name": "Витрина", "base": 100_000, "max": 6, "effect": "Больше номеров на витрине"},
}
PERKS = {
    "lucky": {
        "name": "Нумеролог",
        "icon": "🍀",
        "description": "+20% к шансу редких, мифических и легендарных номеров.",
        "short": "+20% шанс редкости",
    },
    "dealer": {
        "name": "Автодилер",
        "icon": "💸",
        "description": "+15% к выручке от быстрой продажи номеров.",
        "short": "+15% к продаже",
    },
    "mechanic": {
        "name": "Механик",
        "icon": "🔧",
        "description": "+50% опыта за каждый сгенерированный номер.",
        "short": "+50% опыта",
    },
    "archivist": {
        "name": "Архивариус",
        "icon": "🗄️",
        "description": "+10 мест в коллекции и +5 мест в сейфе.",
        "short": "+10 коллекция · +5 сейф",
    },
}
DAILY_REWARDS = [30_000, 50_000, 80_000, 120_000, 200_000, 300_000, 1_000_000]
HALLOWEEN_START = datetime(2026, 10, 1, tzinfo=timezone.utc)
HALLOWEEN_END = datetime(2026, 11, 13, tzinfo=timezone.utc)
HALLOWEEN_REWARDS = {
    "generatorDropChance": 0.22,
    "generatorDropLimit": 10,
    "dailyLogin": 5,
    "activeTimeLimit": 4,
    "activeTimeSeconds": 15 * 60,
    "frameCost": 100,
}
DAILY_ORDERS = (
    {"id": "generate_5", "title": "Первые находки", "description": "Сгенерируй 5 номеров", "target": 5, "progress": "generated", "reward": 15_000},
    {"id": "generate_15", "title": "На волне", "description": "Сгенерируй 15 номеров", "target": 15, "progress": "generated", "reward": 50_000},
    {"id": "fuse_1", "title": "Мастер переплавки", "description": "Переплавь один номер", "target": 1, "progress": "fused", "reward": 30_000},
)
DB_LOCK = threading.Lock()


def connect_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS app_migrations (name TEXT PRIMARY KEY)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            referred_user_id TEXT PRIMARY KEY,
            referrer_user_id TEXT NOT NULL,
            rewarded INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_codes (
            user_id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE
        )
        """
    )
    if DATABASE_PATH.resolve() == DEFAULT_DATABASE_PATH.resolve() and LEGACY_DATABASE_PATH.exists():
        already_imported = connection.execute(
            "SELECT 1 FROM app_migrations WHERE name = 'import_nomerok_profiles'"
        ).fetchone()
        if already_imported:
            return connection
        with sqlite3.connect(LEGACY_DATABASE_PATH, timeout=10) as legacy:
            legacy_rows = legacy.execute(
                "SELECT user_id, username, state, created_at, updated_at FROM players"
            ).fetchall()
        connection.executemany(
            "INSERT OR IGNORE INTO players (user_id, username, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            legacy_rows,
        )
        connection.execute(
            "INSERT INTO app_migrations (name) VALUES ('import_nomerok_profiles')"
        )
    return connection


@contextmanager
def database():
    connection = connect_db()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def new_player():
    return {
        "balance": 650_000,
        "experience": 0,
        "level": 1,
        "totalGenerated": 0,
        "totalSpent": 0,
        "totalEarned": 0,
        "dailyStreak": 0,
        "lastDaily": "",
        "numbers": [],
        "upgrades": {key: 1 for key in UPGRADES},
        "perk": None,
        "country": "ru",
        "region": "any",
        "halloween": default_halloween_state(),
        "dailyOrders": default_daily_orders(),
    }


def level_for_experience(experience):
    level = 1
    remaining = experience
    while level < 50:
        needed = 10 + level * 4
        if remaining < needed:
            break
        remaining -= needed
        level += 1
    return level


def halloween_live(now=None):
    now = now or datetime.now(timezone.utc)
    return HALLOWEEN_START <= now < HALLOWEEN_END


def default_halloween_state():
    return {
        "pumpkins": 0,
        "eventDay": "",
        "generatorToday": 0,
        "dailyBonusDay": "",
        "activeSeconds": 0,
        "activeToday": 0,
        "lastActivityAt": 0,
        "exclusiveFrame": False,
    }


def default_daily_orders():
    return {
        "day": datetime.now(timezone.utc).date().isoformat(),
        "generated": 0,
        "fused": 0,
        "claimed": [],
    }


def normalize_daily_orders(state, now=None):
    orders = state.setdefault("dailyOrders", default_daily_orders())
    today = (now or datetime.now(timezone.utc)).date().isoformat()
    if not isinstance(orders, dict) or orders.get("day") != today:
        orders = default_daily_orders()
        orders["day"] = today
        state["dailyOrders"] = orders
    for key in ("generated", "fused"):
        value = orders.get(key, 0)
        orders[key] = max(0, value) if isinstance(value, int) else 0
    claimed = orders.get("claimed", [])
    valid_ids = {order["id"] for order in DAILY_ORDERS}
    orders["claimed"] = [item for item in claimed if isinstance(item, str) and item in valid_ids] if isinstance(claimed, list) else []
    return orders


def normalize_halloween(state, now=None):
    event = state.setdefault("halloween", default_halloween_state())
    defaults = default_halloween_state()
    for key, value in defaults.items():
        event.setdefault(key, value)
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    if event["eventDay"] != today:
        event["eventDay"] = today
        event["generatorToday"] = 0
        event["activeSeconds"] = 0
        event["activeToday"] = 0
        event["lastActivityAt"] = 0
    event["active"] = halloween_live(now)
    event["pumpkinLimit"] = HALLOWEEN_REWARDS["generatorDropLimit"] + 5 + HALLOWEEN_REWARDS["activeTimeLimit"]
    event["pumpkinGoal"] = HALLOWEEN_REWARDS["frameCost"]
    event["endsAt"] = HALLOWEEN_END.isoformat()
    return event


def number_cap(state):
    perk_bonus = 10 if state.get("perk") == "archivist" else 0
    return 40 + (state["upgrades"]["storage"] - 1) * 10 + perk_bonus


def safe_cap(state):
    perk_bonus = 5 if state.get("perk") == "archivist" else 0
    return 20 + (state["upgrades"]["safe"] - 1) * 5 + perk_bonus


def showcase_cap(state):
    return 3 + (state["upgrades"]["showcase"] - 1) * 2


def upgrade_price(kind, level):
    factor = {"generator": 1, "storage": 1.65, "safe": 2.4, "showcase": 3.2}[kind]
    return int(UPGRADES[kind]["base"] * factor * (1.72 ** (level - 1)))


def pick_rarity(generator_level, perk=None):
    weights = [entry["chance"] for entry in RARITIES]
    shift = min(generator_level - 1, 10) * 0.7
    for index in range(len(weights) - 1):
        transfer = min(shift, weights[index] * 0.12)
        weights[index] -= transfer
        weights[index + 1] += transfer
    if perk == "lucky":
        weights = [weight * (1.2 if index >= 2 else 1) for index, weight in enumerate(weights)]
    target = random.random() * sum(weights)
    for entry, weight in zip(RARITIES, weights):
        target -= weight
        if target <= 0:
            return entry
    return RARITIES[-1]


def make_number(country_code, generator_level, perk=None, region_code=None, rarity_override=None):
    country = COUNTRIES[country_code]
    if region_code is None:
        code, region = random.choice(country["codes"])
    else:
        matches = [entry for entry in country["codes"] if entry[0] == region_code]
        if not matches:
            raise ValueError("Этот регион недоступен для выбранной страны")
        code, region = matches[0]
    rarity = rarity_override or pick_rarity(generator_level, perk)
    if isinstance(rarity, str):
        rarity = next((entry for entry in RARITIES if entry["id"] == rarity), None)
        if rarity is None:
            raise ValueError("Неизвестная редкость номера")
    letters = country["letters"]
    plate = f"{random.choice(letters)}{random.randrange(100, 1000)}{''.join(random.choices(letters, k=2))}"
    formatted = f"{plate} {code}"
    price = random.randint(rarity["min"], rarity["max"])
    return {
        "id": uuid.uuid4().hex[:12],
        "plate": formatted,
        "country": country_code,
        "region": region,
        "regionCode": code,
        "flag": country["flag"],
        "suffix": country["suffix"],
        "rarity": rarity["id"],
        "rarityColor": rarity["color"],
        "price": price,
        "createdAt": int(time.time()),
        "inSafe": False,
        "onShowcase": False,
    }


def normalized_state(state):
    state.setdefault("perk", None)
    state.setdefault("upgrades", {})
    for key in UPGRADES:
        state["upgrades"].setdefault(key, 1)
    state.setdefault("numbers", [])
    state.setdefault("experience", 0)
    state.setdefault("country", "ru")
    if state["country"] not in COUNTRIES:
        state["country"] = "ru"
    valid_regions = {code for code, _ in COUNTRIES[state["country"]]["codes"]}
    if state.get("region", "any") != "any" and state["region"] not in valid_regions:
        state["region"] = "any"
    else:
        state.setdefault("region", "any")
    state["level"] = level_for_experience(state["experience"])
    state["numbers"].sort(key=lambda number: (number["price"], number["createdAt"]), reverse=True)
    event = normalize_halloween(state)
    normalize_daily_orders(state)
    state["regions"] = [
        {"code": code, "name": name}
        for code, name in COUNTRIES[state["country"]]["codes"]
    ]
    state["regionCatalog"] = {
        country_code: [
            {"code": code, "name": name}
            for code, name in details["codes"]
        ]
        for country_code, details in COUNTRIES.items()
    }
    state["halloween"] = event
    state["safeCapacity"] = safe_cap(state)
    state["showcaseCapacity"] = showcase_cap(state)
    state["inventoryCapacity"] = number_cap(state)
    return state


def telegram_user(init_data):
    if not BOT_TOKEN:
        if APP_ENV == "production":
            raise ValueError("Telegram authentication is not configured")
        return "demo", "Гость"
    if not init_data or len(init_data) > 8192:
        raise ValueError("Open this game from its Telegram bot")
    values = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    supplied_hash = values.pop("hash", "")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied_hash):
        raise ValueError("Invalid Telegram signature")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, supplied_hash):
        raise ValueError("Invalid Telegram signature")
    try:
        auth_date = int(values["auth_date"])
        user = json.loads(values["user"])
        user_id = str(user["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Telegram user data") from exc
    now = int(time.time())
    if auth_date > now + 30 or now - auth_date > 86_400:
        raise ValueError("Telegram login expired; reopen the Mini App")
    if not re.fullmatch(r"\d{1,20}", user_id):
        raise ValueError("Invalid Telegram user ID")
    username = str(user.get("first_name", "")).strip()[:80]
    return user_id, username


def require_player(connection, user_id, username):
    now = int(time.time())
    connection.execute(
        "INSERT OR IGNORE INTO players (user_id, username, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, json.dumps(new_player(), ensure_ascii=False), now, now),
    )
    row = connection.execute("SELECT state FROM players WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise RuntimeError("Could not create player state")
    try:
        state = json.loads(row["state"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Player state is corrupt") from exc
    state = normalized_state(state)
    referral = connection.execute(
        "SELECT referrer_user_id FROM referrals WHERE referred_user_id = ? AND rewarded = 0",
        (user_id,),
    ).fetchone()
    if referral:
        reward = 50_000
        state["balance"] += reward
        state["totalEarned"] += reward
        save_player(connection, user_id, username, state)
        referrer_id = referral["referrer_user_id"]
        connection.execute(
            "INSERT OR IGNORE INTO players (user_id, username, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (referrer_id, "Игрок", json.dumps(new_player(), ensure_ascii=False), now, now),
        )
        referrer_row = connection.execute(
            "SELECT username, state FROM players WHERE user_id = ?",
            (referrer_id,),
        ).fetchone()
        if referrer_row is None:
            raise RuntimeError("Could not load referral owner")
        try:
            referrer_state = normalized_state(json.loads(referrer_row["state"]))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Referral owner state is corrupt") from exc
        referrer_state["balance"] += reward
        referrer_state["totalEarned"] += reward
        save_player(connection, referrer_id, referrer_row["username"], referrer_state)
        connection.execute(
            "UPDATE referrals SET rewarded = 1 WHERE referred_user_id = ? AND rewarded = 0",
            (user_id,),
        )
    return state


def save_player(connection, user_id, username, state):
    connection.execute(
        "UPDATE players SET username = ?, state = ?, updated_at = ? WHERE user_id = ?",
        (username, json.dumps(state, ensure_ascii=False), int(time.time()), user_id),
    )


def get_referral_code(user_id):
    with DB_LOCK, database() as connection:
        row = connection.execute(
            "SELECT code FROM referral_codes WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        if row:
            return row["code"]
        code = secrets.token_urlsafe(9)
        connection.execute(
            "INSERT OR IGNORE INTO referral_codes (user_id, code) VALUES (?, ?)",
            (str(user_id), code),
        )
        row = connection.execute(
            "SELECT code FROM referral_codes WHERE user_id = ?",
            (str(user_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError("Could not create referral code")
        return row["code"]


def register_referral(code, referred_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", str(code)) or not re.fullmatch(r"\d{1,20}", str(referred_id)):
        raise ValueError("Некорректный код приглашения")
    with DB_LOCK, database() as connection:
        referrer = connection.execute(
            "SELECT user_id FROM referral_codes WHERE code = ?",
            (str(code),),
        ).fetchone()
        if referrer is None:
            return False
        referrer_id = referrer["user_id"]
        if referrer_id == str(referred_id):
            return False
        existing_player = connection.execute(
            "SELECT 1 FROM players WHERE user_id = ?",
            (str(referred_id),),
        ).fetchone()
        if existing_player:
            return False
        cursor = connection.execute(
            "INSERT OR IGNORE INTO referrals (referred_user_id, referrer_user_id, created_at) VALUES (?, ?, ?)",
            (str(referred_id), referrer_id, int(time.time())),
        )
        return cursor.rowcount == 1
def leaderboard_entries(connection):
    rows = connection.execute(
        "SELECT user_id, username, state FROM players"
    ).fetchall()
    players = []
    for row in rows:
        try:
            state = json.loads(row["state"])
        except (TypeError, json.JSONDecodeError):
            continue
        numbers = state.get("numbers", [])
        if not isinstance(numbers, list):
            numbers = []
        experience = state.get("experience", 0)
        if not isinstance(experience, (int, float)):
            experience = 0
        players.append({
            "name": str(row["username"] or "Игрок")[:40],
            "level": int(state.get("level", 1) or 1),
            "experience": experience,
            "numberCount": len(numbers),
            "collectionValue": sum(
                number.get("price", 0)
                for number in numbers
                if isinstance(number, dict) and isinstance(number.get("price", 0), (int, float))
            ),
            "legendaryCount": sum(
                1 for number in numbers
                if isinstance(number, dict) and number.get("rarity") == "легендарный"
            ),
            "_sortId": row["user_id"],
        })
    players.sort(
        key=lambda player: (
            -player["experience"],
            -player["legendaryCount"],
            -player["numberCount"],
            player["_sortId"],
        )
    )
    return [
        {"rank": index, **{key: value for key, value in player.items() if key != "_sortId"}}
        for index, player in enumerate(players[:50], start=1)
    ]


def perform_action(state, payload):
    action = payload.get("action")
    if action == "tap":
        cost = 3_000
        selected_country = payload.get("country", state["country"])
        if not isinstance(selected_country, str) or selected_country not in COUNTRIES:
            raise ValueError("Выбери доступную страну")
        selected_region = payload.get("region", "any")
        if not isinstance(selected_region, str):
            raise ValueError("Выбери регион из списка")
        if selected_region != "any" and selected_region not in {code for code, _ in COUNTRIES[selected_country]["codes"]}:
            raise ValueError("Этот регион недоступен для выбранной страны")
        if state["balance"] < cost:
            raise ValueError("Не хватает рублей для генерации")
        if len(state["numbers"]) >= number_cap(state):
            raise ValueError("Инвентарь заполнен — продай номер или улучши хранилище")
        state["country"] = selected_country
        halloween = normalize_halloween(state)
        number = make_number(
            selected_country,
            state["upgrades"]["generator"],
            state.get("perk"),
            region_code=None if selected_region == "any" else selected_region,
        )
        state["balance"] -= cost
        state["totalSpent"] += cost
        state["totalGenerated"] += 1
        normalize_daily_orders(state)["generated"] += 1
        state["experience"] += 1.5 if state.get("perk") == "mechanic" else 1
        state["numbers"].append(number)
        pumpkin_earned = 0
        if halloween["active"] and halloween["generatorToday"] < HALLOWEEN_REWARDS["generatorDropLimit"]:
            if random.random() < HALLOWEEN_REWARDS["generatorDropChance"]:
                pumpkin_earned = 1
                halloween["pumpkins"] += pumpkin_earned
                halloween["generatorToday"] += pumpkin_earned
        return {"generated": number, "pumpkinsEarned": pumpkin_earned}
    if action == "country":
        country = payload.get("country")
        if not isinstance(country, str) or country not in COUNTRIES:
            raise ValueError("Выбери доступную страну")
        state["country"] = country
        state["region"] = "any"
        return {}
    if action == "region":
        country = payload.get("country", state["country"])
        region = payload.get("region")
        if not isinstance(country, str) or country not in COUNTRIES:
            raise ValueError("Выбери доступную страну")
        if not isinstance(region, str) or region != "any" and region not in {code for code, _ in COUNTRIES[country]["codes"]}:
            raise ValueError("Выбери доступный регион")
        state["country"] = country
        state["region"] = region
        return {}
    if action == "choose_perk":
        perk = payload.get("perk")
        if not isinstance(perk, str) or perk not in PERKS:
            raise ValueError("Выбери одну из доступных специализаций")
        if state.get("perk"):
            raise ValueError("Специализация уже выбрана — изменить её нельзя")
        state["perk"] = perk
        return {}
    if action == "upgrade":
        kind = payload.get("kind")
        if not isinstance(kind, str) or kind not in UPGRADES:
            raise ValueError("Неизвестное улучшение")
        current = state["upgrades"][kind]
        if current >= UPGRADES[kind]["max"]:
            raise ValueError("Это улучшение уже максимального уровня")
        price = upgrade_price(kind, current)
        if state["balance"] < price:
            raise ValueError("Не хватает рублей для улучшения")
        state["balance"] -= price
        state["totalSpent"] += price
        state["upgrades"][kind] = current + 1
        return {}
    if action == "claim_daily":
        today = datetime.now(timezone.utc).date()
        last_daily = state["lastDaily"]
        if last_daily == today.isoformat():
            raise ValueError("Сегодня награда уже получена — загляни завтра")
        yesterday = (today - timedelta(days=1)).isoformat()
        state["dailyStreak"] = state["dailyStreak"] + 1 if last_daily == yesterday else 1
        reward = DAILY_REWARDS[(state["dailyStreak"] - 1) % len(DAILY_REWARDS)]
        state["balance"] += reward
        state["totalEarned"] += reward
        state["lastDaily"] = today.isoformat()
        halloween = normalize_halloween(state)
        pumpkins_earned = 0
        if halloween["active"] and halloween["dailyBonusDay"] != today.isoformat():
            pumpkins_earned = HALLOWEEN_REWARDS["dailyLogin"]
            halloween["pumpkins"] += pumpkins_earned
            halloween["dailyBonusDay"] = today.isoformat()
        return {"reward": reward, "pumpkinsEarned": pumpkins_earned}
    if action == "claim_event_daily":
        halloween = normalize_halloween(state)
        if not halloween["active"]:
            raise ValueError("Хэллоуин-событие завершено")
        today = datetime.now(timezone.utc).date().isoformat()
        if halloween["dailyBonusDay"] == today:
            raise ValueError("Тыквы за вход уже получены сегодня")
        halloween["dailyBonusDay"] = today
        halloween["pumpkins"] += HALLOWEEN_REWARDS["dailyLogin"]
        return {"pumpkinsEarned": HALLOWEEN_REWARDS["dailyLogin"]}
    if action == "event_activity":
        halloween = normalize_halloween(state)
        if not halloween["active"]:
            raise ValueError("Хэллоуин-событие завершено")
        now = int(time.time())
        previous = halloween["lastActivityAt"]
        if previous and 0 < now - previous <= 120:
            halloween["activeSeconds"] += min(now - previous, 90)
        halloween["lastActivityAt"] = now
        pumpkin_earned = 0
        while (
            halloween["activeSeconds"] >= HALLOWEEN_REWARDS["activeTimeSeconds"]
            and halloween["activeToday"] < HALLOWEEN_REWARDS["activeTimeLimit"]
        ):
            halloween["activeSeconds"] -= HALLOWEEN_REWARDS["activeTimeSeconds"]
            halloween["activeToday"] += 1
            halloween["pumpkins"] += 1
            pumpkin_earned += 1
        return {"pumpkinsEarned": pumpkin_earned}
    if action == "claim_halloween_frame":
        halloween = normalize_halloween(state)
        if not halloween["active"]:
            raise ValueError("Хэллоуин-событие завершено")
        if halloween["exclusiveFrame"]:
            raise ValueError("Эксклюзивная рамка уже получена")
        if halloween["pumpkins"] < HALLOWEEN_REWARDS["frameCost"]:
            raise ValueError("Собери ещё тыквы, чтобы получить рамку")
        halloween["pumpkins"] -= HALLOWEEN_REWARDS["frameCost"]
        halloween["exclusiveFrame"] = True
        return {"frameClaimed": True}
    if action == "claim_order":
        order_id = payload.get("orderId")
        order = next((item for item in DAILY_ORDERS if item["id"] == order_id), None)
        if order is None:
            raise ValueError("Неизвестное задание")
        orders = normalize_daily_orders(state)
        if order_id in orders["claimed"]:
            raise ValueError("Награда за это задание уже получена")
        if orders[order["progress"]] < order["target"]:
            raise ValueError("Сначала выполни задание")
        orders["claimed"].append(order_id)
        state["balance"] += order["reward"]
        state["totalEarned"] += order["reward"]
        return {"orderReward": order["reward"], "orderId": order_id}
    if action == "fuse":
        ids = payload.get("ids")
        if not isinstance(ids, list) or len(ids) != 5:
            raise ValueError("Для переплавки выбери ровно 5 номеров одной редкости")
        ids = {str(value)[:20] for value in ids}
        if len(ids) != 5:
            raise ValueError("Выбери 5 разных номеров")
        selected = [number for number in state["numbers"] if number["id"] in ids]
        if len(selected) != 5:
            raise ValueError("Один из выбранных номеров не найден")
        if any(number["inSafe"] for number in selected):
            raise ValueError("Сначала достань номера из сейфа")
        rarities = [entry["id"] for entry in RARITIES]
        tier_indexes = {rarities.index(number["rarity"]) for number in selected if number.get("rarity") in rarities}
        if len(tier_indexes) != 1 or sum(1 for number in selected if number.get("rarity") in rarities) != 5:
            raise ValueError("Для переплавки нужны 5 номеров одинаковой редкости")
        tier_index = next(iter(tier_indexes))
        if tier_index >= len(RARITIES) - 1:
            raise ValueError("Номер максимальной редкости переплавить нельзя")
        next_tier = RARITIES[tier_index + 1]
        fee = max(1_000, sum(number["price"] for number in selected) // 10)
        if state["balance"] < fee:
            raise ValueError(f"Не хватает игровой валюты на плату за переплавку: {fee:,} ₽".replace(",", " "))
        result_country = selected[0]["country"]
        result_region = selected[0]["regionCode"]
        fused = make_number(
            result_country,
            state["upgrades"]["generator"],
            state.get("perk"),
            region_code=result_region,
            rarity_override=next_tier,
        )
        state["numbers"] = [number for number in state["numbers"] if number["id"] not in ids]
        state["numbers"].append(fused)
        state["balance"] -= fee
        state["totalSpent"] += fee
        state["experience"] += 5
        normalize_daily_orders(state)["fused"] += 1
        return {"fused": fused, "fee": fee}
    if action in ("safe", "showcase", "sell"):
        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids or len(ids) > 100:
            raise ValueError("Выбери номера для этого действия")
        ids = {str(value)[:20] for value in ids}
        selected = [number for number in state["numbers"] if number["id"] in ids]
        if len(selected) != len(ids):
            raise ValueError("Один из выбранных номеров не найден")
        if action == "safe":
            remove_from_safe = all(number["inSafe"] for number in selected)
            if not remove_from_safe:
                room = safe_cap(state) - sum(1 for number in state["numbers"] if number["inSafe"])
                if len([number for number in selected if not number["inSafe"]]) > room:
                    raise ValueError("В сейфе не хватает места — улучши его")
            for number in selected:
                number["inSafe"] = not remove_from_safe
            return {}
        if action == "showcase":
            remove_from_showcase = all(number["onShowcase"] for number in selected)
            if not remove_from_showcase:
                room = showcase_cap(state) - sum(1 for number in state["numbers"] if number["onShowcase"])
                if len([number for number in selected if not number["onShowcase"]]) > room:
                    raise ValueError("На витрине не хватает места — улучши её")
            for number in selected:
                number["onShowcase"] = not remove_from_showcase
            return {}
        if any(number["inSafe"] for number in selected):
            raise ValueError("Сначала достань номера из сейфа")
        state["numbers"] = [number for number in state["numbers"] if number["id"] not in ids]
        multiplier = 1.15 if state.get("perk") == "dealer" else 1
        earnings = int(sum(number["price"] for number in selected) * multiplier)
        state["balance"] += earnings
        state["totalEarned"] += earnings
        return {"earned": earnings}
    raise ValueError("Неизвестное действие")


class GameHandler(BaseHTTPRequestHandler):
    server_version = "Znakoboom/1.0"

    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request size") from exc
        if length <= 0 or length > 16_384:
            raise ValueError("Request body must be under 16 KB")
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        return body

    def authenticate(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("tma "):
            if not BOT_TOKEN and APP_ENV != "production":
                return "demo", "Гость"
            raise ValueError("Open this game from its Telegram bot")
        return telegram_user(authorization[4:])

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self.send_json(200, {"ok": True, "mode": APP_ENV})
            return
        if path == "/api/state":
            try:
                user_id, username = self.authenticate()
                with DB_LOCK, database() as connection:
                    state = require_player(connection, user_id, username)
                    referral_count = connection.execute(
                        "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ? AND rewarded = 1",
                        (user_id,),
                    ).fetchone()[0]
                referral_url = (
                    f"https://t.me/{BOT_USERNAME}?start=ref_{get_referral_code(user_id)}"
                    if BOT_USERNAME
                    else ""
                )
                self.send_json(200, {
                    "state": state,
                    "user": {
                        "name": username,
                        "referralUrl": referral_url,
                        "referralCount": referral_count,
                    },
                })
            except ValueError as exc:
                self.send_json(401, {"error": str(exc)})
            except (OSError, sqlite3.Error, RuntimeError) as exc:
                print(f"State request failed: {exc}", flush=True)
                self.send_json(500, {"error": "Не удалось загрузить прогресс"})
            return
        if path == "/api/leaderboard":
            try:
                self.authenticate()
                with DB_LOCK, database() as connection:
                    players = leaderboard_entries(connection)
                self.send_json(200, {"players": players})
            except ValueError as exc:
                self.send_json(401, {"error": str(exc)})
            except (OSError, sqlite3.Error, RuntimeError) as exc:
                print(f"Leaderboard request failed: {exc}", flush=True)
                self.send_json(500, {"error": "Не удалось загрузить таблицу лидеров"})
            return
        self.serve_file(path)

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/action":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            payload = self.read_json()
            user_id, username = self.authenticate()
            with DB_LOCK, database() as connection:
                connection.execute("BEGIN IMMEDIATE")
                state = require_player(connection, user_id, username)
                result = perform_action(state, payload)
                state = normalized_state(state)
                save_player(connection, user_id, username, state)
                response = {"state": state, **result}
            self.send_json(200, response)
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except (OSError, sqlite3.Error, RuntimeError) as exc:
            print(f"Action request failed: {exc}", flush=True)
            self.send_json(500, {"error": "Не удалось сохранить прогресс"})

    def serve_file(self, request_path):
        try:
            relative = unquote(request_path).lstrip("/") or "index.html"
            file_path = (WEB_ROOT / relative).resolve()
            file_path.relative_to(WEB_ROOT.resolve())
            if not file_path.is_file():
                raise FileNotFoundError(relative)
            content = file_path.read_bytes()
        except (OSError, ValueError):
            self.send_error(404, "Not found")
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache" if file_path.name == "index.html" else "public, max-age=300")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}", flush=True)


def main():
    if APP_ENV == "production" and not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is required when APP_ENV=production")
    if not WEB_ROOT.is_dir():
        raise SystemExit(f"Web app folder not found: {WEB_ROOT}")
    server = ThreadingHTTPServer((HOST, PORT), GameHandler)
    print(f"Знакобум server listening on http://{HOST}:{PORT} ({APP_ENV})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
