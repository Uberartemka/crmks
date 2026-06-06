from __future__ import annotations

from startup.db_init import startup_init_db

if __name__ == "__main__":
    startup_init_db()
    print("DB initialized successfully")
