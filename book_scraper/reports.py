"""Snapshot comparisons, exports, statistics, and charts."""

from decimal import Decimal
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .storage import Store


def changes(store: Store) -> dict[str, list]:
    snapshots = store.snapshots()
    if len(snapshots) < 2:
        return {k: [] for k in ("new", "removed", "increases", "drops", "back_in_stock", "out_of_stock")}
    old, new = store.snapshot(snapshots[-2]), store.snapshot(snapshots[-1])
    result: dict[str, list[Any]] = {
        k: [] for k in ("new", "removed", "increases", "drops", "back_in_stock", "out_of_stock")
    }
    result["new"] = sorted(set(new) - set(old))
    result["removed"] = sorted(set(old) - set(new))
    for upc in set(old) & set(new):
        before, after = old[upc], new[upc]
        if Decimal(after["price"]) > Decimal(before["price"]):
            result["increases"].append((upc, before["price"], after["price"]))
        if Decimal(after["price"]) < Decimal(before["price"]):
            result["drops"].append((upc, before["price"], after["price"]))
        if not before["in_stock"] and after["in_stock"]:
            result["back_in_stock"].append(upc)
        if before["in_stock"] and not after["in_stock"]:
            result["out_of_stock"].append(upc)
    return result


def get_stats(store: Store) -> dict[str, Any]:
    """Calculate detailed statistics: totals, price distribution, category counts, and largest price changes."""
    rows = store.all_latest()
    total = len(rows)
    if not total:
        return {
            "total_books": 0,
            "in_stock": 0,
            "out_of_stock": 0,
            "price_min": 0.0,
            "price_max": 0.0,
            "price_avg": 0.0,
            "distribution": {},
            "categories": {},
            "largest_increases": [],
            "largest_decreases": [],
        }

    prices = [float(r["price"]) for r in rows]
    in_stock_cnt = sum(1 for r in rows if r["in_stock"])
    out_of_stock_cnt = total - in_stock_cnt

    # Distribution buckets
    buckets = {"< £10": 0, "£10 - £20": 0, "£20 - £30": 0, "£30 - £40": 0, "£40 - £50": 0, "£50+": 0}
    for p in prices:
        if p < 10:
            buckets["< £10"] += 1
        elif p < 20:
            buckets["£10 - £20"] += 1
        elif p < 30:
            buckets["£20 - £30"] += 1
        elif p < 40:
            buckets["£30 - £40"] += 1
        elif p < 50:
            buckets["£40 - £50"] += 1
        else:
            buckets["£50+"] += 1

    # Counts per category
    cat_counts: dict[str, int] = {}
    for r in rows:
        cat = r["category"] or "Uncategorized"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    sorted_cats = dict(sorted(cat_counts.items(), key=lambda kv: kv[1], reverse=True))

    # Price changes between last 2 runs
    chg = changes(store)
    increases = []
    for upc, before, after in chg["increases"]:
        diff = float(Decimal(after) - Decimal(before))
        pct = float((Decimal(after) - Decimal(before)) / Decimal(before) * 100)
        book_info = store.db.execute("SELECT title FROM books WHERE upc = ?", (upc,)).fetchone()
        title = book_info["title"] if book_info else upc
        increases.append({"upc": upc, "title": title, "old": before, "new": after, "diff": diff, "pct": pct})
    increases.sort(key=lambda x: x["diff"], reverse=True)

    decreases = []
    for upc, before, after in chg["drops"]:
        diff = float(Decimal(before) - Decimal(after))
        pct = float((Decimal(before) - Decimal(after)) / Decimal(before) * 100)
        book_info = store.db.execute("SELECT title FROM books WHERE upc = ?", (upc,)).fetchone()
        title = book_info["title"] if book_info else upc
        decreases.append({"upc": upc, "title": title, "old": before, "new": after, "diff": diff, "pct": pct})
    decreases.sort(key=lambda x: x["diff"], reverse=True)

    return {
        "total_books": total,
        "in_stock": in_stock_cnt,
        "out_of_stock": out_of_stock_cnt,
        "price_min": min(prices),
        "price_max": max(prices),
        "price_avg": sum(prices) / total,
        "distribution": buckets,
        "categories": sorted_cats,
        "largest_increases": increases[:5],
        "largest_decreases": decreases[:5],
    }


def format_stats(stats: dict[str, Any]) -> str:
    """Format statistics dictionary into a clean readable string."""
    if stats["total_books"] == 0:
        return "No books tracked in the database."

    lines = [
        "======================= Price Tracker Statistics =======================",
        f"Books Tracked: {stats['total_books']} (In Stock: {stats['in_stock']}, Out of Stock: {stats['out_of_stock']})",
        f"Price Range:   £{stats['price_min']:.2f} to £{stats['price_max']:.2f} (Average: £{stats['price_avg']:.2f})",
        "",
        "Price Distribution:",
    ]
    for bucket, count in stats["distribution"].items():
        pct = (count / stats["total_books"]) * 100
        bar = "█" * int(pct / 4)
        lines.append(f"  {bucket:<12} {count:>4} books ({pct:>5.1f}%) {bar}")

    lines.append("")
    lines.append("Top Categories:")
    for cat, count in list(stats["categories"].items())[:8]:
        lines.append(f"  {cat:<25}: {count:>4} books")
    if len(stats["categories"]) > 8:
        lines.append(f"  ... and {len(stats['categories']) - 8} more categories")

    if stats["largest_increases"]:
        lines.append("")
        lines.append("Largest Price Increases (Between Runs):")
        for inc in stats["largest_increases"]:
            lines.append(
                f"  ↑ {inc['title'][:40]:<40} £{inc['old']} -> £{inc['new']} (+£{inc['diff']:.2f}, +{inc['pct']:.1f}%)"
            )

    if stats["largest_decreases"]:
        lines.append("")
        lines.append("Largest Price Decreases (Between Runs):")
        for dec in stats["largest_decreases"]:
            lines.append(
                f"  ↓ {dec['title'][:40]:<40} £{dec['old']} -> £{dec['new']} (-£{dec['diff']:.2f}, -{dec['pct']:.1f}%)"
            )

    lines.append("========================================================================")
    return "\n".join(lines)


def chart_history(store: Store, upc: str, output: str | Path) -> Path:
    row = store.db.execute("SELECT id FROM books WHERE upc=?", (upc,)).fetchone()
    if not row:
        raise ValueError(f"Unknown UPC: {upc}")
    points = store.db.execute(
        "SELECT scraped_at,price FROM price_history WHERE book_id=? ORDER BY scraped_at,id", (row[0],)
    ).fetchall()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure()
    plt.plot([p[0] for p in points], [float(p[1]) for p in points], marker="o")
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("Price")
    plt.title(f"Price history: {upc}")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path


def chart_aggregate(store: Store, kind: str, output: str | Path) -> Path:
    """Generate aggregate charts: category-avg, rating-vs-price, price-changes, or stock."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 6))

    if kind == "category-avg":
        rows = store.db.execute(
            """
            SELECT category, AVG(CAST(h.price AS REAL)) as avg_price
            FROM books b JOIN price_history h ON h.book_id=b.id
            WHERE h.id=(SELECT MAX(id) FROM price_history WHERE book_id=b.id)
              AND category != ''
            GROUP BY category
            ORDER BY avg_price DESC
            LIMIT 15
            """
        ).fetchall()
        if not rows:
            plt.text(0.5, 0.5, "No category data available", ha="center")
        else:
            cats = [r["category"] for r in rows]
            avgs = [r["avg_price"] for r in rows]
            plt.barh(cats[::-1], avgs[::-1], color="skyblue")
            plt.xlabel("Average Price (£)")
            plt.title("Top Categories by Average Price")

    elif kind == "rating-vs-price":
        rows = store.db.execute(
            """
            SELECT rating, AVG(CAST(h.price AS REAL)) as avg_price, COUNT(*) as cnt
            FROM books b JOIN price_history h ON h.book_id=b.id
            WHERE h.id=(SELECT MAX(id) FROM price_history WHERE book_id=b.id)
              AND rating >= 1 AND rating <= 5
            GROUP BY rating
            ORDER BY rating
            """
        ).fetchall()
        if not rows:
            plt.text(0.5, 0.5, "No rating data available", ha="center")
        else:
            ratings = [f"{r['rating']} Stars" for r in rows]
            avgs = [r["avg_price"] for r in rows]
            plt.bar(ratings, avgs, color="coral")
            plt.ylabel("Average Price (£)")
            plt.title("Average Price by Star Rating")

    elif kind == "price-changes":
        chg = changes(store)
        items = []
        for upc, b, a in chg["increases"]:
            items.append((upc, float(Decimal(a) - Decimal(b))))
        for upc, b, a in chg["drops"]:
            items.append((upc, float(Decimal(a) - Decimal(b))))

        if not items:
            plt.text(0.5, 0.5, "No price changes between recent runs", ha="center")
        else:
            items.sort(key=lambda x: x[1])
            labels = [x[0][:10] for x in items]
            diffs = [x[1] for x in items]
            colors = ["green" if d > 0 else "crimson" for d in diffs]
            plt.bar(labels, diffs, color=colors)
            plt.axhline(0, color="gray", linestyle="--")
            plt.ylabel("Price Change (£)")
            plt.title("Price Changes Between Runs")
            plt.xticks(rotation=45, ha="right")

    elif kind == "stock":
        rows = store.db.execute(
            """
            SELECT in_stock, COUNT(*) as cnt
            FROM books b JOIN price_history h ON h.book_id=b.id
            WHERE h.id=(SELECT MAX(id) FROM price_history WHERE book_id=b.id)
            GROUP BY in_stock
            """
        ).fetchall()
        if not rows:
            plt.text(0.5, 0.5, "No stock data available", ha="center")
        else:
            labels = ["In Stock" if r["in_stock"] else "Out of Stock" for r in rows]
            counts = [r["cnt"] for r in rows]
            colors = ["mediumseagreen" if "In" in lbl else "salmon" for lbl in labels]
            plt.bar(labels, counts, color=colors, width=0.5)
            plt.ylabel("Count")
            plt.title("Stock Availability")

    else:
        raise ValueError(
            f"Unknown chart kind: {kind}. Allowed kinds: category-avg, rating-vs-price, price-changes, stock"
        )

    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    return path
