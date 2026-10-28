"""FastAPI application for the book-price-tracker web dashboard."""

import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from ..reports import changes, chart_history
from ..storage import Store

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app(db_path: str = "book_data.db") -> FastAPI:
    app = FastAPI(title="Book Price Tracker Dashboard", docs_url="/docs")

    def get_store() -> Store:
        return Store(db_path)

    @app.get("/", response_class=HTMLResponse)
    async def overview_page(request: Request) -> Any:
        store = get_store()
        try:
            rows = store.all_latest()
            snapshots = store.snapshots()
            total = len(rows)
            in_stock = sum(1 for r in rows if r["in_stock"])
            out_of_stock = total - in_stock
            cats = {r["category"] for r in rows if r["category"]}
            prices = [float(r["price"]) for r in rows] if rows else []
            last_run = snapshots[-1] if snapshots else None

            return templates.TemplateResponse(
                request=request,
                name="overview.html",
                context={
                    "total_books": total,
                    "in_stock": in_stock,
                    "out_of_stock": out_of_stock,
                    "categories_count": len(cats),
                    "snapshots_count": len(snapshots),
                    "last_run": last_run,
                    "price_range": (min(prices), max(prices)) if prices else None,
                },
            )
        finally:
            store.close()

    @app.get("/books", response_class=HTMLResponse)
    async def books_page(
        request: Request,
        q: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
        rating: int | None = None,
    ) -> Any:
        store = get_store()
        try:
            rows = store.all_latest()
            all_cats = sorted({r["category"] for r in rows if r["category"]})

            # Filter
            filtered = rows
            if q:
                query_lower = q.strip().lower()
                filtered = [r for r in filtered if query_lower in r["title"].lower() or query_lower in r["upc"].lower()]
            if category:
                filtered = [r for r in filtered if r["category"] and r["category"].lower() == category.lower()]
            if max_price is not None:
                filtered = [r for r in filtered if Decimal(r["price"]) <= Decimal(str(max_price))]
            if in_stock:
                filtered = [r for r in filtered if r["in_stock"]]
            if rating:
                filtered = [r for r in filtered if r["rating"] == rating]

            return templates.TemplateResponse(
                request=request,
                name="books.html",
                context={
                    "books": filtered,
                    "all_categories": all_cats,
                    "query": q or "",
                    "selected_category": category or "",
                    "max_price": max_price,
                    "in_stock_only": in_stock,
                },
            )
        finally:
            store.close()

    @app.get("/book/{upc}", response_class=HTMLResponse)
    async def book_detail_page(request: Request, upc: str) -> Any:
        store = get_store()
        try:
            row = store.db.execute("SELECT * FROM books WHERE upc = ?", (upc,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Book not found")
            book = dict(row)
            history = store.db.execute(
                "SELECT price, in_stock, scraped_at FROM price_history WHERE book_id = ? ORDER BY id DESC",
                (book["id"],),
            ).fetchall()
            latest_price = history[0]["price"] if history else "0.00"
            book["price"] = latest_price
            book["in_stock"] = bool(history[0]["in_stock"]) if history else False

            return templates.TemplateResponse(
                request=request,
                name="book_detail.html",
                context={
                    "book": book,
                    "history": [dict(h) for h in history],
                },
            )
        finally:
            store.close()

    @app.get("/changes", response_class=HTMLResponse)
    async def changes_page(request: Request) -> Any:
        store = get_store()
        try:
            chg = changes(store)
            return templates.TemplateResponse(request=request, name="changes.html", context={"chg": chg})
        finally:
            store.close()

    @app.get("/watchlist", response_class=HTMLResponse)
    async def watchlist_page(request: Request) -> Any:
        store = get_store()
        try:
            raw_items = store.get_watchlist()
            items = []
            for it in raw_items:
                book = store.db.execute("SELECT title FROM books WHERE upc = ?", (it["upc"],)).fetchone()
                history = store.db.execute(
                    "SELECT price FROM price_history WHERE book_id = (SELECT id FROM books WHERE upc = ?) ORDER BY id DESC LIMIT 1",
                    (it["upc"],),
                ).fetchone()
                latest_p = Decimal(history["price"]) if history else None
                target_met = False
                if latest_p and it["below_price"] and latest_p <= Decimal(it["below_price"]):
                    target_met = True

                items.append(
                    {
                        "upc": it["upc"],
                        "title": book["title"] if book else it["upc"],
                        "below_price": it["below_price"],
                        "drop_percent": it["drop_percent"],
                        "last_alerted_price": it["last_alerted_price"],
                        "latest_price": str(latest_p) if latest_p else None,
                        "triggered": target_met,
                    }
                )
            return templates.TemplateResponse(request=request, name="watchlist.html", context={"items": items})
        finally:
            store.close()

    @app.get("/api/chart/{upc}")
    async def book_chart_api(upc: str) -> Response:
        store = get_store()
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                chart_history(store, upc, tmp_path)
                data = tmp_path.read_bytes()
                return Response(content=data, media_type="image/png")
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        finally:
            store.close()

    @app.get("/api/overview")
    async def api_overview() -> dict[str, Any]:
        store = get_store()
        try:
            rows = store.all_latest()
            snapshots = store.snapshots()
            return {
                "total_books": len(rows),
                "in_stock": sum(1 for r in rows if r["in_stock"]),
                "last_run": snapshots[-1] if snapshots else None,
                "snapshots_count": len(snapshots),
            }
        finally:
            store.close()

    @app.get("/api/books")
    async def api_books(q: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
        store = get_store()
        try:
            rows = store.all_latest()
            if q:
                q_lower = q.lower()
                rows = [r for r in rows if q_lower in r["title"].lower() or q_lower in r["upc"].lower()]
            if category:
                rows = [r for r in rows if r["category"] and r["category"].lower() == category.lower()]
            return rows
        finally:
            store.close()

    @app.get("/api/watchlist")
    async def api_watchlist() -> list[dict[str, Any]]:
        store = get_store()
        try:
            return store.get_watchlist()
        finally:
            store.close()

    return app
