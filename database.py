import os
import uuid
import datetime
import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import threading
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("healthbridge.database")

# ── DB Credentials ─────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "healthbridge")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# ── Connection Pool ────────────────────────────────────────────
_pool = None
_pool_lock = threading.Lock()

def init_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                try:
                    _pool = ThreadedConnectionPool(
                        minconn=1,
                        maxconn=20,
                        host=DB_HOST,
                        port=DB_PORT,
                        database=DB_NAME,
                        user=DB_USER,
                        password=DB_PASSWORD
                    )
                    logger.info("Database connection pool initialized successfully.")
                except Exception as e:
                    logger.critical(f"Failed to initialize database connection pool: {e}")
                    raise

def get_connection():
    """Returns a connection from the connection pool."""
    init_pool()
    return _pool.getconn()

def release_connection(conn):
    """Safely rolls back any pending transaction and returns the connection to the pool."""
    if conn:
        try:
            conn.rollback()
        except Exception:
            pass
        if _pool:
            try:
                _pool.putconn(conn)
            except Exception as e:
                logger.error(f"Error returning connection to pool: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            try:
                conn.close()
            except Exception:
                pass

def init_db():
    """
    Connects to the default 'postgres' database to ensure target database exists,
    then initializes all required tables.
    """
    # 1. Ensure target DB exists
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database="postgres"
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,))
        exists = cur.fetchone()
        if not exists:
            # Safely create database
            # PostgreSQL does not allow parameterization of identifiers, so we build it directly.
            # DB_NAME is configured in our local .env.
            cur.execute(f'CREATE DATABASE "{DB_NAME}"')
            logger.info(f"Created database: {DB_NAME}")
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Database creation check failed (continuing in case DB exists): {e}")

    # 2. Create tables
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        role VARCHAR(100) DEFAULT 'ASHA Worker',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Sessions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token VARCHAR(255) PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    );
    """)

    # Chats table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        id VARCHAR(255) PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        language VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Messages table
    # Note: image_path stores only a boolean-ish marker string like "uploaded"
    # or is NULL, as images are processed in-memory only and never saved on disk.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id VARCHAR(255) PRIMARY KEY,
        chat_id VARCHAR(255) NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        role VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        query_type VARCHAR(100),
        language VARCHAR(50) NOT NULL,
        image_path VARCHAR(512),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Ensure existing installations get the image_path column
    cur.execute("""
    ALTER TABLE messages ADD COLUMN IF NOT EXISTS image_path VARCHAR(512);
    """)

    cur.close()
    release_connection(conn)
    logger.info("Database tables initialized successfully.")
    
    # Run startup cleanup of expired sessions and start the periodic task
    try:
        cleanup_expired_sessions()
        start_periodic_cleanup()
    except Exception as e:
        logger.error(f"Failed to run startup session cleanup or start thread: {e}")

def cleanup_expired_sessions():
    """Deletes expired sessions from the sessions table."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cur.execute("DELETE FROM sessions WHERE expires_at < %s", (now,))
        conn.commit()
        logger.info("Expired sessions cleaned up successfully.")
    except Exception as e:
        logger.error(f"Failed to cleanup expired sessions: {e}")
    finally:
        cur.close()
        release_connection(conn)

def _periodic_cleanup_loop():
    while True:
        # Clean up every hour (3600 seconds)
        time.sleep(3600)
        try:
            cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Error in periodic sessions cleanup: {e}")

def start_periodic_cleanup():
    thread = threading.Thread(target=_periodic_cleanup_loop, daemon=True)
    thread.start()
    logger.info("Periodic sessions cleanup thread started.")

# ── Password Helpers ───────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

# ── Auth & Users ───────────────────────────────────────────────
def create_user(name: str, email: str, password: str, role: str = "ASHA Worker"):
    email_clean = email.strip().lower()
    pw_hash = hash_password(password)
    
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING id, name, email, role, created_at",
            (name.strip(), email_clean, pw_hash, role.strip())
        )
        user = cur.fetchone()
        conn.commit()
        return dict(user)
    except psycopg2.IntegrityError:
        conn.rollback()
        raise ValueError("User with this email already exists")
    finally:
        cur.close()
        release_connection(conn)

def verify_user(email: str, password: str):
    email_clean = email.strip().lower()
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM users WHERE email = %s", (email_clean,))
        user = cur.fetchone()
        if user and check_password(password, user["password_hash"]):
            return {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        return None
    finally:
        cur.close()
        release_connection(conn)

# ── Session Management ─────────────────────────────────────────
def create_session(user_id: int) -> str:
    token = str(uuid.uuid4())
    # Sessions valid for 7 days
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
            (token, user_id, expires_at)
        )
        conn.commit()
        return token
    finally:
        cur.close()
        release_connection(conn)

def get_user_by_token(token: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        cur.execute(
            """
            SELECT u.id, u.name, u.email, u.role 
            FROM sessions s 
            JOIN users u ON s.user_id = u.id 
            WHERE s.token = %s AND s.expires_at > %s
            """,
            (token, now)
        )
        user = cur.fetchone()
        return dict(user) if user else None
    finally:
        cur.close()
        release_connection(conn)

def delete_session(token: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
        conn.commit()
    finally:
        cur.close()
        release_connection(conn)

# ── Chats CRUD ──────────────────────────────────────────────────
def create_chat(user_id: int, title: str, language: str = "English") -> dict:
    chat_id = str(uuid.uuid4())
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO chats (id, user_id, title, language) VALUES (%s, %s, %s, %s) RETURNING id, title, language, created_at",
            (chat_id, user_id, title, language)
        )
        chat = cur.fetchone()
        conn.commit()
        return dict(chat)
    finally:
        cur.close()
        release_connection(conn)

def get_user_chats(user_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT id, title, language, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        chats = cur.fetchall()
        return [dict(chat) for chat in chats]
    finally:
        cur.close()
        release_connection(conn)

def update_chat_title(chat_id: str, title: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE chats SET title = %s WHERE id = %s", (title, chat_id))
        conn.commit()
    finally:
        cur.close()
        release_connection(conn)

def delete_chat(user_id: int, chat_id: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM chats WHERE id = %s AND user_id = %s", (chat_id, user_id))
        conn.commit()
    finally:
        cur.close()
        release_connection(conn)

# ── Messages CRUD ───────────────────────────────────────────────
def add_message(chat_id: str, role: str, content: str, query_type: str = "general_health", language: str = "English", image_path: str = None) -> dict:
    msg_id = str(uuid.uuid4())
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            INSERT INTO messages (id, chat_id, role, content, query_type, language, image_path) 
            VALUES (%s, %s, %s, %s, %s, %s, %s) 
            RETURNING id, chat_id, role, content, query_type, language, image_path, created_at
            """,
            (msg_id, chat_id, role, content, query_type, language, image_path)
        )
        msg = cur.fetchone()
        conn.commit()
        return dict(msg)
    finally:
        cur.close()
        release_connection(conn)

def get_chat_messages(chat_id: str) -> list:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT id, role, content, query_type, language, image_path, created_at FROM messages WHERE chat_id = %s ORDER BY created_at ASC",
            (chat_id,)
        )
        messages = cur.fetchall()
        return [dict(msg) for msg in messages]
    finally:
        cur.close()
        release_connection(conn)
