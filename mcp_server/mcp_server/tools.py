from dataclasses import dataclass


@dataclass
class PartStatus:
    part_id: str
    name: str
    qty_on_hand: int
    reorder_threshold: int
    status: str


def check_stock(collection, part_id: str) -> PartStatus:
    doc = collection.find_one({"part_id": part_id})
    if doc is None:
        raise ValueError(f"Unknown part_id: {part_id}")

    qty = doc["qty_on_hand"]
    threshold = doc["reorder_threshold"]
    if qty <= 0:
        status = "out_of_stock"
    elif qty <= threshold:
        status = "low_stock"
    else:
        status = "in_stock"

    return PartStatus(
        part_id=doc["part_id"],
        name=doc["name"],
        qty_on_hand=qty,
        reorder_threshold=threshold,
        status=status,
    )
