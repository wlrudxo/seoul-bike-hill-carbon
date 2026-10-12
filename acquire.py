"""Download unauthenticated official files; preserve originals outside Git."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import requests

from settings import RAW
SOURCES = [
    ('stations_202606.xlsx', 'OA-13252', 2, 24, '2026-06'),
    ('stations_202512.xlsx', 'OA-13252', 2, 23, '2025-12'),
    ('stations_202506.xlsx', 'OA-13252', 2, 22, '2025-06'),
    ('trips_202601.csv', 'OA-15182', 1, 144, '2026-01'),
    ('trips_202604.csv', 'OA-15182', 1, 148, '2026-04'),
    ('trips_202606.csv', 'OA-15182', 1, 150, '2026-06'),
]

def download(item, raw=RAW):
    name, code, infseq, seq, period = item
    url = 'https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do'
    params = dict(useCache='false', infId=code, seqNo='', infSeq=infseq, seq=seq)
    path = raw / name
    manifest=raw/'metadata'/f'{name}.json'
    if path.exists():
        if manifest.exists() and path.stat().st_size==json.loads(manifest.read_text(encoding='utf8'))['bytes']:
            print('EXISTS', name, path.stat().st_size, flush=True)
            return
        raise FileExistsError(f'{path}: existing file is incomplete or lacks a manifest; preserve and review before retrying')
    r = requests.get(url, params=params, stream=True, timeout=(30, 120))
    r.raise_for_status()
    print('START', name, r.status_code, r.headers.get('Content-Type'), r.headers.get('Content-Length'), flush=True)
    sha = hashlib.sha256()
    with path.open('wb') as f:
        for block in r.iter_content(4 * 1024 * 1024):
            f.write(block); sha.update(block)
    record = dict(file=name, url=r.url, dataset_url=f'https://data.seoul.go.kr/dataList/{code}/F/1/datasetView.do', period=period, retrieved=dt.datetime.now(dt.timezone.utc).isoformat(), bytes=path.stat().st_size, sha256=sha.hexdigest(), license='KOGL Type 1 (attribution; commercial use and modification permitted)', content_type=r.headers.get('Content-Type'))
    (raw/'metadata'/f'{name}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print('DONE', name, record['bytes'], sha.hexdigest(), flush=True)

def dem(lon, raw=RAW):
    name=f'N37E{lon:03d}.hgt.gz'
    path=raw/name
    if path.exists() and path.stat().st_size>10000: return
    url=f'https://s3.amazonaws.com/elevation-tiles-prod/skadi/N37/{name}'
    r=requests.get(url,timeout=120);r.raise_for_status();path.write_bytes(r.content)
    record=dict(file=name,url=url,retrieved=dt.datetime.now(dt.timezone.utc).isoformat(),bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),product='Mapzen Terrain Tiles / Skadi 1 arcsecond HGT (derived DEM; not ground survey)',license='Mapzen attribution and source licenses; see https://github.com/tilezen/joerd/blob/master/docs/attribution.md',period='static source mosaic, varies by underlying DEM')
    (raw/'metadata'/f'{name}.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print('DEM',name,len(r.content),flush=True)

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--raw',type=Path,default=RAW);args=parser.parse_args()
    args.raw.mkdir(parents=True,exist_ok=True);(args.raw/'metadata').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        jobs=[ex.submit(download,x,args.raw) for x in SOURCES]+[ex.submit(dem,x,args.raw) for x in [126,127]]
        for job in concurrent.futures.as_completed(jobs):job.result()
