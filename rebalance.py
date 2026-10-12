"""Minimum-cost monthly balancing benchmark and explicit truck assumptions.

Not an estimate of actual truck routes: start/end stocks, depots, road network,
intraday service, vehicle fleet, maintenance and empty trips are unobserved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from probe import haversine, RAW, WORK

GHG_URL='https://assets.publishing.service.gov.uk/media/6846a4f55e92539572806125/ghg-conversion-factors-2025-full-set.xlsx'

def factor(raw):
    path=raw/'ghg-conversion-factors-2025-full-set.xlsx'
    if not path.exists():
        r=requests.get(GHG_URL,timeout=90);r.raise_for_status();path.write_bytes(r.content)
    frame=pd.read_excel(path,sheet_name='Delivery vehicles',header=None)
    assert frame.iloc[29,1]=='Class III (1.74 to 3.5 tonnes)' and frame.iloc[29,2]=='km'
    ef=float(frame.iloc[29,3]);co2=float(frame.iloc[29,4])
    rec=dict(url=GHG_URL,dataset_url='https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025',file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),retrieved_date='2026-10-12',period='2025 v1.0',sheet='Delivery vehicles',co2e_cell='D30',co2_cell='E30',kg_co2e_per_vehicle_km=ef,kg_co2_per_vehicle_km=co2,vehicle='diesel van class III 1.74–3.5 tonnes; UK proxy, Seoul vehicle class unknown',boundary='Scope 1 operation; excludes well-to-tank, vehicle manufacture',license='UK Open Government Licence v3.0 (page footer)')
    (raw/'metadata'/'ghg_factor.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2),encoding='utf8')
    return rec

def run(raw,work):
    factors=factor(raw);st=pd.read_csv(work/'station_month.csv');allflows=[];records=[]
    for month,g in st.groupby('month'):
        supply=g[g.net<0].reset_index(drop=True);demand=g[g.net>0].reset_index(drop=True)
        n,m=len(supply),len(demand);assert supply.net.sum()+demand.net.sum()==0
        dist=np.asarray(haversine(supply.lat.to_numpy()[:,None],supply.lon.to_numpy()[:,None],demand.lat.to_numpy()[None,:],demand.lon.to_numpy()[None,:]))
        col=np.arange(n*m);rows1=np.repeat(np.arange(n),m);rows2=np.tile(np.arange(m),n)+n
        A=coo_matrix((np.ones(2*n*m),(np.r_[rows1,rows2],np.r_[col,col])),shape=(n+m,n*m)).tocsc()
        b=np.r_[-supply.net.to_numpy(),demand.net.to_numpy()]
        print('SOLVING',month,n,m,n*m,flush=True)
        sol=linprog(dist.ravel(),A_eq=A,b_eq=b,bounds=(0,None),method='highs',options={'time_limit':240})
        if not sol.success:raise RuntimeError(f'No optimal transport solution: {sol.message}')
        assert np.max(np.abs(A@sol.x-b))<1e-5
        ix=np.where(sol.x>1e-6)[0];i=ix//m;j=ix%m
        f=pd.DataFrame(dict(month=month,from_station=supply.station.to_numpy()[i],to_station=demand.station.to_numpy()[j],bikes=sol.x[ix],km=dist.ravel()[ix],elev_from=supply.elevation.to_numpy()[i],elev_to=demand.elevation.to_numpy()[j]))
        f['delta_m']=f.elev_to-f.elev_from;f['bike_km']=f.bikes*f.km;f['uphill10']=f.delta_m>=10
        allflows.append(f);records.append(dict(month=int(month),bikes=float(f.bikes.sum()),bike_km=float(f.bike_km.sum()),uphill10_bikes=float(f.loc[f.uphill10,'bikes'].sum()),uphill10_bike_km=float(f.loc[f.uphill10,'bike_km'].sum()),optimality='HiGHS optimal',balance_max_error=float(np.max(np.abs(A@sol.x-b)))))
        print('OPTIMUM',records[-1],flush=True)
    flows=pd.concat(allflows);flows.to_csv(work/'rebalance_min_cost_flows.csv',index=False)
    base=pd.DataFrame(records);base.to_csv(work/'rebalance_months.csv',index=False)
    bike_km=float(base.bike_km.sum());uphill_km=float(base.uphill10_bike_km.sum());uphill_bikes=float(base.uphill10_bikes.sum())
    sensitivity=[]
    for capacity in [10,20,40]:
        for road in [1.0,1.3,1.6]:
            for extra in [1.0,1.5,2.0]:
                vk=bike_km/capacity*road*extra
                sensitivity.append(dict(bikes_per_vehicle=capacity,road_factor=road,route_empty_multiplier=extra,vehicle_km_equivalent=vk,kg_co2e=vk*factors['kg_co2e_per_vehicle_km']))
    pd.DataFrame(sensitivity).to_csv(work/'carbon_sensitivity.csv',index=False)
    # Fixed service assumption, constant capacity and multiplier; 10m+ uphill demand.
    capacity=20;road=1.3;extra=1.5;conversion=road*extra/capacity
    scenarios=[]
    for x in [0,.1,.25,.5]:
        saved_km=x*uphill_km*conversion
        scenarios.append(dict(uphill10_flow_shift_fraction=x,additional_user_uphill_trips=x*uphill_bikes,vehicle_km_equivalent=(bike_km-x*uphill_km)*conversion,kg_co2e=(bike_km-x*uphill_km)*conversion*factors['kg_co2e_per_vehicle_km'],avoided_vehicle_km_equivalent=saved_km,avoided_kg_co2e=saved_km*factors['kg_co2e_per_vehicle_km'],interpretation='incentive/e-bike conditional substitution of minimum-flow uphill deliveries; not measured policy uptake'))
    pd.DataFrame(scenarios).to_csv(work/'policy_scenarios.csv',index=False)
    summary=dict(benchmark='Monthly final-inventory restoration; straight-line min-cost flow, not actual truck operations and not causal slope attribution',months=records,total_bikes=float(base.bikes.sum()),total_bike_km=bike_km,uphill10_bikes=uphill_bikes,uphill10_bike_km=uphill_km,factor=factors,base_assumptions=dict(bikes_per_vehicle=capacity,road_factor=road,route_empty_multiplier=extra),scenarios=scenarios,sensitivity_kg_co2e_range=[min(x['kg_co2e'] for x in sensitivity),max(x['kg_co2e'] for x in sensitivity)],mathematical_loaded_vehicle_km_lower_bound_Q20=bike_km/20)
    (work/'rebalance_metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--work',type=Path,default=WORK);a=p.parse_args();run(a.raw,a.work)
