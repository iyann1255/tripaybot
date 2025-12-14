# storage.py
import sqlite3
from typing import Optional, Dict, Any

DB_PATH = "data.db"

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            merchant_ref TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            method TEXT NOT NULL,
            reference TEXT,
            status TEXT NOT NULL,
            pay_url TEXT,
            qr_url TEXT,
            created_at INTEGER NOT NULL,
            paid_at INTEGER
        )
        """)
        con.commit()

def create_invoice(row: Dict[str, Any]) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            INSERT INTO invoices
            (merchant_ref, user_id, amount, method, reference, status, pay_url, qr_url, created_at, paid_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["merchant_ref"], row["user_id"], row["amount"], row["method"],
            row.get("reference"), row["status"], row.get("pay_url"), row.get("qr_url"),
            row["created_at"], row.get("paid_at")
        ))
        con.commit()

def update_invoice(merchant_ref: str, **fields) -> None:
    keys = list(fields.keys())
    if not keys:
        return
    sets = ", ".join([f"{k}=?" for k in keys])
    vals = [fields[k] for k in keys]
    vals.append(merchant_ref)

    with sqlite3.connect(DB_PATH) as con:
        con.execute(f"UPDATE invoices SET {sets} WHERE merchant_ref=?", vals)
        con.commit()

def get_invoice_by_ref(merchant_ref: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute("SELECT * FROM invoices WHERE merchant_ref=? LIMIT 1", (merchant_ref,))
        r = cur.fetchone()
        return dict(r) if r else None

def get_invoice_by_reference(reference: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute("SELECT * FROM invoices WHERE reference=? LIMIT 1", (reference,))
        r = cur.fetchone()
        return dict(r) if r else None
