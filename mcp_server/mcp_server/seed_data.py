SAMPLE_PARTS = [
    {
        "part_id": "BEARING-X4",
        "name": "Bearing X4",
        "qty_on_hand": 12,
        "reorder_threshold": 5,
        "machine_types": ["CNC-Mill-200"],
    },
    {
        "part_id": "BELT-A7",
        "name": "Conveyor Belt A7",
        "qty_on_hand": 2,
        "reorder_threshold": 3,
        "machine_types": ["Conveyor-Belt-A7"],
    },
    {
        "part_id": "VALVE-H9",
        "name": "Hydraulic Valve H9",
        "qty_on_hand": 0,
        "reorder_threshold": 2,
        "machine_types": ["Hydraulic-Press-9"],
    },
    {
        "part_id": "MOTOR-C2",
        "name": "Drive Motor C2",
        "qty_on_hand": 4,
        "reorder_threshold": 1,
        "machine_types": ["CNC-Mill-200", "Conveyor-Belt-A7"],
    },
    {
        "part_id": "SEAL-K1",
        "name": "Hydraulic Seal Kit K1",
        "qty_on_hand": 1,
        "reorder_threshold": 2,
        "machine_types": ["Hydraulic-Press-9"],
    },
]


def seed(collection, parts: list[dict] = SAMPLE_PARTS) -> int:
    count = 0
    for part in parts:
        collection.update_one(
            {"part_id": part["part_id"]},
            {"$set": part},
            upsert=True,
        )
        count += 1
    return count
