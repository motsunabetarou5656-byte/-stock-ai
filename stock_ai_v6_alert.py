#!/usr/bin/env python3
# Stock AI v6 — Daily Buy Alert
# No system can guarantee profits. This tool ranks watchlist stocks and flags
# conditions that may warrant a manual review.

from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf

ROOT = Path(__file__).resolve().parent
WATCHLIST = ROOT / "watchlist.csv"
ALERTS = ROOT / "alerts.csv"
REPORT = ROOT / "daily_report.html"

BUY_SCORE = 78
STRONG_BUY_SCORE = 85
DIVIDEND_YIELD = 0.035
MA200_DISCOUNT = 0.97
DRAWDOWN = -0.15

def safe_num(x):
    try:
        return float(x)
    except:
        return np.nan

def one(ticker):
    tk = yf.Ticker(ticker)
    hist = tk.history(period="1y", auto_adjust=False)
    if hist.empty:
        return None

    close = hist["Close"].dropna()
    price = safe_num(close.iloc[-1])
    ma200 = safe_num(close.rolling(200).mean().iloc[-1])
    ma50 = safe_num(close.rolling(50).mean().iloc[-1])
    high_1y = safe_num(close.max())
    ret_1m = safe_num(price / close.iloc[-22] - 1) if len(close) >= 22 else np.nan
    ret_6m = safe_num(price / close.iloc[-126] - 1) if len(close) >= 126 else np.nan
    dd = safe_num(price / high_1y - 1)

    info = {}
    try:
        info = tk.info
    except:
        pass

    div_yield = safe_num(info.get("dividendYield"))
    if not np.isnan(div_yield) and div_yield > 1:
        div_yield /= 100

    pe = safe_num(info.get("trailingPE"))
    roe = safe_num(info.get("returnOnEquity"))
    margin = safe_num(info.get("profitMargins"))
    debt = safe_num(info.get("debtToEquity"))

    score = 50.0
    reasons = []

    # Trend / price zone
    if not np.isnan(ma200):
        if price <= ma200 * MA200_DISCOUNT:
            score += 12; reasons.append("200日線より7%以上下")
        elif price < ma200:
            score += 6; reasons.append("200日線より下")
        elif price > ma200:
            score -= 2

    if not np.isnan(ma50) and not np.isnan(ma200) and ma50 > ma200:
        score += 5; reasons.append("50日線>200日線")

    if not np.isnan(dd) and dd <= DRAWDOWN:
        score += 8; reasons.append("高値から15%以上下落")

    # Dividend
    if not np.isnan(div_yield):
        if div_yield >= 0.05:
            score += 12; reasons.append("配当利回り5%以上")
        elif div_yield >= DIVIDEND_YIELD:
            score += 7; reasons.append("配当利回り3.5%以上")
        elif div_yield > 0:
            score += 2

    # Quality
    if not np.isnan(roe):
        if roe >= 0.15: score += 7; reasons.append("ROE15%以上")
        elif roe >= 0.10: score += 3

    if not np.isnan(margin):
        if margin >= 0.10: score += 5; reasons.append("利益率10%以上")

    # Valuation
    if not np.isnan(pe):
        if 0 < pe <= 12: score += 8; reasons.append("PER12倍以下")
        elif 0 < pe <= 18: score += 4
        elif pe >= 35: score -= 8; reasons.append("PER35倍以上")

    # Balance sheet
    if not np.isnan(debt):
        if debt <= 50: score += 5; reasons.append("D/E50以下")
        elif debt >= 150: score -= 5; reasons.append("D/E150以上")

    score = max(0, min(100, round(score,1)))

    if score >= STRONG_BUY_SCORE:
        signal = "強い買い候補"
    elif score >= BUY_SCORE:
        signal = "買い候補"
    elif score >= 65:
        signal = "監視"
    else:
        signal = "待機"

    if not np.isnan(div_yield) and div_yield >= 0.08:
        reasons.append("高配当のため減配・一時要因を要確認")

    return {
        "Ticker": ticker,
        "Price": round(price,2),
        "Score": score,
        "Signal": signal,
        "DividendYield": round(div_yield*100,2) if not np.isnan(div_yield) else np.nan,
        "PER": round(pe,2) if not np.isnan(pe) else np.nan,
        "ROE": round(roe*100,2) if not np.isnan(roe) else np.nan,
        "1M_Return": round(ret_1m*100,2) if not np.isnan(ret_1m) else np.nan,
        "6M_Return": round(ret_6m*100,2) if not np.isnan(ret_6m) else np.nan,
        "Drawdown": round(dd*100,2) if not np.isnan(dd) else np.nan,
        "Reasons": " / ".join(reasons[:6])
    }

def main():
    if not WATCHLIST.exists():
        pd.DataFrame({"Ticker":["8058.T","9432.T","AAPL","MSFT"]}).to_csv(WATCHLIST,index=False)
        print("watchlist.csv を作成しました。銘柄を追加して再実行してください。")
        return

    wl = pd.read_csv(WATCHLIST)
    rows=[]
    for ticker in wl["Ticker"].dropna().astype(str):
        try:
            r=one(ticker.strip())
            if r: rows.append(r)
        except Exception as e:
            print("SKIP", ticker, e)

    df=pd.DataFrame(rows)
    if df.empty:
        print("データを取得できませんでした。")
        return

    df=df.sort_values(["Score","DividendYield"], ascending=[False,False])
    df.to_csv(ALERTS,index=False,encoding="utf-8-sig")

    now=datetime.now().strftime("%Y-%m-%d %H:%M")
    alerts=df[df["Score"]>=BUY_SCORE].copy()

    html=f"""<!doctype html><html lang='ja'><head><meta charset='utf-8'>
    <title>Stock AI v6 Daily Report</title>
    <style>body{{font-family:system-ui,sans-serif;margin:30px}}table{{border-collapse:collapse;width:100%}}
    th,td{{border:1px solid #ddd;padding:7px;text-align:right}}th{{background:#f3f3f3}}
    td:first-child,td:nth-child(4),td:last-child{{text-align:left}}</style></head><body>
    <h1>Stock AI v6 — Daily Report</h1><p>更新: {now}</p>
    <p><b>買い候補: {len(alerts)}銘柄</b> / 監視対象: {len(df)}銘柄</p>
    {df.to_html(index=False,float_format=lambda x:f"{x:.2f}" if isinstance(x,(float,np.floating)) else str(x))}
    <h2>注意</h2><p>これは売買推奨ではなく、確認対象を絞るためのスクリーナーです。高配当銘柄は減配・特別配当・一時的要因も確認してください。</p>
    </body></html>"""
    REPORT.write_text(html,encoding="utf-8")
    print(f"完了: {ALERTS.name}, {REPORT.name}")

if __name__=="__main__":
    main()
