import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client
from datetime import datetime

# 初始化 Supabase 連線
SUPABASE_URL = "https://sbrmpbshsehplmavqugb.supabase.co"
SUPABASE_KEY = "sb_publishable_ajcCshEPutB7DScVokl0AQ_BVTcgWy-"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="專屬投資組合追蹤", layout="wide")
st.title("📈 投資組合與 0050 績效對決")

# 新增交易區塊
with st.sidebar:
    st.header("➕ 新增交易紀錄")
    trade_date = st.date_input("交易日期", datetime.today())
    symbol_raw = st.text_input("股票代碼 (例: 2330 或 NVDA)", "2330")
    action = st.radio("交易類型", ["BUY (買進)", "SELL (賣出)"])
    shares = st.number_input("股數", min_value=1, value=1000, step=1)
    price = st.number_input("成交單價", min_value=0.0, value=100.0, step=0.5)
    fee = st.number_input("手續費/稅", min_value=0, value=0, step=1)
    
    if st.button("儲存交易", type="primary"):
        symbol = symbol_raw.strip().upper()
        if symbol.isdigit():
            symbol = f"{symbol}.TW"
            
        data = {
            "trade_date": str(trade_date),
            "symbol": symbol,
            "action": "BUY" if "BUY" in action else "SELL",
            "shares": shares,
            "price": price,
            "fee": fee
        }
        supabase.table("transactions").insert(data).execute()
        st.success(f"成功記錄 {symbol}！")
        st.rerun()

# 讀取與呈現交易資料
try:
    response = supabase.table("transactions").select("*").execute()
    df_trades = pd.DataFrame(response.data)
except Exception as e:
    df_trades = pd.DataFrame()

if df_trades.empty:
    st.info("👋 目前尚無交易紀錄，請在左側選單新增第一筆買賣明細！")
else:
    df_trades['trade_date'] = pd.to_datetime(df_trades['trade_date'])
    st.subheader("📋 歷史交易明細")
    st.dataframe(df_trades.sort_values(by="trade_date", ascending=False), use_container_width=True)
    
    st.subheader("⚔️ 策略總資產 vs 同期 0050 對決曲線")
    min_date = df_trades['trade_date'].min()
    unique_symbols = list(set(df_trades['symbol'].tolist() + ['0050.TW']))
    prices_df = yf.download(unique_symbols, start=min_date, progress=False)['Close']
    
    if not prices_df.empty:
        daily_portfolio = []
        for curr_date in prices_df.index:
            sub_trades = df_trades[df_trades['trade_date'] <= curr_date]
            real_val = 0
            bm_shares = 0
            for _, row in sub_trades.iterrows():
                sym = row['symbol']
                sign = 1 if row['action'] == 'BUY' else -1
                if sym in prices_df.columns and not pd.isna(prices_df.loc[curr_date, sym]):
                    real_val += sign * row['shares'] * prices_df.loc[curr_date, sym]
                if '0050.TW' in prices_df.columns and not pd.isna(prices_df.loc[curr_date, '0050.TW']):
                    trade_cost = row['shares'] * row['price']
                    p_0050 = prices_df.loc[row['trade_date'], '0050.TW'] if row['trade_date'] in prices_df.index else prices_df['0050.TW'].iloc[0]
                    if p_0050 > 0:
                        bm_shares += sign * (trade_cost / p_0050)
            bm_val = bm_shares * prices_df.loc[curr_date, '0050.TW'] if '0050.TW' in prices_df.columns else 0
            daily_portfolio.append({
                "Date": curr_date,
                "你的投資組合市值": max(0, real_val),
                "0050 對照組市值": max(0, bm_val)
            })
        chart_df = pd.DataFrame(daily_portfolio).set_index("Date")
        st.line_chart(chart_df)
