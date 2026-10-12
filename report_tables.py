"""Export report tables 1–2 and check computed numbers against the report draft."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image
from settings import RAW, WORK


# Table 1 transcribed from the report's public source list. These are citations,
# not redistributed source datasets or a claim to their copyright.
DATA_SOURCES = [
    ('서울시 공공자전거 대여이력 정보', '2026년 1·4·6월', '서울특별시',
     'https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do', '공공누리 제1유형',
     ['trips_202601.csv','trips_202604.csv','trips_202606.csv']),
    ('서울시 공공자전거 대여소 정보', '2026년 6월(주분석)', '서울특별시',
     'https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do', '공공누리 제1유형',
     ['stations_202606.xlsx']),
    ('고도 격자 DEM / AWS Terrain Tiles', '정적 모자이크; N37E126·N37E127', 'Mapzen·USGS',
     'https://registry.opendata.aws/terrain-tiles/', 'Mapzen 및 원천별 출처표시·이용조건',
     ['N37E126.hgt.gz','N37E127.hgt.gz']),
    ('차량 온실가스 배출계수', '2025 full set', 'UK DESNZ',
     'https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025', 'UK OGL v3.0',
     ['ghg-conversion-factors-2025-full-set.xlsx']),
    ('따릉이 시민참여 재배치 보도자료', '2024-05-03 게시', '서울특별시',
     'https://news.seoul.go.kr/traffic/archives/512211', '인용만; 원문 재배포 안 함', []),
    ('서울특별시 행정경계', '2026-10-12 취득 스냅샷', 'OpenStreetMap contributors',
     'https://www.openstreetmap.org/relation/2297418', 'ODbL 1.0', ['seoul_boundary_osm.geojson']),
]


def markdown(frame):
    # No optional tabulate dependency; all current cells are plain text.
    def cell(x): return str(x).replace('|', '\\|').replace('\n', ' ')
    lines=['| '+' | '.join(map(cell,frame.columns))+' |', '| '+' | '.join(['---']*len(frame.columns))+' |']
    lines += ['| '+' | '.join(map(cell,row))+' |' for row in frame.itertuples(index=False,name=None)]
    return '\n'.join(lines)


def main(raw=RAW, work=WORK):
    out=work/'report'/'tables';out.mkdir(parents=True,exist_ok=True)
    table1=pd.DataFrame([x[:5] for x in DATA_SOURCES],columns=['데이터','기준시점','제공기관','출처 URL','라이선스'])
    table1.to_csv(out/'table1_data_sources.csv',index=False,encoding='utf-8-sig')
    identities=[]
    for *_,files in DATA_SOURCES:
        for name in files:
            p=raw/name
            if not p.is_file(): raise FileNotFoundError(p)
            # Streaming hashes also cover the large original trip files.
            sha=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(8*1024*1024),b''): sha.update(block)
            identities.append({'file':name,'bytes':p.stat().st_size,'sha256':sha.hexdigest()})

    b=pd.read_csv(work/'rebalance_months.csv').sort_values('month')
    cols=['bikes','bike_km','uphill10_bikes']
    full=b[['month']+cols].copy()
    total={'month':'합계',**full[cols].sum().to_dict()}
    full=pd.concat([full,pd.DataFrame([total])],ignore_index=True)
    full.to_csv(out/'table2_rebalance_full_precision.csv',index=False,encoding='utf-8-sig')
    table2=pd.DataFrame({
        '월':[f'{int(x)%100}월' if x!='합계' else x for x in full.month],
        '재고 복원에 필요한 자전거(대)':[f'{x:,.0f}' for x in full.bikes],
        '최소 이동거리(자전거-km)':[f'{x:,.0f}' for x in full.bike_km],
        '10m 이상 오르막 보충(대)':[f'{x:,.0f}' for x in full.uphill10_bikes]})
    table2.to_csv(out/'table2_rebalance_report.csv',index=False,encoding='utf-8-sig')
    (out/'README.md').write_text('# 표 1. 활용 데이터 목록\n\n'+markdown(table1)+
        '\n\n# 표 2. 월별 재배치 부담(모형 계산)\n\n'+markdown(table2)+
        '\n\n표 2는 월별 최소비용 수송 결과를 반올림했다. 전체 합계는 반올림 전 값을 합산한다. 원본 파일의 SHA256은 input_manifest.json에 있다. OSM © OpenStreetMap contributors (ODbL 1.0).\n',encoding='utf8')
    (out/'input_manifest.json').write_text(json.dumps(identities,ensure_ascii=False,indent=2),encoding='utf8')

    m=json.loads((work/'metrics.json').read_text(encoding='utf8'))
    c=json.loads((work/'rebalance_metrics.json').read_text(encoding='utf8'))
    i=json.loads((work/'inferred_metrics.json').read_text(encoding='utf8'))
    coef=next(x for x in m['station_models'] if x['model']=='net_ratio_joint' and x['term']=='elev10')
    daily=next(x for x in m['station_models'] if x['model']=='net_per_day_joint' and x['term']=='elev10')
    directions=[x for x in m['directions'] if x['dem']=='delta_m' and x['month']=='all' and x['threshold_m'] in [10,20,30]]
    scenarios=[x for x in c['scenarios'] if x['uphill10_flow_shift_fraction'] in [0,.25,.5]]
    numbers={'raw_trips':sum(x['raw_rows'] for x in m['qa']), 'valid_trips':m['n_trips'],
        'stations':m['n_stations'],'station_months':m['n_station_month'],
        'elevation_effect_pp_per_10m':coef['beta']*100,
        'elevation_effect_ci_pp':[coef['ci_low']*100,coef['ci_high']*100],
        'net_bikes_per_day_per_10m':daily['beta'],
        'directions':directions,'monthly_models':m['monthly_models'],
        'inferred_displacements':i,'rebalance':full.to_dict('records'),'carbon_scenarios':scenarios,
        'scope':'Public-data model estimates; no fuel/GPS calibration or causal topography attribution.'}
    (out/'report_numbers.json').write_text(json.dumps(numbers,ensure_ascii=False,indent=2),encoding='utf8')

    # Study-specific regression checks against the submitted draft, never input
    # values used to calculate the plots. Fail on stale or changed datasets.
    assert (numbers['raw_trips'],m['n_trips'],m['n_stations'],m['n_station_month'])==(9761201,9427594,2773,8152)
    assert np.isclose(coef['beta']*100,6.445464312239721,atol=1e-6)
    assert np.allclose([x['down_up'] for x in directions],[1.288142422112907,1.5825657666927193,1.825716352656245])
    assert np.allclose(b.bikes,[80841,168460,164992])
    assert np.allclose(b.uphill10_bikes,[43896,98456,96895])
    assert np.array_equal(np.rint(b.bike_km).astype(int),[80944,218268,229241])
    assert np.isclose(full.bike_km.iloc[-1],528453.446549405,atol=.001)
    assert np.allclose([x['kg_co2e']/1000 for x in scenarios],[14.36391955296754,11.789063171957667,9.2142067909478],atol=1e-5)
    assert (i['inferred_displacements'],i['uphill10'],i['downhill10'])==(368227,191276,10683)
    figs=work/'report'/'figs'
    manifest=json.loads((figs/'figure_manifest.json').read_text(encoding='utf8'))
    assert len(manifest)==5
    for item in manifest:
        with Image.open(figs/item['file']) as im:
            assert abs(im.info['dpi'][0]-300)<.1 and min(im.size)>500
    (out/'verification.json').write_text(json.dumps({'status':'passed','figure_count':5,
        'tables':[1,2],'checks':'Draft counts, coefficients, OD ratios, monthly balances, carbon, inferred moves and PNG dpi'},indent=2),encoding='utf8')
    print('REPORT NUMBERS VERIFIED: figures 1–5, tables 1–2',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--work',type=Path,default=WORK)
    a=p.parse_args();main(a.raw,a.work)
