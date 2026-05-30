# PostgreSQL Setup Guide for HHB/FKD

## Step 1: Download & Install PostgreSQL

1. Go to: https://www.postgresql.org/download/windows/
2. Download the installer (latest version, e.g. 16.x)
3. Run the installer:
   - Installation Directory: `C:\Program Files\PostgreSQL\16`
   - Data Directory: `C:\Program Files\PostgreSQL\16\data`
   - Password: set a strong password for `postgres` user (remember it!)
   - Port: `5432` (default)
   - Locale: `Russian, Russia`
   - Keep `pgAdmin 4` and `Stack Builder` checked (useful tools)

4. After install, make sure service is running:
   - Open Services (`services.msc`)
   - Find `postgresql-x64-16`
   - Status should be `Running`

## Step 2: Create Database

Open PowerShell as Administrator and run the setup script:

```powershell
# Navigate to backend folder
cd D:\pod\backend

# Run setup script (creates database and sets environment variable)
.\setup_postgres.ps1
```

Or manually via psql:

```bash
# Open SQL Shell (psql) from Start Menu
# Server: localhost, Database: postgres, Port: 5432, Username: postgres
# Enter your password

CREATE DATABASE hhb_b2b;
\q
```

## Step 3: Start Server to Create Tables

```bash
cd D:\pod\backend
python main.py
```

The server will auto-detect PostgreSQL and create all tables (`users`, `parsed_leads`, `employee_plans`, `call_logs`, etc.).

Look for this in console:
```
[Database] PostgreSQL доступен. Используем PG для каталога/КП.
```

## Step 4: Migrate Existing SQLite Data (Optional)

If you have existing data in `catalog.db`:

```bash
# First, start the server once so PostgreSQL tables are created
# Then run migration:
python migrate_to_postgres.py
# Type "yes" when prompted
```

This copies all data from SQLite to PostgreSQL.

## Step 5: Verify

Log in to `admin.html` with `admin` / `admin123`.
All data should be there. Check "Персонал" tab — seed users should appear.

## Troubleshooting

### "PostgreSQL недоступен. Fallback на SQLite"
- Check if PostgreSQL service is running (`services.msc`)
- Check if password in `PG_URL` matches your actual password
- Try connecting manually: `psql -U postgres -h localhost -d hhb_b2b`

### psql not found
- Add PostgreSQL bin to PATH: `C:\Program Files\PostgreSQL\16\bin`
- Or use SQL Shell from Start Menu

### psycopg2 not installed
```bash
pip install psycopg2-binary
```

## Environment Variable

The connection string is read from `DATABASE_URL` environment variable.
Default in code: `postgresql://postgres:postgres@localhost:5432/hhb_b2b`

To set permanently on Windows:
```powershell
[Environment]::SetEnvironmentVariable("DATABASE_URL", "postgresql://postgres:YOURPASS@localhost:5432/hhb_b2b", "User")
```

Restart your IDE/terminal after setting environment variables.
