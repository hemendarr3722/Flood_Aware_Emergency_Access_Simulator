import os
import sys
import psycopg

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL environment variable is required.")
        sys.exit(1)

    migrations = [
        "database/migrations/001_initial.sql",
        "database/migrations/002_rls_and_schema_improvements.sql",
        "database/migrations/003_routing_and_facilities.sql",
        "database/migrations/004_accessibility_schema.sql",
    ]

    print("Connecting to Supabase database...")
    with psycopg.connect(db_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            for mig_path in migrations:
                print(f"Applying migration: {mig_path}...")
                with open(mig_path, "r", encoding="utf-8") as f:
                    sql = f.read()
                cur.execute(sql)
                conn.commit()
                print(f"  ✓ {mig_path} applied successfully.")

        # Verify tables created
        with conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'gis' ORDER BY table_name")
            tables = [r[0] for r in cur.fetchall()]
            print(f"\nCreated {len(tables)} tables in schema 'gis':")
            for t in tables:
                print(f"  - gis.{t}")

    print("\nAll Supabase migrations applied successfully!")

if __name__ == "__main__":
    main()
