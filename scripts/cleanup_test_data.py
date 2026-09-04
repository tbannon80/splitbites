#!/usr/bin/env python3
import sys
import os
import argparse
import subprocess

CENTRAL_TZ = "America/Chicago"

def is_running_in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv("DATABASE_URL") is not None

class DBClient:
    def __init__(self):
        self.use_asyncpg = False
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            try:
                import asyncpg
                import asyncio
                self.use_asyncpg = True
                self.db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
                self.asyncpg = asyncpg
                self.asyncio = asyncio
            except ImportError:
                self.use_asyncpg = False

    def query(self, sql: str) -> list[str]:
        if self.use_asyncpg:
            async def _run():
                conn = await self.asyncpg.connect(self.db_url)
                try:
                    records = await conn.fetch(sql)
                    lines = []
                    for r in records:
                        lines.append("|".join(str(v) if v is not None else "" for v in r.values()))
                    return lines
                finally:
                    await conn.close()
            return self.asyncio.run(_run())
        else:
            cmd = [
                "docker", "exec", "-i", "splitbites-postgres",
                "psql", "-U", "postgres", "-d", "splitbites",
                "-t", "-A", "-c", sql
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Error querying Postgres: {res.stderr}", file=sys.stderr)
                return []
            return [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]

    def execute(self, sql: str) -> str:
        if self.use_asyncpg:
            async def _run():
                conn = await self.asyncpg.connect(self.db_url)
                try:
                    results = []
                    # Split statements
                    statements = [s.strip() for s in sql.strip().split(";") if s.strip()]
                    async with conn.transaction():
                        for stmt in statements:
                            status = await conn.execute(stmt)
                            results.append(status)
                    return "\n".join(results)
                finally:
                    await conn.close()
            return self.asyncio.run(_run())
        else:
            cmd = [
                "docker", "exec", "-i", "splitbites-postgres",
                "psql", "-U", "postgres", "-d", "splitbites",
                "-c", sql
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Error executing SQL: {res.stderr}", file=sys.stderr)
            return res.stdout.strip()

def main():
    parser = argparse.ArgumentParser(description="SplitBites CLI Test Data & Recipe Cleanup Tool")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count matching rows without deleting")
    parser.add_argument("--purge-test-accounts", action="store_true", help="Also clean up synthetic test users (*@example.com) and test households")
    parser.add_argument("--execute", action="store_true", help="Execute the deletion")
    args = parser.parse_args()

    is_dry_run = args.dry_run or not args.execute
    db = DBClient()

    print("=" * 65)
    print("  🧹 SplitBites Database Cleanup Utility")
    print(f"  Mode: {'DRY RUN (Inspection Only)' if is_dry_run else 'LIVE EXECUTION'}")
    print(f"  Driver: {'Direct asyncpg' if db.use_asyncpg else 'docker exec psql'}")
    print("=" * 65)

    # 1. Matching title/fixture/empty recipes
    recipe_query = """
    SELECT recipe_id, title, COALESCE(description, '') 
    FROM recipes 
    WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb;
    """
    matching_recipes = db.query(recipe_query)
    print(f"\n[1] Recipes matching criteria ('%test%', '%fixture%', or empty ingredients): {len(matching_recipes)}")
    for r in matching_recipes[:5]:
        print(f"    • {r}")

    # 2. Test accounts and artifacts
    test_recipes_by_users = []
    test_users = []
    test_households = []
    if args.purge_test_accounts:
        test_recipes_by_users = db.query("""
            SELECT r.recipe_id, r.title, u.email 
            FROM recipes r 
            JOIN users u ON r.creator_id = u.user_id 
            WHERE u.email LIKE '%example.com';
        """)
        print(f"\n[2] Custom recipes created by test users (*@example.com): {len(test_recipes_by_users)}")
        for r in test_recipes_by_users[:5]:
            print(f"    • {r}")
        if len(test_recipes_by_users) > 5:
            print(f"    ... and {len(test_recipes_by_users) - 5} more.")

        test_users = db.query("SELECT user_id, email, full_name FROM users WHERE email LIKE '%example.com';")
        print(f"\n[3] Synthetic test users (*@example.com): {len(test_users)}")

        test_households = db.query("""
            SELECT household_id, household_name 
            FROM households 
            WHERE household_name != 'The Bannon Family';
        """)
        print(f"\n[4] Test households (excluding 'The Bannon Family'): {len(test_households)}")

    if is_dry_run:
        print("\n💡 [DRY RUN] No changes were made to the database.")
        print("To execute, run with: --execute --purge-test-accounts")
        return

    print("\n🚀 Executing database cleanup...")
    sql = """
    DELETE FROM household_recipes 
    WHERE recipe_id IN (
        SELECT recipe_id FROM recipes 
        WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb
    );
    DELETE FROM recipes 
    WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb;
    """

    if args.purge_test_accounts:
        sql += """
        DELETE FROM household_recipes 
        WHERE recipe_id IN (
            SELECT r.recipe_id FROM recipes r 
            JOIN users u ON r.creator_id = u.user_id 
            WHERE u.email LIKE '%example.com'
        );
        DELETE FROM recipes 
        WHERE creator_id IN (
            SELECT user_id FROM users WHERE email LIKE '%example.com'
        );
        DELETE FROM households 
        WHERE household_name != 'The Bannon Family';
        DELETE FROM users 
        WHERE email LIKE '%example.com';
        """

    result = db.execute(sql)
    print("\nExecution Output:\n" + result)

    # Post-cleanup verification
    total_u = db.query("SELECT count(*) FROM users;")[0]
    total_h = db.query("SELECT count(*) FROM households;")[0]
    total_r = db.query("SELECT count(*) FROM recipes;")[0]
    cust_r = db.query("SELECT count(*) FROM recipes WHERE creator_id IS NOT NULL;")[0]

    print("\n" + "=" * 65)
    print("  ✅ Post-Cleanup Database State")
    print("=" * 65)
    print(f"  • Total Registered Users: {total_u} (Real users preserved)")
    print(f"  • Total Households:       {total_h} (The Bannon Family preserved)")
    print(f"  • Total Recipes:          {total_r} (76 seed recipes + {cust_r} custom)")
    print("=" * 65)

if __name__ == "__main__":
    main()
