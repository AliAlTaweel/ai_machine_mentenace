import sys

from mcp_server.db import get_inventory_collection
from mcp_server.seed_data import seed
from mcp_server.server import server


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"

    if command == "seed":
        collection = get_inventory_collection()
        count = seed(collection)
        print(f"Seeded {count} parts into the inventory collection.")
        return

    if command == "serve":
        server.run(transport="stdio")
        return

    print(f"Usage: mcp-inventory-server [seed|serve]\nUnknown command: {command}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
