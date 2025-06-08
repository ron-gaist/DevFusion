#!/usr/bin/env python
import os
import sys
import argparse
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/devfusion"
)


def get_alembic_config():
    """Get Alembic configuration."""
    config = Config()
    config.set_main_option("script_location", "migrations")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def get_current_revision():
    """Get current database revision."""
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()


def get_head_revision():
    """Get head revision from migrations."""
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def check_database_connection():
    """Check if database is accessible."""
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return False


def create_migration(message):
    """Create a new migration."""
    if not check_database_connection():
        return False

    config = get_alembic_config()
    command.revision(config, message=message, autogenerate=True)
    return True


def upgrade_database(revision="head"):
    """Upgrade database to specified revision."""
    if not check_database_connection():
        return False

    config = get_alembic_config()
    command.upgrade(config, revision)
    return True


def downgrade_database(revision):
    """Downgrade database to specified revision."""
    if not check_database_connection():
        return False

    config = get_alembic_config()
    command.downgrade(config, revision)
    return True


def show_migration_status():
    """Show current migration status."""
    if not check_database_connection():
        return False

    current = get_current_revision()
    head = get_head_revision()

    print("\nMigration Status:")
    print(f"Current revision: {current}")
    print(f"Head revision: {head}")
    print(f"Status: {'Up to date' if current == head else 'Out of date'}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Manage database migrations")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create migration command
    create_parser = subparsers.add_parser("create", help="Create a new migration")
    create_parser.add_argument("message", help="Migration message")

    # Upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade database")
    upgrade_parser.add_argument("--revision", default="head", help="Target revision")

    # Downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Downgrade database")
    downgrade_parser.add_argument("revision", help="Target revision")

    # Status command
    subparsers.add_parser("status", help="Show migration status")

    args = parser.parse_args()

    if args.command == "create":
        success = create_migration(args.message)
    elif args.command == "upgrade":
        success = upgrade_database(args.revision)
    elif args.command == "downgrade":
        success = downgrade_database(args.revision)
    elif args.command == "status":
        success = show_migration_status()
    else:
        parser.print_help()
        sys.exit(1)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
