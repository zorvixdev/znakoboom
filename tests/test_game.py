import hashlib
import hmac
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from unittest.mock import patch

import server


class GameTests(unittest.TestCase):
    def setUp(self):
        self.previous_token = server.BOT_TOKEN
        self.previous_environment = server.APP_ENV
        self.previous_database_path = server.DATABASE_PATH
        self.previous_default_database_path = server.DEFAULT_DATABASE_PATH
        self.previous_legacy_database_path = server.LEGACY_DATABASE_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        server.DATABASE_PATH = server.Path(self.temp_dir.name) / "game.sqlite3"

    def tearDown(self):
        server.BOT_TOKEN = self.previous_token
        server.APP_ENV = self.previous_environment
        server.DATABASE_PATH = self.previous_database_path
        server.DEFAULT_DATABASE_PATH = self.previous_default_database_path
        server.LEGACY_DATABASE_PATH = self.previous_legacy_database_path
        self.temp_dir.cleanup()

    def test_generator_spends_currency_and_adds_number_and_experience(self):
        state = server.new_player()
        with patch.object(server.random, "random", return_value=0.0):
            result = server.perform_action(state, {"action": "tap"})
        self.assertEqual(state["balance"], 647_000)
        self.assertEqual(state["totalGenerated"], 1)
        self.assertEqual(state["experience"], 1)
        self.assertEqual(state["level"], 1)
        self.assertEqual(state["numbers"][0], result["generated"])
        self.assertEqual(result["generated"]["country"], "ru")

    def test_generator_cannot_spend_more_than_available_balance(self):
        state = server.new_player()
        state["balance"] = 0
        with self.assertRaisesRegex(ValueError, "Не хватает"):
            server.perform_action(state, {"action": "tap"})
        self.assertEqual(state["totalGenerated"], 0)

    def test_tap_uses_the_selected_country_and_exact_region(self):
        state = server.new_player()
        server.perform_action(state, {"action": "region", "country": "ru", "region": "23"})
        with patch.object(server, "halloween_live", return_value=False):
            result = server.perform_action(
                state,
                {"action": "tap", "country": "ru", "region": "23"},
            )
        self.assertEqual(result["generated"]["regionCode"], "23")
        self.assertEqual(result["generated"]["region"], "Краснодарский край")

    def test_tap_rejects_region_not_in_selected_country(self):
        state = server.new_player()
        with self.assertRaisesRegex(ValueError, "недоступен"):
            server.perform_action(
                state,
                {"action": "tap", "country": "kz", "region": "23"},
            )

    def test_legendary_is_the_rarest_and_most_valuable_rarity(self):
        self.assertEqual([entry["id"] for entry in server.RARITIES][-2:], ["мифический", "легендарный"])
        mythic = server.RARITIES[-2]
        legendary = server.RARITIES[-1]
        self.assertLess(legendary["chance"], mythic["chance"])
        self.assertGreater(legendary["min"], mythic["max"])
        self.assertGreater(legendary["max"], mythic["max"])

    def test_lucky_specialization_improves_the_top_rarity(self):
        with patch.object(server.random, "random", return_value=0.99945):
            self.assertEqual(server.pick_rarity(1)["id"], "мифический")
            self.assertEqual(server.pick_rarity(1, "lucky")["id"], "легендарный")

    def test_two_additional_russian_regions_are_available(self):
        codes = {code: region for code, region in server.COUNTRIES["ru"]["codes"]}
        self.assertEqual(codes["102"], "Республика Башкортостан")
        self.assertEqual(codes["23"], "Краснодарский край")
        self.assertEqual(len(server.normalized_state(server.new_player())["regionCatalog"]["kz"]), 5)

    def test_specializations_apply_their_personal_bonuses(self):
        collector = server.new_player()
        server.perform_action(collector, {"action": "choose_perk", "perk": "archivist"})
        self.assertEqual(server.number_cap(collector), 50)
        self.assertEqual(server.safe_cap(collector), 25)
        with self.assertRaisesRegex(ValueError, "уже выбрана"):
            server.perform_action(collector, {"action": "choose_perk", "perk": "lucky"})

        mechanic = server.new_player()
        server.perform_action(mechanic, {"action": "choose_perk", "perk": "mechanic"})
        with patch.object(server.random, "random", return_value=0.0):
            server.perform_action(mechanic, {"action": "tap"})
        self.assertEqual(mechanic["experience"], 1.5)

        dealer = server.new_player()
        server.perform_action(dealer, {"action": "choose_perk", "perk": "dealer"})
        number = server.make_number("ru", 1)
        dealer["numbers"] = [number]
        result = server.perform_action(dealer, {"action": "sell", "ids": [number["id"]]})
        self.assertEqual(result["earned"], int(number["price"] * 1.15))

    def test_halloween_generator_drops_pumpkins_with_daily_cap(self):
        state = server.new_player()
        state["halloween"]["generatorToday"] = 9
        state["halloween"]["eventDay"] = server.datetime.now(server.timezone.utc).date().isoformat()
        with patch.object(server, "halloween_live", return_value=True), patch.object(server.random, "random", return_value=0.0):
            result = server.perform_action(state, {"action": "tap", "country": "ru", "region": "any"})
        self.assertEqual(result["pumpkinsEarned"], 1)
        self.assertEqual(state["halloween"]["pumpkins"], 1)
        self.assertEqual(state["halloween"]["generatorToday"], 10)

        with patch.object(server, "halloween_live", return_value=True), patch.object(server.random, "random", return_value=0.0):
            next_result = server.perform_action(state, {"action": "tap", "country": "ru", "region": "any"})
        self.assertEqual(next_result["pumpkinsEarned"], 0)
        self.assertEqual(state["halloween"]["pumpkins"], 1)

    def test_halloween_login_pumpkins_are_only_claimed_once_per_day(self):
        state = server.new_player()
        with patch.object(server, "halloween_live", return_value=True):
            result = server.perform_action(state, {"action": "claim_event_daily"})
            self.assertEqual(result["pumpkinsEarned"], 5)
            with self.assertRaisesRegex(ValueError, "уже получены"):
                server.perform_action(state, {"action": "claim_event_daily"})

    def test_daily_reward_and_event_login_cannot_double_claim_pumpkins(self):
        state = server.new_player()
        with patch.object(server, "halloween_live", return_value=True):
            result = server.perform_action(state, {"action": "claim_daily"})
            self.assertEqual(result["pumpkinsEarned"], 5)
            with self.assertRaisesRegex(ValueError, "уже получены"):
                server.perform_action(state, {"action": "claim_event_daily"})
            self.assertEqual(state["halloween"]["pumpkins"], 5)

    def test_halloween_activity_rewards_only_active_time_and_caps_daily_pumpkins(self):
        state = server.new_player()
        state["halloween"]["activeToday"] = 3
        state["halloween"]["activeSeconds"] = 840
        state["halloween"]["eventDay"] = server.datetime.now(server.timezone.utc).date().isoformat()
        with patch.object(server, "halloween_live", return_value=True), patch.object(server.time, "time", return_value=2000):
            server.perform_action(state, {"action": "event_activity"})
        with patch.object(server, "halloween_live", return_value=True), patch.object(server.time, "time", return_value=2060):
            result = server.perform_action(state, {"action": "event_activity"})
        self.assertEqual(result["pumpkinsEarned"], 1)
        self.assertEqual(state["halloween"]["activeToday"], 4)
        self.assertEqual(state["halloween"]["pumpkins"], 1)

    def test_halloween_exclusive_frame_requires_and_spends_one_hundred_pumpkins(self):
        state = server.new_player()
        with patch.object(server, "halloween_live", return_value=True):
            with self.assertRaisesRegex(ValueError, "Собери ещё"):
                server.perform_action(state, {"action": "claim_halloween_frame"})
            state["halloween"]["pumpkins"] = 100
            result = server.perform_action(state, {"action": "claim_halloween_frame"})
            self.assertTrue(result["frameClaimed"])
            self.assertTrue(state["halloween"]["exclusiveFrame"])
            self.assertEqual(state["halloween"]["pumpkins"], 0)

    def test_daily_orders_track_progress_and_award_currency_once(self):
        state = server.new_player()
        with patch.object(server, "halloween_live", return_value=False):
            for _ in range(5):
                server.perform_action(state, {"action": "tap"})
        self.assertEqual(state["dailyOrders"]["generated"], 5)
        old_balance = state["balance"]
        result = server.perform_action(state, {"action": "claim_order", "orderId": "generate_5"})
        self.assertEqual(result["orderReward"], 15_000)
        self.assertEqual(state["balance"], old_balance + 15_000)
        with self.assertRaisesRegex(ValueError, "уже получена"):
            server.perform_action(state, {"action": "claim_order", "orderId": "generate_5"})
        with self.assertRaisesRegex(ValueError, "Неизвестное"):
            server.perform_action(state, {"action": "claim_order", "orderId": "not-a-task"})

    def test_daily_orders_reset_on_utc_day_change(self):
        state = server.new_player()
        previous_day = server.datetime(2026, 10, 19, tzinfo=server.timezone.utc)
        server.normalize_daily_orders(state, previous_day)
        state["dailyOrders"]["generated"] = 15
        state["dailyOrders"]["claimed"] = ["generate_5"]
        today = server.datetime(2026, 10, 20, tzinfo=server.timezone.utc)
        orders = server.normalize_daily_orders(state, today)
        self.assertEqual(orders["generated"], 0)
        self.assertEqual(orders["claimed"], [])

    def test_furnace_consumes_five_same_rarity_numbers_for_one_higher_tier(self):
        state = server.new_player()
        originals = [server.make_number("ru", 1, rarity_override="обычный") for _ in range(5)]
        state["numbers"] = originals
        old_balance = state["balance"]
        old_experience = state["experience"]
        result = server.perform_action(state, {"action": "fuse", "ids": [number["id"] for number in originals]})
        self.assertEqual(result["fused"]["rarity"], "необычный")
        self.assertEqual(result["fused"]["regionCode"], originals[0]["regionCode"])
        self.assertEqual(len(state["numbers"]), 1)
        self.assertEqual(state["numbers"][0]["id"], result["fused"]["id"])
        self.assertEqual(state["balance"], old_balance - result["fee"])
        self.assertEqual(state["totalSpent"], result["fee"])
        self.assertEqual(state["experience"], old_experience + 5)

    def test_furnace_rejects_mixed_rarity_and_safe_numbers(self):
        state = server.new_player()
        numbers = [server.make_number("ru", 1, rarity_override="обычный") for _ in range(4)]
        numbers.append(server.make_number("ru", 1, rarity_override="необычный"))
        state["numbers"] = numbers
        with self.assertRaisesRegex(ValueError, "одинаковой редкости"):
            server.perform_action(state, {"action": "fuse", "ids": [number["id"] for number in numbers]})

        numbers[-1]["rarity"] = "обычный"
        numbers[-1]["inSafe"] = True
        with self.assertRaisesRegex(ValueError, "сейфа"):
            server.perform_action(state, {"action": "fuse", "ids": [number["id"] for number in numbers]})

    def test_furnace_rejects_top_rarity_and_wrong_number_of_inputs(self):
        state = server.new_player()
        legendary = [server.make_number("ru", 1, rarity_override="легендарный") for _ in range(5)]
        state["numbers"] = legendary
        with self.assertRaisesRegex(ValueError, "максимальной"):
            server.perform_action(state, {"action": "fuse", "ids": [number["id"] for number in legendary]})
        with self.assertRaisesRegex(ValueError, "ровно 5"):
            server.perform_action(state, {"action": "fuse", "ids": [number["id"] for number in legendary[:4]]})

    def test_existing_player_state_migrates_with_default_specialization(self):
        legacy = server.new_player()
        legacy.pop("perk")
        legacy["upgrades"].pop("safe")
        migrated = server.normalized_state(legacy)
        self.assertIsNone(migrated["perk"])
        self.assertEqual(migrated["upgrades"]["safe"], 1)

    def test_referral_rewards_both_players_only_once_after_first_open(self):
        with server.database() as connection:
            referrer = server.require_player(connection, "101", "Пригласивший")
        self.assertEqual(referrer["balance"], 650_000)
        invite_code = server.get_referral_code("101")
        self.assertTrue(server.register_referral(invite_code, "202"))
        self.assertFalse(server.register_referral(invite_code, "202"))
        self.assertFalse(server.register_referral(invite_code, "101"))

        with server.database() as connection:
            invited = server.require_player(connection, "202", "Новый игрок")
        self.assertEqual(invited["balance"], 700_000)
        self.assertEqual(invited["totalEarned"], 50_000)

        with server.database() as connection:
            server.require_player(connection, "202", "Новый игрок")
            referrer = server.require_player(connection, "101", "Пригласивший")
            saved_name = connection.execute(
                "SELECT username FROM players WHERE user_id = ?",
                ("101",),
            ).fetchone()["username"]
        self.assertEqual(referrer["balance"], 700_000)
        self.assertEqual(referrer["totalEarned"], 50_000)
        self.assertEqual(saved_name, "Пригласивший")

    def test_existing_player_cannot_be_attributed_to_a_later_referral(self):
        with server.database() as connection:
            server.require_player(connection, "303", "Уже игрок")
        invite_code = server.get_referral_code("101")
        self.assertFalse(server.register_referral(invite_code, "303"))

    def test_legacy_database_import_preserves_newer_profiles_and_imports_others(self):
        folder = server.Path(self.temp_dir.name)
        server.DEFAULT_DATABASE_PATH = folder / "new.sqlite3"
        server.LEGACY_DATABASE_PATH = folder / "old.sqlite3"
        server.DATABASE_PATH = server.DEFAULT_DATABASE_PATH
        with sqlite3.connect(server.DEFAULT_DATABASE_PATH) as connection:
            connection.execute(
                "CREATE TABLE players (user_id TEXT PRIMARY KEY, username TEXT NOT NULL, state TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO players VALUES (?, ?, ?, ?, ?)",
                ("demo", "Guest", json.dumps({"balance": 500}), 1, 20),
            )
        with sqlite3.connect(server.LEGACY_DATABASE_PATH) as connection:
            connection.execute(
                "CREATE TABLE players (user_id TEXT PRIMARY KEY, username TEXT NOT NULL, state TEXT NOT NULL, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO players VALUES (?, ?, ?, ?, ?)",
                [
                    ("demo", "Guest", json.dumps({"balance": 300}), 1, 10),
                    ("returning", "Player", json.dumps({"balance": 200}), 2, 9),
                ],
            )

        with server.database() as connection:
            rows = {
                row["user_id"]: json.loads(row["state"])
                for row in connection.execute("SELECT user_id, state FROM players")
            }
        self.assertEqual(rows["demo"]["balance"], 500)
        self.assertEqual(rows["returning"]["balance"], 200)

    def test_safe_protects_numbers_from_sale(self):
        state = server.new_player()
        number = server.make_number("ru", 1)
        state["numbers"] = [number]
        server.perform_action(state, {"action": "safe", "ids": [number["id"]]})
        self.assertTrue(number["inSafe"])
        with self.assertRaisesRegex(ValueError, "сейфа"):
            server.perform_action(state, {"action": "sell", "ids": [number["id"]]})
        server.perform_action(state, {"action": "safe", "ids": [number["id"]]})
        result = server.perform_action(state, {"action": "sell", "ids": [number["id"]]})
        self.assertEqual(result["earned"], number["price"])
        self.assertEqual(state["numbers"], [])

    def test_daily_reward_can_only_be_claimed_once_each_day(self):
        state = server.new_player()
        result = server.perform_action(state, {"action": "claim_daily"})
        self.assertEqual(result["reward"], server.DAILY_REWARDS[0])
        self.assertEqual(state["dailyStreak"], 1)
        with self.assertRaisesRegex(ValueError, "уже получена"):
            server.perform_action(state, {"action": "claim_daily"})

    def test_upgrade_debits_balance_and_increases_level(self):
        state = server.new_player()
        price = server.upgrade_price("storage", 1)
        server.perform_action(state, {"action": "upgrade", "kind": "storage"})
        self.assertEqual(state["upgrades"]["storage"], 2)
        self.assertEqual(state["balance"], 650_000 - price)
        self.assertEqual(server.number_cap(state), 50)

    def test_invalid_telegram_signature_is_rejected(self):
        server.BOT_TOKEN = "test-token"
        server.APP_ENV = "production"
        with self.assertRaisesRegex(ValueError, "Invalid Telegram signature"):
            server.telegram_user("auth_date=1&hash=0000000000000000000000000000000000000000000000000000000000000000")

    def test_valid_and_expired_telegram_init_data(self):
        server.BOT_TOKEN = "test-token"
        server.APP_ENV = "production"
        params = {
            "auth_date": str(int(time.time())),
            "query_id": "query",
            "user": json.dumps({"id": 12345, "first_name": "Игрок"}, ensure_ascii=False),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
        secret = hmac.new(b"WebAppData", server.BOT_TOKEN.encode(), hashlib.sha256).digest()
        params["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        init_data = urlencode(params)
        self.assertEqual(server.telegram_user(init_data), ("12345", "Игрок"))

        params["auth_date"] = str(int(time.time()) - 86_401)
        check_string = "\n".join(f"{key}={value}" for key, value in sorted({key: value for key, value in params.items() if key != "hash"}.items()))
        params["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(ValueError, "expired"):
            server.telegram_user(urlencode(params))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.previous_token = server.BOT_TOKEN
        self.previous_environment = server.APP_ENV
        self.previous_bot_username = server.BOT_USERNAME
        self.previous_database_path = server.DATABASE_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        server.DATABASE_PATH = server.Path(self.temp_dir.name) / "game.sqlite3"
        server.BOT_TOKEN = ""
        server.APP_ENV = "development"
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.GameHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.BOT_TOKEN = self.previous_token
        server.APP_ENV = self.previous_environment
        server.BOT_USERNAME = self.previous_bot_username
        server.DATABASE_PATH = self.previous_database_path
        self.temp_dir.cleanup()

    def test_static_app_and_demo_progress_are_served(self):
        with urlopen(f"{self.base_url}/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Знакобум".encode("utf-8"), response.read())

        with urlopen(f"{self.base_url}/app.js") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"initData", response.read())

        with urlopen(f"{self.base_url}/api/state") as response:
            initial = json.loads(response.read())["state"]
        self.assertEqual(initial["balance"], 650_000)

        request = Request(
            f"{self.base_url}/api/action",
            data=json.dumps({"action": "tap"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.loads(response.read())
        self.assertEqual(result["state"]["balance"], 647_000)
        self.assertEqual(len(result["state"]["numbers"]), 1)

    def test_leaderboard_endpoint_returns_ranked_profiles(self):
        with server.database() as connection:
            first = server.require_player(connection, "player-1", "Игрок 1")
            first["experience"] = 20
            server.save_player(connection, "player-1", "Игрок 1", first)
            second = server.require_player(connection, "player-2", "Игрок 2")
            second["experience"] = 10
            server.save_player(connection, "player-2", "Игрок 2", second)
        with urlopen(f"{self.base_url}/api/leaderboard") as response:
            players = json.loads(response.read())["players"]
        self.assertEqual([player["name"] for player in players[:2]], ["Игрок 1", "Игрок 2"])
        self.assertEqual([player["rank"] for player in players[:2]], [1, 2])

    def test_state_exposes_configured_referral_link_and_count(self):
        server.BOT_USERNAME = "znakoboom_test_bot"
        with urlopen(f"{self.base_url}/api/state") as response:
            user = json.loads(response.read())["user"]
        self.assertRegex(user["referralUrl"], r"^https://t\.me/znakoboom_test_bot\?start=ref_[A-Za-z0-9_-]{8,32}$")
        self.assertNotIn("demo", user["referralUrl"])
        self.assertEqual(user["referralCount"], 0)

    def test_production_rejects_missing_telegram_authentication(self):
        server.APP_ENV = "production"
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/api/state")
        self.assertEqual(context.exception.code, 401)
        error = json.loads(context.exception.read())
        self.assertIn("Telegram bot", error["error"])

    def test_signed_telegram_player_can_persist_progress_in_production(self):
        server.APP_ENV = "production"
        server.BOT_TOKEN = "integration-test-token"
        params = {
            "auth_date": str(int(time.time())),
            "query_id": "integration-test",
            "user": json.dumps({"id": 54321, "first_name": "Игрок"}, ensure_ascii=False),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
        secret = hmac.new(b"WebAppData", server.BOT_TOKEN.encode(), hashlib.sha256).digest()
        params["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        headers = {"Authorization": f"tma {urlencode(params)}"}

        with urlopen(Request(f"{self.base_url}/api/state", headers=headers)) as response:
            initial = json.loads(response.read())
        self.assertEqual(initial["user"]["name"], "Игрок")
        self.assertIsNone(initial["state"]["perk"])

        with urlopen(Request(
            f"{self.base_url}/api/action",
            data=json.dumps({"action": "choose_perk", "perk": "mechanic"}).encode(),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )) as response:
            chosen = json.loads(response.read())
        self.assertEqual(chosen["state"]["perk"], "mechanic")

        with urlopen(Request(
            f"{self.base_url}/api/action",
            data=json.dumps({"action": "tap"}).encode(),
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )) as response:
            self.assertEqual(json.loads(response.read())["state"]["balance"], 647_000)
        with urlopen(Request(f"{self.base_url}/api/state", headers=headers)) as response:
            state = json.loads(response.read())["state"]
        self.assertEqual(state["perk"], "mechanic")
        self.assertEqual(state["totalGenerated"], 1)
        self.assertEqual(state["experience"], 1.5)
        self.assertEqual(len(state["numbers"]), 1)


if __name__ == "__main__":
    unittest.main()
