import streamlit as st
import pandas as pd
import yfinance as yf
import altair as alt
from supabase import create_client, Client
from datetime import datetime

# 初始化 Supabase 連線
SUPABASE_URL = "https://sbrmpbshsehplmavqugb.supabase.co"
SUPABASE_KEY = "sb_publishable_ajcCshEPutB7DScVokl0AQ_BVTcgWy-"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="專屬投資組合追蹤", layout="wide")
st.title("📈 投資組合與 0050 績效對決")

# 左側側邊欄：新增與刪除交易
with st.sidebar:
    st.header("➕ 新增交易紀錄")
    trade_date = st.date_input("交易日期", datetime.today())
    symbol_raw = st.text_input("股票代碼 (例: 2330 或 NVDA)", "2330")
    action = st.radio("交易類型", ["買進 (BUY)", "賣出 (SELL)"])
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
            "action": "BUY" if "買進" in action else "SELL",
            "shares": shares,
            "price": price,
            "fee": fee
        }
        supabase.table("transactions").insert(data).execute()
        st.success(f"成功記錄 {symbol}！")
        st.rerun()

# 讀取交易資料
try:
    response = supabase.table("transactions").select("*").execute()
    df_trades = pd.DataFrame(response.data)
except Exception as e:
    df_trades = pd.DataFrame()

if df_trades.empty:
    st.info("👋 目前尚無交易紀錄，請在左側選單新增第一筆買賣明細！")
else:
    df_trades['trade_date'] = pd.to_datetime(df_trades['trade_date'])
    
    # 刪除交易區塊
    with st.sidebar:
        st.markdown("---")
        st.header("🗑️ 刪除交易紀錄")
        df_trades['delete_label'] = df_trades.apply(
            lambda r: f"編號:{r['id']} | {r['trade_date'].strftime('%Y-%m-%d')} | {r['symbol']} | {'買進' if r['action']=='BUY' else '賣出'} {r['shares']}股", axis=1
        )
        selected_to_delete = st.selectbox("選擇要刪除的交易紀錄", df_trades['delete_label'].tolist())
        
        if st.button("確認刪除此筆紀錄", type="secondary"):
            target_id = int(selected_to_delete.split("|")[0].replace("編號:", "").strip())
            supabase.table("transactions").delete().eq("id", target_id).execute()
            st.success("成功刪除紀錄！")
            st.rerun()

    # 1. 歷史交易明細表格全中文化
    st.subheader("📋 歷史交易明細")
    df_display = df_trades.copy()
    df_display['action'] = df_display['action'].map({'BUY': '買進', 'SELL': '賣出'})
    df_display['created_at'] = pd.to_datetime(df_display['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    df_display['trade_date'] = df_display['trade_date'].dt.strftime('%Y-%m-%d')
    
    # 重命名為繁體中文欄位頭
    df_display = df_display.rename(columns={
        'id': '交易編號',
        'created_at': '建立時間',
        'trade_date': '交易日期',
        'symbol': '股票代碼',
        'action': '交易類型',
        'shares': '股數',
        'price': '成交單價',
        'fee': '手續費/稅'
    })
    
    show_cols = ['交易編號', '交易日期', '股票代碼', '交易類型', '股數', '成交單價', '手續費/稅', '建立時間']
    st.dataframe(df_display[show_cols].sort_values(by="交易日期", ascending=False), use_container_width=True)
    
    # 2. 折線圖與 X 軸時間全中文化 (使用 Altair 繪圖引擎)
    st.subheader("⚔️ 策略總資產 vs 同期 0050 對決曲線")
    min_date = df_trades['trade_date'].min() - pd.Timedelta(days=7)
    unique_symbols = list(set(df_trades['symbol'].tolist() + ['0050.TW']))
    
    with st.spinner("正在抓取最新歷史股價計算中..."):
        prices_df = yf.download(unique_symbols, start=min_date, progress=False)['Close']
        if isinstance(prices_df, pd.Series):
            prices_df = prices_df.to_frame()
            
    if not prices_df.empty:
        prices_df = prices_df.ffill().bfill()
        
        daily_portfolio = []
        for curr_date in prices_df.index:
            if curr_date < df_trades['trade_date'].min():
                continue
                
            sub_trades = df_trades[df_trades['trade_date'] <= curr_date]
            real_val = 0
            bm_shares = 0
            
            for _, row in sub_trades.iterrows():
                sym = row['symbol']
                sign = 1 if row['action'] == 'BUY' else -1
                
                if sym in prices_df.columns and not pd.isna(prices_df.loc[curr_date, sym]):
                    real_val += sign * row['shares'] * prices_df.loc[curr_date, sym]
                
                if '0050.TW' in prices_df.columns:
                    trade_cost = row['shares'] * row['price']
                    t_date = row['trade_date']
                    if t_date in prices_df.index:
                        p_0050 = prices_df.loc[t_date, '0050.TW']
                    else:
                        p_0050 = prices_df['0050.TW'].asof(t_date)
                        
                    if pd.notna(p_0050) and p_0050 > 0:
                        bm_shares += sign * (trade_cost / p_0050)
            
            bm_val = bm_shares * prices_df.loc[curr_date, '0050.TW'] if '0050.TW' in prices_df.columns else 0
            
            daily_portfolio.append({
                "日期": curr_date,
                "你的投資組合市值": max(0, real_val),
                "0050 對照組市值": max(0, bm_val)
            })
            
        chart_df = pd.DataFrame(daily_portfolio)
        chart_melted = chart_df.melt(id_vars=['日期'], var_name='項目', value_name='市值(元)')
        
        # 繪製繁體中文時間格式 (X 軸格式設定為中文日期月/日)
        chart = alt.Chart(chart_melted).mark_line().encode(
            x=alt.X('日期:T', title='日期', axis=alt.Axis(format='%m月%d日', labelAngle=0)),
            y=alt.Y('市值(元):Q', title='總市值 (NTD)'),
            color=alt.Color('項目:N', title='類別')
        ).properties(
            height=400
        ).interactive()
        
        st.altair_chart(chart, use_container_width=True)
