"""Meaningful checks of historical coordinates, model weighting and uncertainty."""
import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
from probe import RAW,WORK,haversine,fit_record

def main(raw=RAW,work=WORK):
    current=pd.read_csv(work/'stations_terrain.csv')
    histories=[];stable=set(current.station)
    for date in ['202512','202506']:
        h=pd.read_excel(raw/f'stations_{date}.xlsx',header=None)
        print(date,h.head(7).iloc[:,:6].to_string(index=False,header=False),flush=True)
        h=h.iloc[:,:6].copy();h.columns=['station','name','district','address','lat','lon']
        for c in ['station','lat','lon']:h[c]=pd.to_numeric(h[c],errors='coerce')
        h=h[h.station.notna()&h.lat.between(37.3,37.8)&h.lon.between(126.7,127.3)].copy()
        assert not h.station.duplicated().any()
        comp=current.merge(h[['station','lat','lon']],on='station',suffixes=('_new','_old'))
        comp['moved_m']=1000*haversine(comp.lat_old,comp.lon_old,comp.lat_new,comp.lon_new)
        stable&=set(comp.loc[comp.moved_m<50,'station'])
        histories.append(dict(master=date,historical_stations=len(h),matched_current=len(comp),moved_at_least_50m=int((comp.moved_m>=50).sum()),max_coordinate_change_m=float(comp.moved_m.max())))
    st=pd.read_csv(work/'station_month.csv');reg=st[st.activity>=100].copy();reg['median10']=reg.elevation_median/10
    form='net_ratio ~ elev10 + slope_pct + C(district) + C(month) + log_activity + log_capacity'
    configs=[('district_cluster',reg,form,False,'district'),('without_activity_controls',reg,'net_ratio ~ elev10 + slope_pct + C(district) + C(month)',False,'station'),('activity_weighted',reg,form,True,'station'),('stable_coordinates_202506_to_202606',reg[reg.station.isin(stable)],form,False,'station'),('median_5x5_elevation',reg,form.replace('elev10','median10'),False,'station')]
    results=[]
    for name,g,f,weighted,group in configs:
        model=smf.wls(f,g,weights=g.activity) if weighted else smf.ols(f,g)
        r=model.fit(cov_type='cluster',cov_kwds={'groups':g.loc[model.data.row_labels,group]})
        results.extend(fit_record(r,name,[x for x in ['elev10','median10','slope_pct'] if x in r.params]))
    pd.DataFrame(results).to_csv(work/'robustness.csv',index=False)
    report=dict(historical_coordinate_checks=histories,stable_50m_all_three_masters=len(stable),models=results)
    (work/'robustness.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--work',type=Path,default=WORK)
    a=p.parse_args();main(a.raw,a.work)
