import requests, json
from datetime import datetime, timezone

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

FX_PAIRS = {
    'USD': 'TWD=X', 'JPY': 'JPYTWD=X', 'EUR': 'EURTWD=X',
    'AUD': 'AUDTWD=X', 'HKD': 'HKDTWD=X', 'SGD': 'SGDTWD=X',
    'GBP': 'GBPTWD=X', 'CNY': 'CNYTWD=X',
}

def yf(sym):
    for url in [
        f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d',
        f'https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d',
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            res = r.json().get('chart', {}).get('result', [None])[0]
            if not res:
                continue
            m = res['meta']
            price = m.get('regularMarketPrice')
            if not price:
                continue
            prev = m.get('chartPreviousClose') or m.get('previousClose') or price
            name = m.get('longName') or m.get('shortName') or sym
            return {'price': round(price, 4), 'chg': round((price - prev) / prev * 100, 2), 'name': name}
        except:
            pass
    return None

def fetch_twse():
    try:
        r = requests.get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL', timeout=15)
        r.raise_for_status()
        data = {}
        for s in r.json():
            try:
                close = float(s['ClosingPrice'])
                if not close:
                    continue
                chg = float(s.get('Change') or 0)
                prev = close - chg
                data[s['Code']] = {
                    'price': close,
                    'chg': round(chg / prev * 100, 2) if prev > 0 else 0,
                    'name': s['Name']
                }
            except:
                pass
        print(f'  TWSE: {len(data)} stocks')
        return data
    except Exception as e:
        print(f'  TWSE error: {e}')
        return {}

def fetch_tpex():
    try:
        r = requests.get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_quotes', timeout=15)
        r.raise_for_status()
        data = {}
        for s in r.json():
            try:
                close = float(s['Close'])
                if not close:
                    continue
                prev = float(s.get('PreviousClose') or close)
                data[s['SecuritiesCompanyCode']] = {
                    'price': close,
                    'chg': round((close - prev) / prev * 100, 2) if prev > 0 else 0,
                    'name': s.get('CompanyName') or s['SecuritiesCompanyCode']
                }
            except:
                pass
        print(f'  TPEX: {len(data)} stocks')
        return data
    except Exception as e:
        print(f'  TPEX error: {e}')
        return {}

def fetch_us(tickers):
    data = {}
    for t in tickers:
        r = yf(t)
        if r:
            data[t] = r
            print(f'  {t}: {r["price"]}')
        else:
            print(f'  {t}: failed')
    return data

def fetch_fx():
    fx = {'TWD': 1}
    for cur, sym in FX_PAIRS.items():
        r = yf(sym)
        if r and r['price'] > 0:
            fx[cur] = round(r['price'], 4)
    print(f'  FX: {fx}')
    return fx

if __name__ == '__main__':
    print('Fetching TWSE...')
    tw = fetch_twse()
    print('Fetching TPEX...')
    tw.update(fetch_tpex())

    try:
        with open('us_tickers.json', 'r') as f:
            us_tickers = json.load(f)
    except:
        us_tickers = []
    print(f'Fetching {len(us_tickers)} US stocks...')
    us = fetch_us(us_tickers)

    print('Fetching FX rates...')
    fx = fetch_fx()

    out = {
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'tw': tw,
        'us': us,
        'fx': fx,
    }
    with open('prices.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'Done: {len(tw)} TW + {len(us)} US stocks saved to prices.json')
