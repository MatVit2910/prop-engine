import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://quant_user:quant_password@localhost:5432/nba_props_db")
    ticks_count = await conn.fetchval("SELECT COUNT(*) FROM odds_ticks;")
    signals_count = await conn.fetchval("SELECT COUNT(*) FROM trade_signals;")
    latest_signal = await conn.fetchrow("SELECT player_name, side, line, bookmaker, ev_percent, recommended_wager FROM trade_signals ORDER BY timestamp DESC LIMIT 1;")

    print(f"📊 TimescaleDB Total Odds Ticks Logged: {ticks_count}")
    print(f"🔥 TimescaleDB Total Trade Signals Logged: {signals_count}")
    if latest_signal:
        print(f"⚡ Latest Logged Signal: {latest_signal['player_name']} {latest_signal['side']} {latest_signal['line']} @ {latest_signal['bookmaker']} | EV: {latest_signal['ev_percent']*100:.2f}% | Wager: ${latest_signal['recommended_wager']}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
