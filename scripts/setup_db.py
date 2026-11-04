#!/usr/bin/env python3
"""
Campus Nexus — Interactive Database Setup & Management Utility.

Provides:
1. Migration inspection and interactive execution.
2. Menu-driven database navigation (view tables, inspect schemas, browse rows).
3. Direct DQL execution (SELECT queries with formatted ASCII table output).
4. Direct DML / DDL execution (INSERT, UPDATE, DELETE with transaction safeguards).
5. Simplified User Creation (Superuser Admin, Staff, or Standard Student)
   with all model complexity, password hashing, and enrollment parsing abstracted.
6. Multi-database compatibility (PostgreSQL and SQLite3).
"""

import os
import sys
import getpass
import re
import secrets
from pathlib import Path
from typing import List, Tuple, Any, Dict

# Ensure console safe encoding on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Setup default Django settings if not already defined
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ["DJANGO_SETTINGS_MODULE"] = "campus.settings.dev"

import django
django.setup()

from django.conf import settings
from django.db import connection, transaction
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

User = get_user_model()
ENROLLMENT_REGEX = re.compile(r'^(?:\d{4}|20XX)[BMP][A-Z]{3}\d{3}$')


# ==============================================================================
# Terminal UI Formatting Helpers
# ==============================================================================

def print_header(title: str):
    width = 68
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)


def print_subline(title: str):
    print(f"\n--- {title} " + "-" * max(10, 50 - len(title)))


def format_table(headers: List[str], rows: List[Tuple[Any, ...]], max_col_width: int = 35) -> str:
    """Format tabular data into an aligned ASCII table."""
    if not headers and not rows:
        return "(empty table)"

    str_rows = []
    for r in rows:
        str_rows.append([
            (str(c) if c is not None else "NULL")[:max_col_width] for c in r
        ])

    col_widths = [len(h) for h in headers]
    for row in str_rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(val))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))

    data_lines = []
    for row in str_rows:
        data_lines.append(" | ".join(row[i].ljust(col_widths[i]) if i < len(row) else "".ljust(col_widths[i]) for i in range(len(headers))))

    return f"\n{header_line}\n{separator_line}\n" + "\n".join(data_lines) + "\n"


# ==============================================================================
# 1. Migration Management
# ==============================================================================

def get_unapplied_migrations() -> List[Tuple[str, str]]:
    """Return a list of (app_label, migration_name) that have not been applied."""
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [(migration.app_label, migration.name) for migration, backwards in plan]


def check_and_run_migrations(interactive: bool = True):
    """Check for pending migrations and offer to apply them."""
    print_subline("Migration Check")
    unapplied = get_unapplied_migrations()

    if not unapplied:
        print("[OK] All database migrations are up to date.")
        return

    print(f"[!] Found {len(unapplied)} unapplied migration(s):")
    for app, name in unapplied:
        print(f"    - {app}: {name}")

    if interactive:
        choice = input("\nWould you like to apply these migrations now? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            print("\nApplying migrations...")
            try:
                call_command("migrate", interactive=False)
                print("[OK] Migrations successfully applied.")
            except Exception as e:
                print(f"[FAIL] Error applying migrations: {e}")
        else:
            print("[INFO] Skipping migrations.")
    else:
        print("\nApplying migrations in non-interactive mode...")
        call_command("migrate", interactive=False)
        print("[OK] Migrations successfully applied.")


# ==============================================================================
# 2. Database Inspection (DQL / Schema View)
# ==============================================================================

def get_database_tables() -> List[str]:
    """Retrieve list of table names in current database."""
    with connection.cursor() as cursor:
        return connection.introspection.table_names(cursor)


def view_database_tables():
    """Menu to browse tables, row counts, and data."""
    tables = get_database_tables()
    if not tables:
        print("\n[!] No tables found in database. You may need to run migrations first.")
        return

    # Prioritize campus nexus application tables
    priority = [t for t in tables if t.startswith(('accounts_', 'coordinate_', 'auth_'))]
    others = [t for t in tables if t not in priority]
    ordered_tables = sorted(priority) + sorted(others)

    print_subline("Database Tables")
    for idx, table in enumerate(ordered_tables, 1):
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cursor.fetchone()[0]
        print(f"  [{idx:2d}] {table.ljust(35)} ({cnt} records)")

    choice = input("\nEnter table number to inspect (or 0 to return): ").strip()
    if not choice.isdigit() or int(choice) == 0:
        return

    selected_idx = int(choice)
    if 1 <= selected_idx <= len(ordered_tables):
        table_name = ordered_tables[selected_idx - 1]
        inspect_table(table_name)
    else:
        print("[FAIL] Invalid table selection.")


def inspect_table(table_name: str):
    """View schema and browse top records of a table."""
    print_header(f"Table Inspection: {table_name}")

    with connection.cursor() as cursor:
        # 1. Fetch column info
        columns = connection.introspection.get_table_description(cursor, table_name)
        col_names = [col.name for col in columns]

        print(f"Columns ({len(col_names)}): {', '.join(col_names)}")

        # 2. Fetch top 15 rows
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 15")
        rows = cursor.fetchall()

    if rows:
        print(format_table(col_names, rows, max_col_width=25))
        print(f"Showing {len(rows)} record(s).")
    else:
        print("\n(Table is currently empty)")

    input("\nPress Enter to return to main menu...")


def execute_dql_query():
    """Prompt user for a SELECT statement and render formatted results."""
    print_header("Execute DQL Query (Data Query Language)")
    print("Enter a SQL SELECT query to execute against the active database.")
    print("Example: SELECT id, enrollment_number, email, is_superuser FROM accounts_user;")
    print("Type 'cancel' to return.\n")

    query = input("SQL Query > ").strip()
    if not query or query.lower() == "cancel":
        return

    if not query.lower().startswith("select") and not query.lower().startswith("with") and not query.lower().startswith("explain"):
        print("[!] Warning: DQL should start with SELECT, WITH, or EXPLAIN.")
        confirm = input("Execute anyway? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            return

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:
                headers = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                print(format_table(headers, rows))
                print(f"[OK] Query returned {len(rows)} row(s).")
            else:
                print(f"[OK] Query executed. (No rows returned)")
    except Exception as e:
        print(f"\n[FAIL] Database error executing query:\n{e}")

    input("\nPress Enter to continue...")


# ==============================================================================
# 3. Database Execution (DML / DDL)
# ==============================================================================

def execute_dml_ddl_statement():
    """Prompt user for DML/DDL (INSERT, UPDATE, DELETE, ALTER, etc.) with confirmation."""
    print_header("Execute DML / DDL Statement")
    print("Enter SQL statement (INSERT, UPDATE, DELETE, ALTER, CREATE, DROP).")
    print("Statements execute inside a transaction with automatic rollback on error.")
    print("Type 'cancel' to return.\n")

    statement = input("SQL Statement > ").strip()
    if not statement or statement.lower() == "cancel":
        return

    print(f"\nProposed statement:\n  {statement}")
    confirm = input("\nAre you SURE you want to execute this statement? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("[INFO] Operation cancelled.")
        return

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(statement)
                rowcount = cursor.rowcount
        print(f"\n[OK] Statement executed successfully. Rows affected: {rowcount}")
    except Exception as e:
        print(f"\n[FAIL] Statement failed and was rolled back:\n{e}")

    input("\nPress Enter to continue...")


# ==============================================================================
# 4. User Provisioning (Complexity Abstracted)
# ==============================================================================

def add_user_interactive():
    """Interactive wizard to create a user with abstracted complexity."""
    print_header("Campus Nexus — Add User Wizard")
    print("Creates accounts directly in the database with auto-computed branch/degree,")
    print("secure password hashing, and role provisioning for PostgreSQL & SQLite.\n")

    # 1. Role Selection
    print("Select User Role:")
    print("  [1] Superuser / Administrator (Full admin & staff privileges)")
    print("  [2] Staff Member (Administrative access)")
    print("  [3] Standard Student / Member (Regular platform access)")
    role_choice = input("Choice [1-3, default 1]: ").strip() or "1"

    is_superuser = (role_choice == "1")
    is_staff = (role_choice in ("1", "2"))

    # 2. Enrollment Number
    suggested_enrollment = "2024BCSE001" if not is_superuser else "2024BCSE099"
    while True:
        prompt = f"Enrollment Number (Format: 2024BCSE001) [default: {suggested_enrollment}]: "
        enrollment = input(prompt).strip().upper() or suggested_enrollment
        if ENROLLMENT_REGEX.match(enrollment):
            if User.objects.filter(enrollment_number=enrollment).exists():
                print(f"[!] User with enrollment '{enrollment}' already exists.")
                overwrite = input("Do you want to update this existing user? [y/N]: ").strip().lower()
                if overwrite in ("y", "yes"):
                    update_existing = True
                    break
                else:
                    continue
            else:
                update_existing = False
                break
        else:
            print("[FAIL] Invalid format. Must be YYYY[B/M/P][Branch 3-char][Roll 3-digits] e.g. 2024BCSE001")

    # 3. Name
    first_name = input("First Name [default: Campus]: ").strip() or "Campus"
    last_name = input(f"Last Name [default: {'Admin' if is_superuser else 'Student'}]: ").strip() or ("Admin" if is_superuser else "Student")

    # 4. Email
    default_email = f"{enrollment.lower()}@nitsri.ac.in"
    email = input(f"Email [default: {default_email}]: ").strip().lower() or default_email

    # 5. Phone & Gender
    phone = input("Phone Number [default: +919876543210]: ").strip() or "+919876543210"
    gender_input = input("Gender (M/F) [default: M]: ").strip().upper() or "M"
    gender = "F" if gender_input.startswith("F") else "M"

    # 6. Password
    auto_pw = secrets.token_urlsafe(12)
    pw_input = input(f"Password [leave blank to auto-generate: '{auto_pw}']: ").strip()
    password = pw_input if pw_input else auto_pw

    # 7. Verification & 2FA
    verified_in = input("Mark Account as Verified? [Y/n]: ").strip().lower()
    verified = (verified_in not in ("n", "no"))

    two_fa_in = input("Enable Two-Factor Authentication (2FA)? [y/N]: ").strip().lower()
    two_fa = (two_fa_in in ("y", "yes"))

    # Summary confirmation
    print("\nSummary of User to Provision:")
    print(f"  Enrollment Number : {enrollment}")
    print(f"  Name              : {first_name} {last_name}")
    print(f"  Email             : {email}")
    print(f"  Phone             : {phone}")
    print(f"  Gender            : {gender}")
    print(f"  Role              : {'Superuser Admin' if is_superuser else ('Staff' if is_staff else 'Student')}")
    print(f"  Verified          : {verified}")
    print(f"  2FA Enabled       : {two_fa}")
    print(f"  Password          : {password}")

    proceed = input("\nProceed with database creation? [Y/n]: ").strip().lower()
    if proceed in ("n", "no"):
        print("[INFO] User creation cancelled.")
        return

    try:
        if update_existing:
            user = User.objects.get(enrollment_number=enrollment)
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone_number = phone
            user.gender = gender
            user.is_superuser = is_superuser
            user.is_staff = is_staff
            user.verified = verified
            user.two_factor_enabled = two_fa
            user.set_password(password)
            user.save()
            print(f"\n[OK] Successfully updated user '{enrollment}'.")
        else:
            user = User(
                enrollment_number=enrollment,
                username=enrollment,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone,
                gender=gender,
                is_superuser=is_superuser,
                is_staff=is_staff,
                is_active=True,
                verified=verified,
                two_factor_enabled=two_fa,
            )
            user.set_password(password)
            user.save()
            print(f"\n[OK] Successfully created user '{enrollment}'.")

        print(f"    Degree: {user.degree} | Branch: {user.branch} | Year: {user.joining_year}")
        print(f"    Password: {password}")
    except Exception as e:
        print(f"\n[FAIL] Error saving user to database:\n{e}")

    input("\nPress Enter to continue...")


# ==============================================================================
# 5. Database Diagnostics & Status
# ==============================================================================

def print_diagnostics():
    """Print connected database engine, connection state, and statistics."""
    print_header("Database Diagnostics & Statistics")

    engine = settings.DATABASES['default']['ENGINE']
    db_name = settings.DATABASES['default'].get('NAME', '')
    host = settings.DATABASES['default'].get('HOST', 'localhost')
    port = settings.DATABASES['default'].get('PORT', '')

    print(f"  Database Engine    : {engine}")
    print(f"  Database Name/Path : {db_name}")
    if 'postgresql' in engine:
        print(f"  Host / Port        : {host}:{port or '5432'}")
        print(f"  User               : {settings.DATABASES['default'].get('USER', '')}")
    print(f"  Django Settings    : {os.environ.get('DJANGO_SETTINGS_MODULE', 'unknown')}")

    # Test connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        print("  Connection Status  : [OK] Active & Healthy")
    except Exception as e:
        print(f"  Connection Status  : [FAIL] Failed ({e})")
        input("\nPress Enter to continue...")
        return

    # Counts
    try:
        user_count = User.objects.count()
        admin_count = User.objects.filter(is_superuser=True).count()
        table_count = len(get_database_tables())
        print(f"  Total Tables       : {table_count}")
        print(f"  Total Users        : {user_count} ({admin_count} Superusers)")

        # Coordinates ride count if installed
        try:
            from coordinate.models import Ride
            print(f"  Total Rides        : {Ride.objects.count()}")
        except Exception:
            pass
    except Exception as e:
        print(f"  Table Stats Error  : {e}")

    input("\nPress Enter to continue...")


# ==============================================================================
# Main Interactive Menu Loop
# ==============================================================================

def interactive_menu():
    """Run the main interactive menu loop."""
    # First, always check for unapplied migrations
    check_and_run_migrations(interactive=True)

    while True:
        engine = settings.DATABASES['default']['ENGINE'].split('.')[-1]
        db_name = Path(str(settings.DATABASES['default'].get('NAME', ''))).name

        print_header("CAMPUS NEXUS — DATABASE SETUP & MANAGEMENT")
        print(f"  Database: {engine.upper()} ({db_name}) | Settings: {os.environ.get('DJANGO_SETTINGS_MODULE', 'dev')}")
        print("-" * 68)
        print("  [1] View Database Tables & Records (Browse & Inspect)")
        print("  [2] Execute DQL Query (SELECT Statements / Read Data)")
        print("  [3] Execute DML / DDL Statement (INSERT, UPDATE, DELETE, ALTER)")
        print("  [4] Add User (Admin or Student — Complexity Abstracted)")
        print("  [5] Manage Migrations (Check Status & Apply)")
        print("  [6] Database Connection Diagnostics & Statistics")
        print("  [0] Exit")
        print("=" * 68)

        choice = input("\nEnter choice [0-6]: ").strip()

        if choice == "1":
            view_database_tables()
        elif choice == "2":
            execute_dql_query()
        elif choice == "3":
            execute_dml_ddl_statement()
        elif choice == "4":
            add_user_interactive()
        elif choice == "5":
            check_and_run_migrations(interactive=True)
            input("\nPress Enter to continue...")
        elif choice == "6":
            print_diagnostics()
        elif choice in ("0", "q", "exit", "quit"):
            print("\nExiting Campus Nexus Setup. Goodbye!\n")
            break
        else:
            print("[FAIL] Invalid option. Please choose between 0 and 6.")


# ==============================================================================
# Non-Interactive / CLI Argument Handling
# ==============================================================================

def main(argv=None):
    import argparse
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "setup_db":
        argv = argv[1:]

    parser = argparse.ArgumentParser(
        description="Campus Nexus Database Setup & User Provisioning CLI"
    )
    parser.add_argument("--migrate", action="store_true", help="Apply any unapplied migrations non-interactively")
    parser.add_argument("--check-migrations", action="store_true", help="Check for unapplied migrations and exit with status code")
    parser.add_argument("--add-user", action="store_true", help="Non-interactive user creation")
    parser.add_argument("--enrollment", type=str, help="Enrollment number for user")
    parser.add_argument("--password", type=str, help="Password for user")
    parser.add_argument("--email", type=str, help="Email address")
    parser.add_argument("--first-name", type=str, default="Campus", help="First name")
    parser.add_argument("--last-name", type=str, default="User", help="Last name")
    parser.add_argument("--phone", type=str, default="+919876543210", help="Phone number")
    parser.add_argument("--gender", type=str, default="M", choices=["M", "F"], help="Gender (M/F)")
    parser.add_argument("--admin", action="store_true", help="Create as superuser and staff")
    parser.add_argument("--staff", action="store_true", help="Create as staff")
    parser.add_argument("--verified", action="store_true", default=True, help="Mark user as verified")

    args = parser.parse_args(argv)

    if args.check_migrations:
        unapplied = get_unapplied_migrations()
        if unapplied:
            print(f"Found {len(unapplied)} unapplied migrations:")
            for a, m in unapplied:
                print(f"  {a}: {m}")
            sys.exit(1)
        else:
            print("Database is up to date.")
            sys.exit(0)

    if args.migrate:
        check_and_run_migrations(interactive=False)
        if not args.add_user:
            return

    if args.add_user:
        enrollment = (args.enrollment or "2024BCSE001").upper()
        if not ENROLLMENT_REGEX.match(enrollment):
            print(f"[FAIL] Error: Invalid enrollment number format: {enrollment}")
            sys.exit(1)
        password = args.password or secrets.token_urlsafe(12)
        email = args.email or f"{enrollment.lower()}@nitsri.ac.in"

        user, created = User.objects.get_or_create(
            enrollment_number=enrollment,
            defaults={
                "username": enrollment,
                "first_name": args.first_name,
                "last_name": args.last_name,
                "email": email,
                "phone_number": args.phone,
                "gender": args.gender,
                "is_superuser": args.admin,
                "is_staff": args.admin or args.staff,
                "is_active": True,
                "verified": args.verified,
            }
        )
        user.set_password(password)
        if not created:
            user.first_name = args.first_name
            user.last_name = args.last_name
            user.email = email
            user.phone_number = args.phone
            user.gender = args.gender
            user.is_superuser = args.admin
            user.is_staff = args.admin or args.staff
            user.verified = args.verified
        user.save()

        action = "Created" if created else "Updated"
        print(f"[OK] {action} user {enrollment}:")
        print(f"    Name: {user.first_name} {user.last_name}")
        print(f"    Email: {user.email}")
        print(f"    Role: {'Superuser' if user.is_superuser else ('Staff' if user.is_staff else 'Student')}")
        print(f"    Password: {password}")
        return

    # If no flags passed, launch the interactive menu
    interactive_menu()


if __name__ == "__main__":
    main()
