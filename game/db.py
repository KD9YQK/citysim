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
                resources INTEGER DEFAULT 0,
                population INTEGER DEFAULT 0,
                max_population INTEGER DEFAULT 100,
                max_troops INTEGER DEFAULT 500,
                defense_bonus REAL DEFAULT 1.0,
                defense_attack_bonus REAL DEFAULT 0.0,
                defense_buff REAL DEFAULT 1.0,
                defense_attack_buff REAL DEFAULT 1.0,
                personality TEXT DEFAULT NULL,
                last_diplomacy REAL DEFAULT 0,
                last_active REAL DEFAULT (strftime('%s','now')),
                attack_bonus REAL DEFAULT 1.0,
                prestige INTEGER DEFAULT 0,
                last_prestige_update REAL DEFAULT 0,
                spies INTEGER DEFAULT 0
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
