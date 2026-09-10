"""Refresh public Wikipedia identities; no edits, metrics or article prose collected.

Run explicitly from any directory: python frontend/scripts/refresh-wiki-sources.py
Network is needed only to refresh checked-in provenance, never to run the demo.
"""
import json
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import hashlib
import tempfile
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'src/data/mock/fixtures/sources.json'
API = 'https://en.wikipedia.org/w/api.php'
AS_OF = '2026-09-10'


def query(**params):
    url = API + '?' + urllib.parse.urlencode({'format': 'json', 'formatversion': 2, **params})
    cache = Path(tempfile.gettempdir()) / ('wikipulse-source-' + AS_OF + '-' + hashlib.sha256(url.encode()).hexdigest() + '.json')
    if cache.exists():
        return json.loads(cache.read_text(encoding='utf-8'))
    request = urllib.request.Request(url, headers={'User-Agent': 'WikiPulseDemo/1.0 (public article identity verification)'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503) or attempt == 4:
                raise
            time.sleep(max(int(error.headers.get('Retry-After', 5)), 5 * (attempt + 1)))
    if 'error' in data:
        raise RuntimeError(data['error'])
    cache.write_text(json.dumps(data), encoding='utf-8')
    time.sleep(0.5)
    return data


class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.link = [], [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        if tag in ('td', 'th'):
            self.cell, self.link = [], None
        if tag == 'a' and self.cell is not None:
            href = dict(attrs).get('href', '')
            if href.startswith('/wiki/') and not self.link:
                self.link = urllib.parse.unquote(href[6:])

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append((''.join(self.cell).strip(), self.link))
            self.cell = None
        if tag == 'tr' and self.row:
            self.rows.append(self.row)


def main():
    topics = json.loads(subprocess.check_output([
        'node', '--input-type=module', '-e',
        "import {topics} from './src/data/mock/fixtures/topics.js'; console.log(JSON.stringify(topics));",
    ], cwd=ROOT).decode('utf-8'))
    parsed = query(action='parse', page='List of NASDAQ-100 companies', prop='text|revid')['parse']
    table = Table()
    table.feed(parsed['text'])
    stocks = [dict(symbol=row[0][0], name=row[1][0], title=row[1][1].replace('_', ' '),
                   industry=row[2][0], subsector=row[3][0])
              for row in table.rows if len(row) == 4 and row[0][0].isupper()
              and row[0][0].isalpha() and row[1][1]]
    assert 100 <= len(stocks) <= 105, f'Unexpected universe: {len(stocks)}'
    titles = sorted({d['title'] for t in topics for d in t['documents']} | {s['title'] for s in stocks})
    articles, failures = {}, []
    for offset in range(0, len(titles), 40):
        batch = titles[offset:offset + 40]
        data = query(action='query', titles='|'.join(batch), redirects=1,
                     prop='info|pageprops', inprop='url', ppprop='disambiguation')['query']
        aliases = {p['from']: p['to'] for p in data.get('normalized', []) + data.get('redirects', [])}
        pages = {p['title']: p for p in data['pages']}
        for title in batch:
            canonical = title
            while canonical in aliases:
                canonical = aliases[canonical]
            page = pages[canonical]
            if page.get('missing') or 'disambiguation' in page.get('pageprops', {}):
                failures.append(title)
                continue
            articles[title] = dict(pageId=page['pageid'], title=canonical, url=page['fullurl'])
        print(f'Validated {min(offset + 40, len(titles))}/{len(titles)} identities', flush=True)
    if failures:
        raise RuntimeError('Missing or ambiguous pages: ' + ', '.join(failures))
    def first_revision(article):
        page = query(action='query', pageids=article['pageId'], prop='revisions',
                     rvprop='ids|timestamp', rvdir='newer', rvlimit=1)['query']['pages'][0]
        first = page['revisions'][0]
        article.update(firstRevisionAt=first['timestamp'], firstRevisionId=first['revid'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(first_revision, articles.values()))
    result = dict(checkedAt=AS_OF, universe=dict(name='Nasdaq-100', asOf=AS_OF,
        source='https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies',
        revisionId=parsed['revid'], membershipMode='fixed-current-universe',
        note='Current constituent snapshot applied to all demo dates; not historical index membership.',
        stocks=stocks), articles=articles)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved {len(articles)} articles and {len(stocks)} securities to {OUT}')


if __name__ == '__main__':
    main()
