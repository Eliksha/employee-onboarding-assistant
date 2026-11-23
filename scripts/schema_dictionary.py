"""Check the schema dictionary against a PostgreSQL database (read-only catalog queries).

Usage (repository root, PG_* settings pointing at the database to check):
  python -m scripts.schema_dictionary --check        # exit 1 and list differences if they do not match
  python -m scripts.schema_dictionary --print        # print the tables and relationships
"""
import argparse
import sys

from backend.services import schema_dictionary as sd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print", action="store_true", dest="show")
    args = parser.parse_args(argv)
    if args.show or not args.check:
        for name, table in sd.tables().items():
            print(f"{name}: {table['description']} (PK {', '.join(table['primary_key'])})")
        for rel in sd.relationships():
            print(f"  {rel['from_table']}({', '.join(rel['from_columns'])}) -> "
                  f"{rel['to_table']}({', '.join(rel['to_columns'])})")
    if not args.check:
        return 0
    from backend.services.postgres import postgres_connection

    with postgres_connection() as conn:
        conn.set_session(readonly=True)
        problems = sd.diff(sd.tables(), sd.introspect(conn))
    print("\n".join(problems) if problems else "Schema dictionary matches the database.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
