"""API de ejemplo de pedidos para experimentar en la sandbox Crixol."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE = DATA_DIR / "orders.db"

app = FastAPI(title="Crixol - API de pedidos", version="1.0.0")


class OrderInput(BaseModel):
    customer: str = Field(min_length=2, max_length=100)
    total: float = Field(gt=0)


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database() -> None:
    with connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT NOT NULL,
                total REAL NOT NULL,
                created_at TEXT NOT NULL,
                deleted_at TEXT NULL
            )"""
        )
        count = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            db.executemany(
                "INSERT INTO orders (customer, total, created_at) VALUES (?, ?, ?)",
                [
                    ("Ada Lovelace", 120.50, now),
                    ("Grace Hopper", 89.90, now),
                    ("Alan Turing", 245.00, now),
                ],
            )


@app.on_event("startup")
def on_startup() -> None:
    initialise_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/orders")
def list_orders(include_deleted: bool = Query(default=False)) -> list[dict]:
    sql = "SELECT * FROM orders"
    if not include_deleted:
        sql += " WHERE deleted_at IS NULL"
    sql += " ORDER BY id"
    with connect() as db:
        return [dict(row) for row in db.execute(sql).fetchall()]


@app.get("/orders/{order_id}")
def get_order(order_id: int) -> dict:
    with connect() as db:
        row = db.execute(
            "SELECT * FROM orders WHERE id = ? AND deleted_at IS NULL", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return dict(row)


@app.post("/orders", status_code=201)
def create_order(payload: OrderInput) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO orders (customer, total, created_at) VALUES (?, ?, ?)",
            (payload.customer, payload.total, now),
        )
        order_id = cursor.lastrowid
        row = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return dict(row)


@app.delete("/orders/{order_id}")
def delete_order(order_id: int) -> dict[str, bool]:
    """Elimina físicamente el pedido. Puede modificarse para implementar borrado lógico."""
    with connect() as db:
        cursor = db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {"deleted": True}