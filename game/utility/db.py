import sqlite3
import threading


class Database:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, path='city_sim.db'):
        self.path = path
        # allow use from different threads / async tasks
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self._conn.row_factory = sqlite3.Row
        # enable WAL for better concurrency
        try:
            self._conn.execute('PRAGMA journal_mode=WAL;')
            self._conn.execute('PRAGMA synchronous=NORMAL;')
        except Exception:
            pass
        self._lock2 = threading.Lock()
        self.init_db()

    @classmethod
    def instance(cls, path='city_sim.db'):
        with cls._lock:
            if cls._instance is None:
                cls._instance = Database(path)
            return cls._instance

    def init_db(self):
        with self._lock2:
            cur = self._conn.cursor()
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                is_npc INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                troops INTEGER DEFAULT 0,
                population INTEGER DEFAULT 0,
                max_population INTEGER DEFAULT 100,
                max_troops INTEGER DEFAULT 500,
                defense_bonus REAL DEFAULT 1.0,
                defense_buff REAL DEFAULT 1.0,
                personality TEXT DEFAULT NULL,
                last_diplomacy REAL DEFAULT 0,
                last_active REAL DEFAULT (strftime('%s','now')),
                attack_bonus REAL DEFAULT 1.0,
                prestige INTEGER DEFAULT 0,
                last_prestige_update REAL DEFAULT 0,
                spies INTEGER DEFAULT 0,
                trait_greed REAL DEFAULT 1.0,
                trait_risk REAL DEFAULT 1.0,
                city_phase TEXT DEFAULT 'early'
            );

            CREATE TABLE IF NOT EXISTS wars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_id INTEGER,
                defender_id INTEGER,
                status TEXT DEFAULT 'active',
                started_at INTEGER DEFAULT (strftime('%s', 'now')),
                ended_at INTEGER,
                FOREIGN KEY(attacker_id) REFERENCES players(id),
                FOREIGN KEY(defender_id) REFERENCES players(id)
            );

            CREATE TABLE IF NOT EXISTS attacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker_name TEXT,
                defender_name TEXT,
                troops_sent INTEGER,
                defender_troops INTEGER DEFAULT 0,
                attacker_losses INTEGER DEFAULT 0,
                defender_losses INTEGER DEFAULT 0,
                loot_amount INTEGER DEFAULT 0,
                loot_resource TEXT DEFAULT NULL,
                start_time INTEGER,
                status TEXT DEFAULT 'pending',
                result TEXT DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                troops INTEGER NOT NULL,
                start_time INTEGER NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS buildings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                building_name TEXT NOT NULL,
                level INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS building_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                building_name TEXT NOT NULL,
                start_time INTEGER NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                message TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS npc_traits (
                name TEXT PRIMARY KEY,
                attack_chance REAL DEFAULT 0.3,
                build_chance REAL DEFAULT 0.3,
                peace_chance REAL DEFAULT 0.3,
                last_update REAL DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS prestige_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player TEXT NOT NULL,
                prestige INTEGER NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS espionage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attacker TEXT NOT NULL,
                target TEXT NOT NULL,
                action TEXT NOT NULL,           -- scout | steal | sabotage
                start_time REAL NOT NULL,
                processed INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS intel_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                target TEXT NOT NULL,
                report TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS spy_training (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player TEXT NOT NULL,
                amount INTEGER NOT NULL,
                start_time REAL NOT NULL,
                processed INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS player_resources (
                player_id INTEGER NOT NULL,
                resource_name TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (player_id, resource_name)
            );
            CREATE TABLE IF NOT EXISTS global_market (
                resource_name TEXT PRIMARY KEY,
                supply REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                npc_name TEXT NOT NULL,
                resource TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                total_value REAL NOT NULL,
                profit REAL NOT NULL,
                action TEXT CHECK(action IN ('buy','sell')) NOT NULL,
                timestamp REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS trade_summary (
                npc_name TEXT PRIMARY KEY,
                total_trades INTEGER DEFAULT 0,
                total_profit REAL DEFAULT 0,
                avg_profit REAL DEFAULT 0,
                best_trade REAL DEFAULT 0,
                worst_trade REAL DEFAULT 0,
                last_update REAL DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS npc_trade_stats (
                npc_name TEXT PRIMARY KEY,
                total_profit REAL DEFAULT 0,
                trades INTEGER DEFAULT 0,
                prestige REAL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS npc_cycles (
                npc_id INTEGER PRIMARY KEY,
                awake INTEGER DEFAULT 1,                -- 1 = active, 0 = sleeping
                ticks_awake INTEGER DEFAULT 0,          -- how many ticks awake so far
                ticks_asleep INTEGER DEFAULT 0,         -- how many ticks asleep so far
                next_wake_tick INTEGER DEFAULT 0,       -- optional deterministic wake-up
                active_duration INTEGER DEFAULT 5,      -- how long current active phase lasts (ticks)
                sleep_duration INTEGER DEFAULT 5,       -- how long current sleep phase lasts (ticks)
                last_state_change REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY(npc_id) REFERENCES players(id)
            );
            """)
            cur.close()

    def execute(self, sql, params=(), fetchone=False, fetchall=False):
        with self._lock2:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            if fetchone:
                rv = cur.fetchone()
                cur.close()
                return rv
            if fetchall:
                rv = cur.fetchall()
                cur.close()
                return rv
            return cur

    def close(self):
        with self._lock2:
            try:
                self._conn.close()
            except Exception:
                pass
