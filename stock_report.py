import anthropic
import yfinance as yf
import requests
import os
import json
import base64
from datetime import datetime

# API 설정
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
KAKAO_TOKEN = "P2nn3EVSP76boQ07bsO9b_3FoRYtTproAAAAAQoXIS0AAAGcn-Na4Crd4XW-Oo9G"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_USER = "insikoo"
GITHUB_REPO = "stock-report"

# 모니터링할 종목 (name: (ticker, 국내여부, 로고URL))
STOCKS = {
    "샌디스크":           ("SNDK",      False, "https://logo.clearbit.com/sandisk.com"),
    "마이크론 테크놀로지": ("MU",        False, "https://logo.clearbit.com/micron.com"),
    "SK하이닉스":         ("000660.KS", True,  "https://logo.clearbit.com/skhynix.com"),
    "현대차":             ("005380.KS", True,  "https://logo.clearbit.com/hyundai.com"),
    "팔란티어":           ("PLTR",      False, "https://logo.clearbit.com/palantir.com"),
}

def get_usd_krw():
    try:
        ticker = yf.Ticker("USDKRW=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return round(float(hist['Close'].iloc[-1]), 2)
    except:
        pass
    return None

def get_stock_data(usd_krw):
    result = []
    weekly_data = {}
    for name, (ticker, is_korean, logo) in STOCKS.items():
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="8d")
            if len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[-2])
                today_close = float(hist['Close'].iloc[-1])
                change = ((today_close - prev_close) / prev_close) * 100

                if is_korean:
                    price_str = f"{today_close:,.0f}원"
                    prev_str = f"{prev_close:,.0f}원"
                    krw_str = None
                else:
                    price_str = f"${today_close:.2f}"
                    prev_str = f"${prev_close:.2f}"
                    krw_str = f"≈ {today_close * usd_krw:,.0f}원" if usd_krw else None

                result.append({
                    "name": name, "ticker": ticker, "is_korean": is_korean,
                    "logo": logo, "price": price_str, "prev_price": prev_str,
                    "krw_price": krw_str, "change": f"{change:+.2f}%", "change_val": change,
                })
                weekly_data[name] = [float(v) for v in hist['Close'].tail(7)]
            else:
                result.append({"name": name, "ticker": ticker, "is_korean": is_korean,
                                "logo": logo, "price": "N/A", "prev_price": "N/A",
                                "krw_price": None, "change": "N/A", "change_val": 0})
                weekly_data[name] = []
        except:
            result.append({"name": name, "ticker": ticker, "is_korean": is_korean,
                           "logo": logo, "price": "N/A", "prev_price": "N/A",
                           "krw_price": None, "change": "N/A", "change_val": 0})
            weekly_data[name] = []
    return result, weekly_data

def generate_report(stock_data):
    stock_text = "\n".join([f"{s['name']} ({s['ticker']}): {s['price']} ({s['change']})" for s in stock_data])
    message = claude_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": f"""다음 오늘의 주식 데이터를 바탕으로 시황 리포트를 작성해줘.

{stock_text}

아래 형식을 반드시 지켜줘. 모든 종목을 빠짐없이 포함해야 해:

## 전체 시장 분위기
한 줄 요약

## 종목별 분석
5개 종목 각각 분석 포인트 2줄 이상

## 내일 주의사항
5개 종목 각각 주의할 점
"""}]
    )
    return message.content[0].text

def build_cards(stocks, weekly_data):
    cards = ""
    for s in stocks:
        name = s['name']
        ticker_sym = s['ticker']
        logo_url = s['logo']
        change_val = s['change_val']
        is_up = change_val >= 0
        color = "#00C896" if is_up else "#FF4D4D"
        bg_color = "rgba(0,200,150,0.08)" if is_up else "rgba(255,77,77,0.08)"
        arrow = "▲" if is_up else "▼"
        safe_id = ticker_sym.replace(".", "_").replace("=", "_")

        # 주간 그래프
        weekly = weekly_data.get(name, [])
        chart_html = ""
        if weekly and len(weekly) > 1:
            max_v = max(weekly)
            min_v = min(weekly)
            rng = max_v - min_v if max_v != min_v else 1
            w, h = 280, 60
            points = []
            for i, v in enumerate(weekly):
                x = int(i * (w / (len(weekly) - 1)))
                y = int(h - ((v - min_v) / rng) * (h - 10) - 5)
                points.append(f"{x},{y}")
            polyline = " ".join(points)
            fill_pts = f"0,{h} " + polyline + f" {w},{h}"
            chart_html = f"""
            <div class="chart-wrap">
                <svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">
                    <defs>
                        <linearGradient id="g_{safe_id}" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stop-color="{color}" stop-opacity="0.3"/>
                            <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                    <polygon points="{fill_pts}" fill="url(#g_{safe_id})"/>
                    <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
                </svg>
                <div class="chart-labels"><span>7일 전</span><span>오늘</span></div>
            </div>"""

        krw_html = f'<div class="krw-price">{s["krw_price"]}</div>' if s.get('krw_price') else ""

        cards += f"""
        <div class="stock-card" onclick="toggleDetail(this)">
            <div class="card-main">
                <div class="stock-left">
                    <div class="logo-wrap">
                        <img src="{logo_url}" alt="{name}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
                        <div class="logo-fallback" style="display:none">{ticker_sym[:2]}</div>
                    </div>
                    <div class="stock-info">
                        <div class="stock-name">{name}</div>
                        <div class="stock-ticker">{ticker_sym}</div>
                    </div>
                </div>
                <div class="stock-right">
                    <div class="stock-price">{s['price']}</div>
                    {krw_html}
                    <div class="stock-change" style="color:{color};background:{bg_color}">{arrow} {s['change']}</div>
                </div>
            </div>
            <div class="card-detail">
                <div class="price-compare">
                    <div class="price-item">
                        <span class="price-label">어제 종가</span>
                        <span class="price-value">{s['prev_price']}</span>
                    </div>
                    <div class="price-arrow">→</div>
                    <div class="price-item">
                        <span class="price-label">오늘 종가</span>
                        <span class="price-value" style="color:{color}">{s['price']}</span>
                    </div>
                </div>
                {chart_html}
            </div>
        </div>"""
    return cards

def generate_html(stock_data, report, weekly_data, usd_krw):
    today = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")

    fx_html = ""
    if usd_krw:
        fx_html = f"""
        <div class="fx-bar">
            <span class="fx-label">💱 USD/KRW</span>
            <span class="fx-value">{usd_krw:,.2f}원</span>
            <span class="fx-time">실시간</span>
        </div>"""

    global_stocks = [s for s in stock_data if not s['is_korean']]
    korean_stocks = [s for s in stock_data if s['is_korean']]
    global_cards = build_cards(global_stocks, weekly_data)
    korean_cards = build_cards(korean_stocks, weekly_data)

    report_html = ""
    for line in report.split("\n"):
        line = line.strip()
        if not line:
            report_html += "<br>"
        elif line.startswith("## ") or line.startswith("# "):
            report_html += f'<h3 class="report-section">{line.lstrip("#").strip()}</h3>'
        elif line.startswith("- ") or line.startswith("* "):
            report_html += f'<div class="report-bullet">• {line[2:]}</div>'
        elif "|" in line and "---" not in line:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if cols:
                report_html += '<div class="report-row">' + "".join(f'<span>{c}</span>' for c in cols) + '</div>'
        else:
            report_html += f'<p class="report-text">{line}</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
    <title>주식 시황 · {today}</title>
    <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0A0A0F; --surface: #13131A; --surface2: #1C1C26;
            --border: rgba(255,255,255,0.06); --text: #F0F0F5;
            --text2: #8888A0; --text3: #55556A; --accent: #6C6CFF;
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }}
        body {{ font-family:'Pretendard',-apple-system,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; padding-bottom:40px; }}
        .header {{ padding:56px 20px 20px; background:linear-gradient(180deg,rgba(108,108,255,0.12) 0%,transparent 100%); }}
        .header-top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:4px; }}
        .header-badge {{ font-size:11px; font-weight:600; color:var(--accent); background:rgba(108,108,255,0.15); padding:4px 10px; border-radius:20px; }}
        .header-date {{ font-size:12px; color:var(--text3); }}
        .header h1 {{ font-size:26px; font-weight:700; line-height:1.2; margin-top:12px; }}
        .header p {{ font-size:14px; color:var(--text2); margin-top:6px; }}
        .fx-bar {{ display:flex; align-items:center; gap:8px; margin:16px 16px 0; background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:12px 16px; }}
        .fx-label {{ font-size:12px; color:var(--text3); }}
        .fx-value {{ font-size:15px; font-weight:700; color:#FFD166; flex:1; }}
        .fx-time {{ font-size:11px; color:var(--text3); background:rgba(255,255,255,0.05); padding:2px 8px; border-radius:10px; }}
        .section-title {{ font-size:12px; font-weight:600; color:var(--text3); letter-spacing:0.08em; text-transform:uppercase; padding:24px 20px 12px; }}
        .section-badge {{ display:inline-block; font-size:10px; font-weight:700; padding:2px 7px; border-radius:6px; margin-left:6px; vertical-align:middle; }}
        .badge-global {{ background:rgba(108,108,255,0.2); color:var(--accent); }}
        .badge-korean {{ background:rgba(255,77,77,0.15); color:#FF6B6B; }}
        .stock-card {{ margin:0 16px 10px; background:var(--surface); border-radius:16px; border:1px solid var(--border); overflow:hidden; cursor:pointer; transition:transform 0.15s ease; }}
        .stock-card:active {{ transform:scale(0.98); }}
        .card-main {{ display:flex; align-items:center; justify-content:space-between; padding:16px; }}
        .stock-left {{ display:flex; align-items:center; gap:12px; }}
        .logo-wrap {{ width:42px; height:42px; border-radius:12px; overflow:hidden; background:var(--surface2); flex-shrink:0; display:flex; align-items:center; justify-content:center; }}
        .logo-wrap img {{ width:100%; height:100%; object-fit:cover; }}
        .logo-fallback {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:700; color:var(--text2); }}
        .stock-name {{ font-size:15px; font-weight:600; }}
        .stock-ticker {{ font-size:12px; color:var(--text3); margin-top:2px; }}
        .stock-right {{ text-align:right; }}
        .stock-price {{ font-size:16px; font-weight:700; font-variant-numeric:tabular-nums; }}
        .krw-price {{ font-size:11px; color:var(--text3); margin-top:1px; }}
        .stock-change {{ display:inline-block; font-size:12px; font-weight:600; padding:3px 8px; border-radius:6px; margin-top:4px; }}
        .card-detail {{ max-height:0; overflow:hidden; transition:max-height 0.35s cubic-bezier(0.4,0,0.2,1); }}
        .card-detail.open {{ max-height:200px; border-top:1px solid var(--border); }}
        .price-compare {{ display:flex; align-items:center; justify-content:center; gap:16px; padding:14px 16px 10px; }}
        .price-item {{ text-align:center; }}
        .price-label {{ display:block; font-size:11px; color:var(--text3); margin-bottom:4px; }}
        .price-value {{ font-size:15px; font-weight:600; font-variant-numeric:tabular-nums; }}
        .price-arrow {{ font-size:16px; color:var(--text3); }}
        .chart-wrap {{ padding:4px 16px 14px; }}
        .chart-wrap svg {{ width:100%; height:60px; display:block; }}
        .chart-labels {{ display:flex; justify-content:space-between; font-size:10px; color:var(--text3); margin-top:4px; }}
        .report-card {{ margin:0 16px; background:var(--surface); border-radius:16px; border:1px solid var(--border); padding:20px; }}
        .report-header {{ display:flex; align-items:center; gap:8px; margin-bottom:16px; }}
        .report-icon {{ width:32px; height:32px; background:rgba(108,108,255,0.15); border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:16px; }}
        .report-title {{ font-size:15px; font-weight:700; }}
        .report-sub {{ font-size:11px; color:var(--text3); margin-top:1px; }}
        .report-section {{ font-size:13px; font-weight:700; color:var(--accent); margin:16px 0 8px; }}
        .report-text {{ font-size:13px; color:var(--text2); line-height:1.7; margin-bottom:4px; }}
        .report-bullet {{ font-size:13px; color:var(--text2); line-height:1.7; padding-left:4px; margin-bottom:2px; }}
        .report-row {{ display:flex; gap:8px; font-size:12px; color:var(--text2); padding:6px 0; border-bottom:1px solid var(--border); }}
        .report-row span {{ flex:1; }}
        .footer {{ text-align:center; font-size:11px; color:var(--text3); padding:24px 20px 0; }}
    </style>
</head>
<body>
<div class="header">
    <div class="header-top">
        <div class="header-badge">AI Report</div>
        <div class="header-date">{today}</div>
    </div>
    <h1>오늘의<br>주식 시황</h1>
    <p>Claude AI가 분석한 실시간 시황 리포트</p>
</div>
{fx_html}
<div class="section-title">해외 주식 <span class="section-badge badge-global">USD</span></div>
{global_cards}
<div class="section-title">국내 주식 <span class="section-badge badge-korean">KRW</span></div>
{korean_cards}
<div class="section-title" style="margin-top:8px">AI 분석</div>
<div class="report-card">
    <div class="report-header">
        <div class="report-icon">🤖</div>
        <div>
            <div class="report-title">Claude 시황 분석</div>
            <div class="report-sub">AI 기반 참고용 분석입니다</div>
        </div>
    </div>
    {report_html}
</div>
<div class="footer">본 리포트는 투자 참고용이며 투자 판단의 책임은 투자자 본인에게 있습니다</div>
<script>
function toggleDetail(card) {{
    const detail = card.querySelector('.card-detail');
    detail.classList.toggle('open');
}}
</script>
</body>
</html>"""

def upload_to_github(html_content):
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/index.html"
    res = requests.get(url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
    sha = res.json().get("sha", None)
    content_b64 = base64.b64encode(html_content.encode()).decode()
    data = {"message": f"Update report {datetime.now().strftime('%Y-%m-%d %H:%M')}", "content": content_b64}
    if sha:
        data["sha"] = sha
    res = requests.put(url, headers={"Authorization": f"token {GITHUB_TOKEN}"}, json=data)
    return res.status_code == 200 or res.status_code == 201

def send_kakao(url):
    text = f"📊 오늘의 주식 시황 리포트가 준비됐어요!\n\n🔗 {url}"
    template = {"object_type": "text", "text": text, "link": {"web_url": url, "mobile_web_url": url}}
    response = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {KAKAO_TOKEN}"},
        data={"template_object": json.dumps(template)}
    )
    return response.json()

def main():
    print("💱 환율 조회 중...")
    usd_krw = get_usd_krw()
    print(f"USD/KRW: {usd_krw:,.2f}원" if usd_krw else "환율 조회 실패")

    print("📊 주식 데이터 수집 중...")
    stock_data, weekly_data = get_stock_data(usd_krw)

    print("🤖 Claude 분석 중...")
    report = generate_report(stock_data)

    print("🌐 HTML 생성 중...")
    html = generate_html(stock_data, report, weekly_data, usd_krw)

    print("📤 GitHub 업로드 중...")
    success = upload_to_github(html)

    if success:
        report_url = f"https://{GITHUB_USER}.github.io/{GITHUB_REPO}/"
        print(f"✅ 업로드 성공: {report_url}")
        print("📱 카카오톡 발송 중...")
        result = send_kakao(report_url)
        print("발송 결과:", result)
    else:
        print("❌ 업로드 실패")

if __name__ == "__main__":
    main()
