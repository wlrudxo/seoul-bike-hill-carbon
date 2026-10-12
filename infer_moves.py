"""Infer between-rental bicycle displacement; vehicles and causes are not observed.

Method reference: https://goutam.org/projects/citi-bike-rebalances/
Retain all raw rows before lagging, so filtering cannot invent missing trips.
Only station-pair counts are exported; individual bicycle sequences remain local.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from probe import RAW,WORK,haversine

def run(raw,work):
    t=pd.read_csv(work/'stations_terrain.csv').set_index('station');records=[];pairs=[]
    cols=['자전거번호','대여일시','대여 대여소번호','반납일시','반납대여소번호']
    for f in sorted(raw.glob('trips_*.csv')):
        month=f.stem[-6:];cache=work/f'inferred_pairs_{month}.parquet';qcache=work/f'inferred_{month}.json'
        if cache.exists() and qcache.exists():pairs.append(pd.read_parquet(cache));records.extend(json.loads(qcache.read_text(encoding='utf8')));continue
        x=pd.read_csv(f,encoding='cp949',usecols=cols);x=x.rename(columns=dict(zip(cols,['bike','start','o','end','d'])))
        for c in ['o','d']:x[c]=pd.to_numeric(x[c],errors='coerce')
        x.start=pd.to_datetime(x.start,errors='coerce');x.end=pd.to_datetime(x.end,errors='coerce')
        x=x.sort_values(['bike','start','end'],kind='stable').reset_index(drop=True)
        prev=x.groupby('bike',sort=False)[['end','d']].shift()
        gap=(x.start-prev.end).dt.total_seconds()/3600
        eligible=x.o.isin(t.index)&prev.d.isin(t.index)&x.start.notna()&prev.end.notna()
        y=pd.DataFrame({'from_station':prev.loc[eligible,'d'].astype(int),'to_station':x.loc[eligible,'o'].astype(int),'gap_h':gap.loc[eligible]})
        y['km']=haversine(y.from_station.map(t.lat),y.from_station.map(t.lon),y.to_station.map(t.lat),y.to_station.map(t.lon))
        y['delta_m']=y.to_station.map(t.elevation)-y.from_station.map(t.elevation)
        out=[]
        for limit in [6,24,72,168]:
            z=y[(y.from_station!=y.to_station)&(y.gap_h>=0)&(y.gap_h<=limit)&(y.km>=.1)]
            down=int((z.delta_m<-10).sum());up=int((z.delta_m>10).sum())
            out.append(dict(month=month,max_gap_hours=limit,inferred_displacements=len(z),straight_line_bike_km=float(z.km.sum()),uphill10=up,downhill10=down,up_down_ratio=up/down,uphill10_bike_km=float(z.loc[z.delta_m>10,'km'].sum()),overlapping_sequence_rows=int((gap<0).sum())))
        z=y[(y.from_station!=y.to_station)&y.gap_h.between(0,72)&(y.km>=.1)].copy()
        z=z.groupby(['from_station','to_station'],as_index=False).agg(n=('km','size'),km=('km','first'),delta_m=('delta_m','first'));z['month']=month
        z.to_parquet(cache,index=False);qcache.write_text(json.dumps(out,indent=2),encoding='utf8');records.extend(out);pairs.append(z);print('INFERRED',out[2],flush=True)
    pd.concat(pairs).to_parquet(work/'inferred_relocation_pairs.parquet',index=False)
    pd.DataFrame(records).to_csv(work/'inferred_moves.csv',index=False)
    all72=[x for x in records if x['max_gap_hours']==72]
    summary={c:sum(x[c] for x in all72) for c in ['inferred_displacements','straight_line_bike_km','uphill10','downhill10','uphill10_bike_km']}
    summary['up_down_ratio']=summary['uphill10']/summary['downhill10'];summary['method']='Consecutive raw rental records per bike; station change during 0–72h idle gap and >=100m endpoint distance. Includes maintenance, record omissions and non-truck moves. Not actual truck telemetry.'
    (work/'inferred_metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--work',type=Path,default=WORK);a=p.parse_args();run(a.raw,a.work)
