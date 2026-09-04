#!/usr/bin/env python3
import sys
import subprocess
import argparse

def run_psql(query: str) -> list[str]:
    cmd = [
        "docker", "exec", "-i", "splitbites-postgres",
        "psql", "-U", "postgres", "-d", "splitbites",
        "-t", "-A", "-c", query
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error querying Postgres: {res.stderr}", file=sys.stderr)
        return []
    lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
    return lines

def execute_sql(query: str) -> bool:
    cmd = [
        "docker", "exec", "-i", "splitbites-postgres",
        "psql", "-U", "postgres", "-d", "splitbites",
        "-c", query
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout.strip())
    if res.returncode != 0:
        print(f"Error executing SQL: {res.stderr}", file=sys.stderr)
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="SplitBites CLI Test Data & Recipe Cleanup Tool")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and count matching rows without deleting")
    parser.add_argument("--purge-test-accounts", action="store_true", help="Also clean up synthetic test users (*@example.com) and test households")
    parser.add_argument("--execute", action="store_true", help="Execute the deletion")
    args = parser.parse_args()

    # Safety: Default to dry-run unless --execute is explicitly passed
    is_dry_run = args.dry_run or not args.execute

    print("=" * 65)
    print("  🧹 SplitBites Database Cleanup Utility")
    print(f"  Mode: {'DRY RUN (Simulated)' if is_dry_run else 'LIVE EXECUTION'}")
    print("=" * 65)

    # 1. Check recipes matching cleanup criteria
    recipe_query = """
    SELECT recipe_id, title, COALESCE(description, '') 
    FROM recipes 
    WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb;
    """
    matching_recipes = run_psql(recipe_query)
    print(f"\n[1] Recipes matching criteria ('%test%', '%fixture%', or empty ingredients): {len(matching_recipes)}")
    for r in matching_recipes[:10]:
        print(f"    • {r}")
    if len(matching_recipes) > 10:
        print(f"    ... and {len(matching_recipes) - 10} more.")

    # 2. Check test accounts if requested
    test_recipes_by_test_users = []
    test_users = []
    test_households = []
    if args.purge_test_accounts:
        test_recipes_by_test_users = run_psql("""
            SELECT r.recipe_id, r.title, u.email 
            FROM recipes r 
            JOIN users u ON r.creator_id = u.user_id 
            WHERE u.email LIKE '%example.com';
        """)
        print(f"\n[2] Custom recipes created by test users (*@example.com): {len(test_recipes_by_test_users)}")
        for r in test_recipes_by_test_users[:5]:
            print(f"    • {r}")

        test_users = run_psql("SELECT user_id, email, full_name FROM users WHERE email LIKE '%example.com';")
        print(f"\n[3] Synthetic test users (*@example.com): {len(test_users)}")

        test_households = run_psql("""
            SELECT household_id, household_name 
            FROM households 
            WHERE household_name != 'The Bannon Family';
        """)
        print(f"\n[4] Test households (excluding 'The Bannon Family'): {len(test_households)}")

    if is_dry_run:
        print("\n💡 [DRY RUN] No changes were made to the database.")
        print("To apply cleanup, re-run with: --execute")
        return

    # Execute cleanup
    print("\n🚀 Executing cleanup...")
    sql_statements = []

    # Recipes matching pattern
    sql_statements.append("""
    DELETE FROM household_recipes 
    WHERE recipe_id IN (
        SELECT recipe_id FROM recipes 
        WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb
    );
    DELETE FROM recipes 
    WHERE title ILIKE '%test%' OR description ILIKE '%fixture%' OR ingredients = '[]'::jsonb;
    """)

    if args.purge_test_accounts:
        sql_statements.append("""
        -- Delete test recipes created by test users
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

        -- Delete test households (cascades meal plans, pantry items, household members)
        DELETE FROM households 
        WHERE household_name != 'The Bannon Family';

        -- Delete test users
        DELETE FROM users 
        WHERE email LIKE '%example.com';
        """)

    full_sql = "\n".join(sql_statements)
    execute_sql(full_sql)
    print("✅ Cleanup execution finished.")

if __name__ == "__main__":
    main()
