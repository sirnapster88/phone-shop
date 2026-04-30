from pathlib import Path

from .models import AggregatedProduct


PRICE_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "price.txt"


def _load_seed_rows_from_price_file():
    from .parser import TextPriceParser

    if not PRICE_TEMPLATE_PATH.exists():
        return []

    text = PRICE_TEMPLATE_PATH.read_text(encoding="utf-8")
    parsed_items = TextPriceParser(text).parse()
    rows = []
    seen = set()

    for item in parsed_items:
        row = {
            "category": item.get("category", "") or "",
            "brand": item.get("brand", "") or "",
            "model": item.get("model", "") or "",
            "color": item.get("color", "") or "",
            "memory": item.get("memory", "") or "",
            "region": item.get("region", "") or "",
            "sim_type": item.get("sim_type", "") or "",
            "specs": item.get("specs", "") or "",
        }

        if not row["model"]:
            continue

        row_key = tuple(row.values())
        if row_key in seen:
            continue

        seen.add(row_key)
        rows.append(row)

    return rows


def seed_default_catalog():
    seed_rows = _load_seed_rows_from_price_file()
    created_count = 0

    for row in seed_rows:
        _, created = AggregatedProduct.objects.get_or_create(**row)
        if created:
            created_count += 1

    return {
        "created": created_count,
        "total_seed_rows": len(seed_rows),
        "total_models": AggregatedProduct.objects.count(),
        "source_file": str(PRICE_TEMPLATE_PATH),
    }
