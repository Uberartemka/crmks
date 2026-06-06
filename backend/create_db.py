"""Create PostgreSQL database hhb_b2b via psycopg2 (no psql needed)."""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

PG_USER = "Herodot"  # from setup output
PG_PASS = input("Enter PostgreSQL password for user '{}': ".format(PG_USER))

# Connect to default 'postgres' database
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user=PG_USER,
    password=PG_PASS,
    dbname="postgres"
)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cursor = conn.cursor()

# Check if database exists
cursor.execute("SELECT 1 FROM pg_database WHERE datname='hhb_b2b'")
exists = cursor.fetchone()

if exists:
    print("Database 'hhb_b2b' already exists.")
else:
    cursor.execute("CREATE DATABASE hhb_b2b;")
    print("Database 'hhb_b2b' created successfully!")

cursor.close()
conn.close()
print("You can now run: python main.py")
