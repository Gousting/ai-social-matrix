"""
数据库工具模块
管理三个SQLite数据库：
  - raw_notes.db   选题库（采集到的爆款笔记）
  - publish_log.db 发布日志
  - metrics.db     互动数据指标
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from .config_loader import config


class DatabaseManager:
    """数据库管理器"""

    def __init__(self):
        self._raw_notes_db = config.get_path("raw_notes_db")
        self._publish_log_db = config.get_path("publish_log_db")
        self._metrics_db = config.get_path("metrics_db")
        self._init_all_databases()

    @contextmanager
    def _get_conn(self, db_path: str):
        """获取数据库连接（上下文管理器，自动提交和关闭）"""
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_all_databases(self):
        """初始化所有数据库表结构"""
        self._init_raw_notes_db()
        self._init_publish_log_db()
        self._init_metrics_db()

    # ============================================
    # 选题库 (raw_notes.db)
    # ============================================
    def _init_raw_notes_db(self):
        """初始化选题库表结构"""
        with self._get_conn(self._raw_notes_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS raw_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id TEXT UNIQUE,
                    platform TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    author TEXT,
                    author_followers INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    favorites INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    publish_time TEXT,
                    collect_time TEXT,
                    url TEXT,
                    tags TEXT,
                    heat_score REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    used_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_notes_platform ON raw_notes(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_notes_heat ON raw_notes(heat_score DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_notes_status ON raw_notes(status)")

    def insert_raw_note(self, note: Dict) -> bool:
        """插入一条选题笔记（已存在则更新热度分）"""
        try:
            with self._get_conn(self._raw_notes_db) as conn:
                existing = conn.execute(
                    "SELECT id, used_count FROM raw_notes WHERE note_id = ?",
                    (note.get("note_id"),)
                ).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE raw_notes SET
                            likes=?, favorites=?, comments=?, shares=?,
                            heat_score=?, collect_time=?
                        WHERE note_id=?
                    """, (
                        note.get("likes", 0), note.get("favorites", 0),
                        note.get("comments", 0), note.get("shares", 0),
                        note.get("heat_score", 0),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        note.get("note_id")
                    ))
                else:
                    conn.execute("""
                        INSERT INTO raw_notes
                        (note_id, platform, title, content, author, author_followers,
                         likes, favorites, comments, shares, publish_time, collect_time,
                         url, tags, heat_score, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        note.get("note_id"), note.get("platform"),
                        note.get("title"), note.get("content"),
                        note.get("author"), note.get("author_followers", 0),
                        note.get("likes", 0), note.get("favorites", 0),
                        note.get("comments", 0), note.get("shares", 0),
                        note.get("publish_time"),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        note.get("url"),
                        json.dumps(note.get("tags", []), ensure_ascii=False),
                        note.get("heat_score", 0),
                        "pending"
                    ))
            return True
        except Exception as e:
            print(f"[DB Error] 插入选题失败: {e}")
            return False

    def get_top_topics(self, limit: int = 20, platform: str = None) -> List[Dict]:
        """获取热度Top N的候选选题"""
        with self._get_conn(self._raw_notes_db) as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM raw_notes WHERE status='pending' AND platform=? ORDER BY heat_score DESC LIMIT ?",
                    (platform, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM raw_notes WHERE status='pending' ORDER BY heat_score DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(r) for r in rows]

    def mark_note_used(self, note_id: str):
        """标记选题已被使用"""
        with self._get_conn(self._raw_notes_db) as conn:
            conn.execute(
                "UPDATE raw_notes SET status='used', used_count=used_count+1 WHERE note_id=?",
                (note_id,)
            )

    # ============================================
    # 发布日志 (publish_log.db)
    # ============================================
    def _init_publish_log_db(self):
        """初始化发布日志表结构"""
        with self._get_conn(self._publish_log_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS publish_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    account TEXT NOT NULL,
                    title TEXT,
                    scheduled_time TEXT,
                    actual_publish_time TEXT,
                    status TEXT DEFAULT 'pending',
                    post_url TEXT,
                    screenshot_path TEXT,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    clash_node TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_platform ON publish_log(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_status ON publish_log(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_publish_scheduled ON publish_log(scheduled_time)")

    def insert_publish_log(self, log: Dict) -> int:
        """插入发布日志，返回记录ID"""
        with self._get_conn(self._publish_log_db) as conn:
            cursor = conn.execute("""
                INSERT INTO publish_log
                (content_id, platform, account, title, scheduled_time,
                 status, clash_node, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                log.get("content_id"), log.get("platform"), log.get("account"),
                log.get("title"), log.get("scheduled_time"),
                "pending", log.get("clash_node"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            return cursor.lastrowid

    def update_publish_status(self, log_id: int, status: str, **kwargs):
        """更新发布状态"""
        fields = ["status", "updated_at"]
        values = [status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        for key, val in kwargs.items():
            if key in ["actual_publish_time", "post_url", "screenshot_path", "error_message", "retry_count"]:
                fields.append(f"{key}=?")
                values.append(val)
        values.append(log_id)
        with self._get_conn(self._publish_log_db) as conn:
            conn.execute(
                f"UPDATE publish_log SET {', '.join(fields)} WHERE id=?",
                values
            )

    def get_pending_publishes(self) -> List[Dict]:
        """获取所有待发布的记录"""
        with self._get_conn(self._publish_log_db) as conn:
            rows = conn.execute(
                "SELECT * FROM publish_log WHERE status='pending' ORDER BY scheduled_time ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ============================================
    # 数据指标 (metrics.db)
    # ============================================
    def _init_metrics_db(self):
        """初始化数据指标表结构"""
        with self._get_conn(self._metrics_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT UNIQUE,
                    platform TEXT NOT NULL,
                    account TEXT NOT NULL,
                    title TEXT,
                    publish_time TEXT,
                    post_url TEXT,
                    total_views INTEGER DEFAULT 0,
                    total_likes INTEGER DEFAULT 0,
                    total_favorites INTEGER DEFAULT 0,
                    total_comments INTEGER DEFAULT 0,
                    total_shares INTEGER DEFAULT 0,
                    followers_gain INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    platform TEXT,
                    account TEXT,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    favorites INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    followers_gain INTEGER DEFAULT 0,
                    collect_time TEXT,
                    UNIQUE(content_id, date)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_date ON daily_metrics(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_platform ON daily_metrics(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform)")

    def upsert_daily_metrics(self, metrics: Dict):
        """插入或更新每日数据指标"""
        with self._get_conn(self._metrics_db) as conn:
            existing = conn.execute(
                "SELECT id FROM daily_metrics WHERE content_id=? AND date=?",
                (metrics.get("content_id"), metrics.get("date"))
            ).fetchone()

            if existing:
                conn.execute("""
                    UPDATE daily_metrics SET
                        views=?, likes=?, favorites=?, comments=?, shares=?,
                        followers_gain=?, collect_time=?
                    WHERE content_id=? AND date=?
                """, (
                    metrics.get("views", 0), metrics.get("likes", 0),
                    metrics.get("favorites", 0), metrics.get("comments", 0),
                    metrics.get("shares", 0), metrics.get("followers_gain", 0),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    metrics.get("content_id"), metrics.get("date")
                ))
            else:
                conn.execute("""
                    INSERT INTO daily_metrics
                    (content_id, date, platform, account, views, likes, favorites,
                     comments, shares, followers_gain, collect_time)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    metrics.get("content_id"), metrics.get("date"),
                    metrics.get("platform"), metrics.get("account"),
                    metrics.get("views", 0), metrics.get("likes", 0),
                    metrics.get("favorites", 0), metrics.get("comments", 0),
                    metrics.get("shares", 0), metrics.get("followers_gain", 0),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

            # 同步更新posts表的累计数据
            conn.execute("""
                INSERT OR IGNORE INTO posts
                (content_id, platform, account, title, publish_time, post_url, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (
                metrics.get("content_id"), metrics.get("platform"),
                metrics.get("account"), metrics.get("title", ""),
                metrics.get("publish_time", ""), metrics.get("post_url", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.execute("""
                UPDATE posts SET
                    total_views=(SELECT SUM(views) FROM daily_metrics WHERE content_id=?),
                    total_likes=(SELECT SUM(likes) FROM daily_metrics WHERE content_id=?),
                    total_favorites=(SELECT SUM(favorites) FROM daily_metrics WHERE content_id=?),
                    total_comments=(SELECT SUM(comments) FROM daily_metrics WHERE content_id=?),
                    total_shares=(SELECT SUM(shares) FROM daily_metrics WHERE content_id=?),
                    followers_gain=(SELECT SUM(followers_gain) FROM daily_metrics WHERE content_id=?)
                WHERE content_id=?
            """, (
                metrics.get("content_id"), metrics.get("content_id"),
                metrics.get("content_id"), metrics.get("content_id"),
                metrics.get("content_id"), metrics.get("content_id"),
                metrics.get("content_id")
            ))

    def get_metrics_by_date_range(self, start_date: str, end_date: str, platform: str = None) -> List[Dict]:
        """按日期范围获取数据指标"""
        with self._get_conn(self._metrics_db) as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? AND platform=? ORDER BY date DESC",
                    (start_date, end_date, platform)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date DESC",
                    (start_date, end_date)
                ).fetchall()
            return [dict(r) for r in rows]

    def get_top_posts(self, limit: int = 10, platform: str = None) -> List[Dict]:
        """获取表现最好的内容（按总互动量排序）"""
        with self._get_conn(self._metrics_db) as conn:
            if platform:
                rows = conn.execute("""
                    SELECT *, (total_likes + total_favorites + total_comments + total_shares) as engagement
                    FROM posts WHERE platform=? ORDER BY engagement DESC LIMIT ?
                """, (platform, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT *, (total_likes + total_favorites + total_comments + total_shares) as engagement
                    FROM posts ORDER BY engagement DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]


# 全局单例
db = DatabaseManager()


if __name__ == "__main__":
    print("=" * 50)
    print("数据库初始化测试")
    print("=" * 50)

    # 测试选题库
    test_note = {
        "note_id": "test_001",
        "platform": "xiaohongshu",
        "title": "测试选题",
        "content": "测试内容",
        "author": "测试作者",
        "likes": 100,
        "favorites": 80,
        "comments": 20,
        "heat_score": 74.0
    }
    db.insert_raw_note(test_note)
    topics = db.get_top_topics(limit=5)
    print(f"\n选题库: 共{len(topics)}条候选选题")
    for t in topics:
        print(f"  - [{t['platform']}] {t['title']} (热度:{t['heat_score']})")

    # 测试发布日志
    log_id = db.insert_publish_log({
        "content_id": "test_content_001",
        "platform": "xiaohongshu",
        "account": "ai_xiaobai",
        "title": "测试发布",
        "scheduled_time": "2026-08-27 08:30:00"
    })
    print(f"\n发布日志: 插入记录ID={log_id}")

    # 测试数据指标
    db.upsert_daily_metrics({
        "content_id": "test_content_001",
        "date": "2026-08-27",
        "platform": "xiaohongshu",
        "account": "ai_xiaobai",
        "title": "测试发布",
        "views": 1000,
        "likes": 50,
        "favorites": 30,
        "comments": 10,
        "shares": 5
    })
    top_posts = db.get_top_posts(limit=5)
    print(f"\n数据指标: 共{len(top_posts)}条内容记录")
    for p in top_posts:
        print(f"  - [{p['platform']}] {p['title']} 互动量:{p.get('engagement', 0)}")

    print("\n数据库初始化成功!")
