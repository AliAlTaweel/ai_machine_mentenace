import sys

from mcp_server.db import get_inventory_collection
from mcp_server.seed_data import seed
from mcp_server.server import mcp


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "seed":
        collection = get_inventory_collection()
        count = seed(collection)
        print(f"Seeded {count} parts into the inventory collection.")
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
