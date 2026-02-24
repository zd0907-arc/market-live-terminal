from backend.app.db.crud import get_db_connection

def cleanup_invalid_dates():
    # Remove data incorrectly generated over the past weekend/holidays
    invalid_dates = [
        "2026-02-14", "2026-02-15", "2026-02-16", 
        "2026-02-17", "2026-02-18", "2026-02-19",
        "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23"
    ]
    conn = get_db_connection()
    c = conn.cursor()
    
    for date in invalid_dates:
        c.execute("DELETE FROM sentiment_snapshots WHERE date = ?", (date,))
        c.execute("DELETE FROM trade_ticks WHERE date = ?", (date,))
        c.execute("DELETE FROM local_history WHERE date = ?", (date,))
        c.execute("DELETE FROM history_30m WHERE substr(start_time, 1, 10) = ?", (date,))
        
    conn.commit()
    conn.close()
    print("Cleanup completed.")

if __name__ == "__main__":
    cleanup_invalid_dates()
