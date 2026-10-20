"""Snapshot comparisons, exports, and simple price charts."""
from decimal import Decimal
from pathlib import Path
from .storage import Store


def changes(store: Store) -> dict[str, list]:
    snapshots = store.snapshots()
    if len(snapshots) < 2: return {k: [] for k in ("new", "removed", "increases", "drops", "back_in_stock", "out_of_stock")}
    old, new = store.snapshot(snapshots[-2]), store.snapshot(snapshots[-1])
    result = {k: [] for k in ("new", "removed", "increases", "drops", "back_in_stock", "out_of_stock")}
    result["new"] = sorted(set(new) - set(old)); result["removed"] = sorted(set(old) - set(new))
    for upc in set(old) & set(new):
        before, after = old[upc], new[upc]
        if Decimal(after["price"]) > Decimal(before["price"]): result["increases"].append((upc, before["price"], after["price"]))
        if Decimal(after["price"]) < Decimal(before["price"]): result["drops"].append((upc, before["price"], after["price"]))
        if not before["in_stock"] and after["in_stock"]: result["back_in_stock"].append(upc)
        if before["in_stock"] and not after["in_stock"]: result["out_of_stock"].append(upc)
    return result


def chart_history(store: Store, upc: str, output: str | Path) -> Path:
    import matplotlib.pyplot as plt
    row = store.db.execute("SELECT id FROM books WHERE upc=?", (upc,)).fetchone()
    if not row: raise ValueError(f"Unknown UPC: {upc}")
    points = store.db.execute("SELECT scraped_at,price FROM price_history WHERE book_id=? ORDER BY scraped_at,id", (row[0],)).fetchall()
    path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(); plt.plot([p[0] for p in points], [float(p[1]) for p in points], marker="o")
    plt.xticks(rotation=30, ha="right"); plt.ylabel("Price"); plt.title(f"Price history: {upc}"); plt.tight_layout(); plt.savefig(path); plt.close()
    return path
