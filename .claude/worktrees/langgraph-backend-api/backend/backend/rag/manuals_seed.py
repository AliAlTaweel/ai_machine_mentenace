from backend.rag.embeddings import embed_text

SAMPLE_MANUALS = [
    {
        "manual_id": "CNC-MILL-200-E101",
        "machine_type": "CNC-Mill-200",
        "error_codes": ["E101"],
        "chunk_text": (
            "Error E101 on the CNC-Mill-200 indicates main spindle bearing wear, "
            "usually presenting as excessive vibration and a grinding noise above "
            "2000 RPM. Diagnosis: inspect the main spindle bearing (part BEARING-X4) "
            "for pitting or discoloration. Repair: power down the mill, remove the "
            "spindle housing cover, replace the worn bearing with BEARING-X4, "
            "repack with the specified grease, and reassemble. Run a 10-minute "
            "no-load test before returning to production."
        ),
    },
    {
        "manual_id": "CNC-MILL-200-E204",
        "machine_type": "CNC-Mill-200",
        "error_codes": ["E204"],
        "chunk_text": (
            "Error E204 on the CNC-Mill-200 signals drive motor overcurrent, "
            "typically caused by a failing drive motor (part MOTOR-C2) under load. "
            "Diagnosis: check motor winding resistance and look for overheating "
            "discoloration on the housing. Repair: isolate power, remove the drive "
            "motor assembly, replace with MOTOR-C2, and verify current draw is "
            "within spec before resuming operation."
        ),
    },
    {
        "manual_id": "CONVEYOR-A7-B12",
        "machine_type": "Conveyor-Belt-A7",
        "error_codes": ["B12"],
        "chunk_text": (
            "Error B12 on the Conveyor-Belt-A7 indicates belt slippage or tearing, "
            "usually from a worn conveyor belt (part BELT-A7). Diagnosis: inspect "
            "the belt surface for fraying, cracking, or uneven wear along the edges. "
            "Repair: release belt tension, remove the worn belt, install a "
            "replacement BELT-A7, and re-tension to the manufacturer's spec before "
            "restarting."
        ),
    },
    {
        "manual_id": "CONVEYOR-A7-B20",
        "machine_type": "Conveyor-Belt-A7",
        "error_codes": ["B20"],
        "chunk_text": (
            "Error B20 on the Conveyor-Belt-A7 indicates drive motor stall, often "
            "caused by the same drive motor part (MOTOR-C2) used on the CNC-Mill-200. "
            "Diagnosis: check for excessive load or jammed rollers before assuming a "
            "motor fault. Repair: clear any jam first; if the stall persists, replace "
            "the drive motor with MOTOR-C2."
        ),
    },
    {
        "manual_id": "HYDRAULIC-PRESS-9-H33",
        "machine_type": "Hydraulic-Press-9",
        "error_codes": ["H33"],
        "chunk_text": (
            "Error H33 on the Hydraulic-Press-9 indicates loss of hydraulic pressure, "
            "commonly from a failed hydraulic valve (part VALVE-H9) or a worn seal kit "
            "(part SEAL-K1). Diagnosis: check for visible fluid leaks around the valve "
            "body and seals first. Repair: if the valve is leaking internally, replace "
            "VALVE-H9; if the leak is at a seal interface, replace the seal kit SEAL-K1. "
            "Bleed the hydraulic system and verify pressure holds before returning to "
            "service."
        ),
    },
]


def seed_manuals(collection, embed_fn=embed_text, manuals: list[dict] = SAMPLE_MANUALS) -> int:
    count = 0
    for manual in manuals:
        collection.update_one(
            {"manual_id": manual["manual_id"]},
            {
                "$set": {
                    "manual_id": manual["manual_id"],
                    "machine_type": manual["machine_type"],
                    "error_codes": manual["error_codes"],
                    "chunk_text": manual["chunk_text"],
                    "embedding": embed_fn(manual["chunk_text"]),
                }
            },
            upsert=True,
        )
        count += 1
    return count
