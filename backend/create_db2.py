"""Create PostgreSQL database hhb_b2b."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

print("Note: PostgreSQL default superuser is 'postgres'")
print("If you don't know the password, check what you entered during PostgreSQL install.")
print()

PG_USER = input("PostgreSQL username [default: postgres]: ").strip()
if not PG_USER:
    PG_USER = "postgres"
PG_PASS = input("PostgreSQL password: ")

try:
    conn = psycopg2.connect(
        f"dbname=postgres user={PG_USER} password={PG_PASS} host=localhost port=5432",
        connect_timeout=5
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname='hhb_b2b'")
    exists = cur.fetchone()
    if not exists:
        cur.execute("CREATE DATABASE hhb_b2b;")
        print("Database 'hhb_b2b' CREATED successfully!")
    else:
        print("Database 'hhb_b2b' already exists.")
    cur.close()
    conn.close()
    print("Now run: python main.py")
except psycopg2.OperationalError as e:
    print(f"Connection failed: {e}")
    print("Common fixes:")
    print("  1. Make sure PostgreSQL service is running (services.msc -> postgresql)")
    print("  2. Try username 'postgres' with the password you set during install")
    print("  3. If you used Windows auth, the superuser is 'postgres'")
