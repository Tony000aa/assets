import requests, json, time
from datetime import datetime, timezone

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://finance.yahoo.com',
}

FX_PAIRS = {
    'USD': 'TWD=X', 'JPY': 'JPYTWD=X', 'EUR': 'EURTWD=X',
    'AUD': 'AUDTWD=X', 'HKD': 'HKDTWD=X', 'SGD': 'SGDTWD=X',
    'GBP': 'GBPTWD=X', 'CNY': 'CNYTWD=X',
}

def init_yf_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    crumb = None
    try:
        s.get('https://fc.yahoo.com', timeout=8)
        r = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=8)
        if r.status_code == 200 and r.text.strip():
            crumb = r.text.strip()
            print(f'  YF crumb OK')
    except Exception as e:
        print(f'  YF session warning: {e}')
    return s, crumb

def yf_batch(session, crumb, symbols):
    if not symbols:
        return {}
    syms_str = ','.join(symbols)
    crumb_param = f'&crumb={crumb}' if crumb else ''
    for base in ['https://query1', 'https://query2']:
        try:
            url = f'{base}.finance.yahoo.com/v7/finance/quote?symbols={syms_str}{crumb_param}'
            r = session.get(url, timeout=12)
            if not r.ok:
                continue
            results = r.json().get('quoteResponse', {}).get('result', [])
            data = {}
            for q in results:
                price = q.get('regularMarketPrice')
                if not price:
                    continue
                prev = q.get('regularMarketPreviousClose') or price
                sym = q['symbol']
                data[sym] = {
                    'price': round(price, 4),
                    'chg': round((price - prev) / prev * 100, 2) if prev else 0,
                    'name': q.get('longName') or q.get('shortName') or sym,
                }
            if data:
                return data
        except Exception as e:
            print(f'  yf_batch {base} error: {e}')
    return {}

def yf_single(session, crumb, sym):
    crumb_param = f'&crumb={crumb}' if crumb else ''
    for base in ['https://query1', 'https://query2']:
        try:
            url = f'{base}.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d{crumb_param}'
            r = session.get(url, timeout=10)
            if not r.ok:
                continue
            res = r.json().get('chart', {}).get('result', [None])[0]
            if not res:
                continue
            m = res['meta']
            price = m.get('regularMarketPrice')
            if not price:
                continue
            prev = m.get('chartPreviousClose') or m.get('previousClose') or price
            return {
                'price': round(price, 4),
                'chg': round((price - prev) / prev * 100, 2),
                'name': m.get('longName') or m.get('shortName') or sym,
            }
        except:
            pass
    return None

def fetch_twse():
    try:
        r = requests.get('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
                         headers=HEADERS, timeout=20)
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
                    'name': s['Name'],
                }
            except:
                pass
        print(f'  TWSE: {len(data)} stocks')
        return data
    except Exception as e:
        print(f'  TWSE error: {e}')
        return {}

def fetch_tpex():
    for attempt in range(3):
        try:
            r = requests.get('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_quotes',
                             headers=HEADERS, timeout=20)
            r.raise_for_status()
            if not r.content:
                print(f'  TPEX empty (attempt {attempt+1}/3), retrying...')
                time.sleep(3)
                continue
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
                        'name': s.get('CompanyName') or s['SecuritiesCompanyCode'],
                    }
                except:
                    pass
            print(f'  TPEX: {len(data)} stocks')
            return data
        except Exception as e:
            print(f'  TPEX error (attempt {attempt+1}/3): {e}')
            if attempt < 2:
                time.sleep(3)
    return {}

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

    print('Initializing Yahoo Finance session...')
    session, crumb = init_yf_session()

    print(f'Fetching {len(us_tickers)} US stocks (batch)...')
    us = yf_batch(session, crumb, us_tickers)
    missing = [t for t in us_tickers if t not in us]
    if missing:
        print(f'  Batch missing: {missing}, trying individually...')
        for t in missing:
            d = yf_single(session, crumb, t)
            if d:
                us[t] = d
                print(f'  {t}: {d["price"]}')
            else:
                print(f'  {t}: failed')
    else:
        for t, d in us.items():
            print(f'  {t}: {d["price"]}')

    print('Fetching FX rates (batch)...')
    fx_syms = list(FX_PAIRS.values())
    fx_raw = yf_batch(session, crumb, fx_syms)
    fx = {'TWD': 1}
    for cur, sym in FX_PAIRS.items():
        if sym in fx_raw and fx_raw[sym]['price'] > 0:
            fx[cur] = fx_raw[sym]['price']
        else:
            d = yf_single(session, crumb, sym)
            if d and d['price'] > 0:
                fx[cur] = d['price']
    print(f'  FX: {fx}')

    out = {
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'tw': tw,
        'us': us,
        'fx': fx,
    }
    with open('prices.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'Done: {len(tw)} TW + {len(us)} US stocks saved to prices.json')
