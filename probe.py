"""Terrain, station imbalance, and reciprocal OD probe. No personal columns used."""
import argparse
import calendar
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import map_coordinates, median_filter
from scipy.spatial import cKDTree
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

from settings import RAW, WORK, FONT

def haversine(lat1,lon1,lat2,lon2):
    a,b=np.radians(lat1),np.radians(lat2)
    x=np.sin((b-a)/2)**2+np.cos(a)*np.cos(b)*np.sin(np.radians(lon2-lon1)/2)**2
    return 6371.0088*2*np.arcsin(np.minimum(1,np.sqrt(x)))

def stations(raw,work):
    t=pd.read_excel(raw/'stations_202606.xlsx',header=None,skiprows=5)
    t=t.iloc[:,:10];t.columns=['station','name','district','address','lat','lon','installed','lcd','qr','type']
    for c in ['station','lat','lon','lcd','qr']:t[c]=pd.to_numeric(t[c],errors='coerce')
    audit={'master_rows':len(t),'duplicate_station_ids':int(t.station.dropna().duplicated().sum())}
    t=t[t.station.notna() & t.lat.between(37.3,37.8) & t.lon.between(126.7,127.3)].copy()
    if t.station.duplicated().any():raise ValueError('Duplicate station IDs require review')
    t.station=t.station.astype(int);t['capacity']=t[['lcd','qr']].fillna(0).sum(axis=1)
    t['elevation']=np.nan;t['elevation_median']=np.nan;t['slope_pct']=np.nan
    for lon in [126,127]:
        data=gzip.decompress((raw/f'N37E{lon:03}.hgt.gz').read_bytes())
        n=int(np.sqrt(len(data)/2));assert n*n*2==len(data)
        grid=np.frombuffer(data,dtype='>i2').reshape(n,n).astype(float)
        grid[grid==-32768]=np.nan
        sel=(t.lon>=lon)&(t.lon<lon+1)
        rr=(38-t.loc[sel,'lat'].to_numpy())*(n-1);cc=(t.loc[sel,'lon'].to_numpy()-lon)*(n-1)
        coords=np.array([rr,cc])
        t.loc[sel,'elevation']=map_coordinates(grid,coords,order=1,mode='nearest')
        med=median_filter(grid,size=5)
        t.loc[sel,'elevation_median']=map_coordinates(med,coords,order=1,mode='nearest')
        # Terrain gradient across +/-3 pixels (~185 m N-S, 147 m E-W).
        dy=2*3*111320/(n-1);dx=dy*np.cos(np.radians(t.loc[sel,'lat']))
        gy=(map_coordinates(grid,[rr+3,cc],order=1)-map_coordinates(grid,[rr-3,cc],order=1))/dy
        gx=(map_coordinates(grid,[rr,cc+3],order=1)-map_coordinates(grid,[rr,cc-3],order=1))/dx
        t.loc[sel,'slope_pct']=100*np.hypot(gx,gy)
    xy=np.column_stack([t.lon*111320*np.cos(np.radians(37.55)),t.lat*111320])
    neigh=cKDTree(xy).query_ball_point(xy,500)
    z=t.elevation.to_numpy()
    t['relative_elevation_500m']=[z[i]-np.mean(z[[j for j in js if j!=i]]) if len(js)>1 else np.nan for i,js in enumerate(neigh)]
    t['neighbors_500m']=[len(js)-1 for js in neigh]
    audit.update(valid_coordinate_stations=len(t),missing_elevation=int(t.elevation.isna().sum()),elevation_range=[float(t.elevation.min()),float(t.elevation.max())])
    assert t.elevation.notna().all()
    t.to_csv(work/'stations_terrain.csv',index=False,encoding='utf-8-sig')
    return t,audit

def aggregate(raw,work,t):
    ids=set(t.station)
    od_parts=[];day_parts=[];qa=[]
    cols=['대여일시','대여 대여소번호','반납일시','반납대여소번호','이용시간(분)','이용거리(M)']
    for file in sorted(raw.glob('trips_*.csv')):
        month=file.stem[-6:];cache=work/f'od_{month}.parquet';dcache=work/f'daily_{month}.parquet';qcache=work/f'qa_{month}.json'
        if cache.exists() and dcache.exists() and qcache.exists():
            od_parts.append(pd.read_parquet(cache));day_parts.append(pd.read_parquet(dcache));qa.append(json.loads(qcache.read_text()));continue
        q=dict(month=month,raw_rows=0,valid_duration_rows=0,matched_rows=0,same_station_rows=0,zero_reported_distance_rows=0,departure_min=None,departure_max=None)
        ods=[];days=[]
        for chunk in pd.read_csv(file,encoding='cp949',usecols=cols,chunksize=250000):
            q['raw_rows']+=len(chunk)
            chunk=chunk.rename(columns=dict(zip(cols,['start','o','end','d','minutes','reported_m'])))
            for c in ['o','d','minutes','reported_m']:chunk[c]=pd.to_numeric(chunk[c],errors='coerce')
            chunk=chunk[chunk.minutes.between(1,180)].copy();q['valid_duration_rows']+=len(chunk)
            chunk=chunk[chunk.o.isin(ids)&chunk.d.isin(ids)].copy();q['matched_rows']+=len(chunk)
            chunk[['o','d']]=chunk[['o','d']].astype(int)
            st=pd.to_datetime(chunk.start);et=pd.to_datetime(chunk.end)
            if len(chunk):
                q['departure_min']=min(q['departure_min'] or str(st.min()),str(st.min()))
                q['departure_max']=max(q['departure_max'] or str(st.max()),str(st.max()))
            q['same_station_rows']+=int((chunk.o==chunk.d).sum());q['zero_reported_distance_rows']+=int((chunk.reported_m==0).sum())
            wd=st.dt.weekday<5;h=st.dt.hour
            chunk['period']=np.select([~wd,wd&h.between(7,9),wd&h.between(17,19)],['weekend','weekday_am','weekday_pm'],default='weekday_other')
            g=chunk.groupby(['o','d','period']).agg(n=('o','size'),reported_m_sum=('reported_m','sum')).reset_index();ods.append(g)
            # Actual start/end calendar dates retained separately, including cross-midnight returns.
            a=pd.DataFrame(dict(date=st.dt.strftime('%Y-%m-%d'),station=chunk.o)).value_counts().rename('rent').reset_index()
            b=pd.DataFrame(dict(date=et.dt.strftime('%Y-%m-%d'),station=chunk.d)).value_counts().rename('returns').reset_index()
            days.append(a.merge(b,how='outer',on=['date','station']).fillna(0))
        od=pd.concat(ods).groupby(['o','d','period'],as_index=False)[['n','reported_m_sum']].sum();od['month']=month
        daily=pd.concat(days).groupby(['date','station'],as_index=False)[['rent','returns']].sum();daily['source_month']=month
        assert int(od.n.sum())==q['matched_rows'];assert daily.rent.sum()==daily.returns.sum()==q['matched_rows']
        od.to_parquet(cache,index=False);daily.to_parquet(dcache,index=False);qcache.write_text(json.dumps(q,indent=2),encoding='utf8')
        od_parts.append(od);day_parts.append(daily);qa.append(q);print('AGGREGATED',q,flush=True)
    return pd.concat(od_parts,ignore_index=True),pd.concat(day_parts,ignore_index=True),qa

def fit_record(model,label,terms):
    return [dict(model=label,term=c,beta=float(model.params[c]),se=float(model.bse[c]),p=float(model.pvalues[c]),ci_low=float(model.conf_int().loc[c,0]),ci_high=float(model.conf_int().loc[c,1]),n=int(model.nobs),r2=float(model.rsquared) if hasattr(model,'rsquared') else None) for c in terms]

def analyze(t,od,daily,qa,work):
    od=od.merge(t[['station','lat','lon','elevation','elevation_median','district']].add_prefix('o_'),left_on='o',right_on='o_station')
    od=od.merge(t[['station','lat','lon','elevation','elevation_median','district']].add_prefix('d_'),left_on='d',right_on='d_station')
    od['delta_m']=od.d_elevation-od.o_elevation
    od['delta_median_m']=od.d_elevation_median-od.o_elevation_median
    od['km']=haversine(od.o_lat,od.o_lon,od.d_lat,od.d_lon)
    rents=od.groupby(['month','o']).n.sum().rename('rent').reset_index().rename(columns={'o':'station'})
    returns=od.groupby(['month','d']).n.sum().rename('returns').reset_index().rename(columns={'d':'station'})
    st=rents.merge(returns,how='outer',on=['month','station']).fillna(0).merge(t,on='station')
    st['net']=st.rent-st.returns;st['activity']=st.rent+st.returns;st['net_ratio']=st.net/st.activity
    st['days']=st.month.map(lambda m:calendar.monthrange(int(m[:4]),int(m[4:]))[1]);st['net_per_day']=st.net/st.days
    st['elev10']=st.elevation/10;st['rel10']=st.relative_elevation_500m/10;st['log_activity']=np.log1p(st.activity/st.days)
    st['log_capacity']=np.log1p(st.capacity)
    st.to_csv(work/'station_month.csv',index=False,encoding='utf-8-sig')
    reg=st[st.activity>=100].copy();models=[]
    for y in ['net_per_day','net_ratio']:
        for spec,formula in [('elevation',f'{y} ~ elev10 + C(district) + C(month) + log_activity + log_capacity'),('joint',f'{y} ~ elev10 + slope_pct + C(district) + C(month) + log_activity + log_capacity'),('relative',f'{y} ~ rel10 + slope_pct + C(district) + C(month) + log_activity + log_capacity')]:
            model=smf.ols(formula,reg)
            r=model.fit(cov_type='cluster',cov_kwds={'groups':reg.loc[model.data.row_labels,'station']})
            models.extend(fit_record(r,f'{y}_{spec}',[x for x in ['elev10','rel10','slope_pct'] if x in r.params]))
    base=smf.ols('net_ratio ~ C(district) + C(month) + log_activity + log_capacity',reg).fit()
    full=smf.ols('net_ratio ~ elev10 + slope_pct + C(district) + C(month) + log_activity + log_capacity',reg).fit()
    per_month=[]
    for m,g in reg.groupby('month'):
        r=smf.ols('net_ratio ~ elev10 + slope_pct + C(district) + log_activity + log_capacity',g).fit(cov_type='HC3')
        per_month.extend(fit_record(r,m,['elev10','slope_pct']))
    pd.DataFrame(models+per_month).to_csv(work/'regression.csv',index=False)
    total=st.groupby('station',as_index=False)[['rent','returns','net','activity']].sum().merge(t,on='station')
    total['net_ratio']=total.net/total.activity
    correlations=[]
    for z in ['elevation','slope_pct','relative_elevation_500m']:
        for y in ['net','net_ratio']:
            s=total[[z,y]].dropna();a=stats.pearsonr(s[z],s[y]);b=stats.spearmanr(s[z],s[y]);correlations.append(dict(x=z,y=y,pearson=float(a.statistic),pearson_p=float(a.pvalue),spearman=float(b.statistic),n=len(s)))
    pd.DataFrame(correlations).to_csv(work/'correlations.csv',index=False)
    direction=[]
    for z in ['delta_m','delta_median_m']:
        for threshold in [0,5,10,20,30]:
            for month,g in [('all',od),*list(od.groupby('month'))]:
                g=g[g.o!=g.d];down=int(g.loc[g[z]<-threshold,'n'].sum());up=int(g.loc[g[z]>threshold,'n'].sum());flat=int(g.n.sum()-down-up)
                direction.append(dict(dem=z,threshold_m=threshold,month=month,down=down,up=up,flat=flat,down_up=down/up,down_share=down/(down+up)))
    pd.DataFrame(direction).to_csv(work/'directions.csv',index=False)
    # Reciprocal OD comparison conditions on each unordered station pair's total.
    pair=od[od.o!=od.d].copy();pair['low_id']=pair[['o','d']].min(axis=1);pair['high_id']=pair[['o','d']].max(axis=1)
    pair['down']=np.where(pair.delta_m<0,pair.n,0);pair['up']=np.where(pair.delta_m>0,pair.n,0)
    pair['abs_delta']=pair.delta_m.abs();pair['h_district']=np.where(pair.delta_m<0,pair.o_district,pair.d_district);pair['l_district']=np.where(pair.delta_m<0,pair.d_district,pair.o_district)
    pair=pair.groupby(['month','low_id','high_id'],as_index=False).agg(down=('down','sum'),up=('up','sum'),abs_delta=('abs_delta','first'),km=('km','first'),h_district=('h_district','first'),l_district=('l_district','first'))
    pair['n']=pair.down+pair.up;pair['down_share']=pair.down/pair.n;pair['abs10']=pair.abs_delta/10;pair['log_km']=np.log(pair.km.clip(lower=.05));pair['pair_id']=pair.low_id.astype(str)+'_'+pair.high_id.astype(str)
    p=pair[(pair.abs_delta>=5)&(pair.km>=.1)&(pair.n>=10)].copy()
    # Binomial denominator weights; pair cluster accounts for repeat months. Descriptive association, not causal.
    design='down_share ~ abs10 + log_km + C(month) + C(h_district) + C(l_district)'
    import patsy
    _,X=patsy.dmatrices(design,p,return_type='dataframe')
    r=sm.GLM(np.column_stack([p.down,p.up]),X,family=sm.families.Binomial()).fit(cov_type='cluster',cov_kwds={'groups':p.pair_id})
    pd.DataFrame(fit_record(r,'reciprocal_OD_binomial',['abs10','log_km'])).to_csv(work/'od_model.csv',index=False)
    pair.to_parquet(work/'reciprocal_pairs.parquet',index=False)
    periods=[]
    for period,g in od.groupby('period'):
        d=int(g.loc[g.delta_m<-10,'n'].sum());u=int(g.loc[g.delta_m>10,'n'].sum());periods.append(dict(period=period,down=d,up=u,down_up=d/u))
    pd.DataFrame(periods).to_csv(work/'period_directions.csv',index=False)
    # Straight-line distance strata, using all trips, including zero reported GPS distance.
    g=od[(od.o!=od.d)&(od.km>=.1)].copy()
    g['dist_bin']=pd.cut(g.km,[0,.5,1,2,3,5,100],right=False,labels=['0.1–0.5','0.5–1','1–2','2–3','3–5','5+'])
    g['height_bin']=pd.cut(g.delta_m.abs(),[10,20,40,80,np.inf],right=False,labels=['10–20','20–40','40–80','80+'])
    g['down']=np.where(g.delta_m<0,g.n,0);g['up']=np.where(g.delta_m>0,g.n,0)
    bins=g.groupby(['height_bin','dist_bin'],observed=True)[['down','up']].sum().reset_index();bins['share']=bins.down/(bins.down+bins.up);bins.to_csv(work/'direction_distance_bins.csv',index=False)
    # Calendar-day net movement is a proxy; initial/final inventory and intraday service are unobserved.
    daily=daily.groupby(['date','station'],as_index=False)[['rent','returns']].sum();daily['net']=daily.rent-daily.returns
    daily.to_parquet(work/'station_daily.parquet',index=False)
    dates=pd.to_datetime(daily.date);internal=dates.dt.strftime('%Y%m').isin(st.month.unique())
    # Exclude first/last date of each month to remove cross-boundary extraction effects.
    internal&=(dates.dt.day>1)&(dates.dt.day<dates.dt.days_in_month)
    daily['complete_day']=internal
    daily_lb=daily[internal].groupby('date').net.apply(lambda x:float(x.clip(lower=0).sum()))
    monthly_lb=st.groupby('month').net.apply(lambda x:int(x.clip(lower=0).sum()))
    total.to_csv(work/'station_total.csv',index=False,encoding='utf-8-sig')
    all10=next(x for x in direction if x['dem']=='delta_m' and x['threshold_m']==10 and x['month']=='all')
    joint=next(x for x in models if x['model']=='net_ratio_joint' and x['term']=='elev10')
    verdict='성립(지형-불균형 연관성); 트럭 탄소의 인과·실측은 미검증' if joint['beta']>0 and joint['ci_low']>0 and all10['down_up']>1.1 else '보류 또는 불성립'
    metrics=dict(verdict=verdict,qa=qa,n_stations=len(total),n_station_month=len(reg),n_trips=int(od.n.sum()),correlations=correlations,station_models=models,monthly_models=per_month,incremental_r2_terrain=float(full.rsquared-base.rsquared),directions=direction,periods=periods,od_model=fit_record(r,'reciprocal_OD_binomial',['abs10','log_km']),od_model_pair_months=len(p),od_model_trips=int(p.n.sum()),monthly_net_relocation_proxy=monthly_lb.to_dict(),complete_days=len(daily_lb),daily_net_relocation_proxy_sum=float(daily_lb.sum()),daily_net_relocation_proxy_mean=float(daily_lb.mean()))
    (work/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
    figures(total,bins,work)
    print(json.dumps({k:v for k,v in metrics.items() if k in ['verdict','n_stations','n_trips','incremental_r2_terrain','od_model','monthly_net_relocation_proxy','daily_net_relocation_proxy_mean']},ensure_ascii=False,indent=2),flush=True)
    return metrics

def figures(total,bins,work):
    plt.rcParams.update({'font.family':FONT,'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(1,2,figsize=(11,5.1),layout='constrained')
    z=axs[0].scatter(total.lon,total.lat,c=total.elevation,s=9,cmap='viridis',vmin=0,vmax=120,rasterized=True)
    fig.colorbar(z,ax=axs[0],label='대여소 DEM 고도 (m)',shrink=.8)
    z=axs[1].scatter(total.lon,total.lat,c=total.net_ratio*100,s=9,cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-40,vcenter=0,vmax=40),rasterized=True)
    fig.colorbar(z,ax=axs[1],label='순유출률 (%) = (대여-반납)/(대여+반납)',shrink=.8,extend='both')
    for ax in axs:ax.set(xlabel='경도',ylabel='위도');ax.set_aspect(1/np.cos(np.radians(37.55)))
    for ext in ['png','pdf']:fig.savefig(work/f'fig01_station_map.{ext}',dpi=220)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.8),layout='constrained')
    heights=['10–20','20–40','40–80','80+'];colors=['#5f879f','#238989','#ad7d35','#9c4154']
    for i,(label,color) in enumerate(zip(heights,colors)):
        sub=bins[bins.height_bin.astype(str)==label].set_index('dist_bin')
        xs=[];ys=[]
        for j,d in enumerate(['0.1–0.5','0.5–1','1–2','2–3','3–5','5+']):
            if d in sub.index and sub.loc[d,['down','up']].sum()>=100:
                xs.append(j+(i-1.5)*.19);ys.append(float(sub.loc[d,'share'])*100)
        ax.bar(xs,ys,width=.18,label=f'고도차 {label} m',color=color)
    ax.axhline(50,color='#555555',ls='--',lw=1)
    ax.set(xticks=range(6),xticklabels=['0.1–0.5','0.5–1','1–2','2–3','3–5','5+'],xlabel='대여소 간 직선거리 (km)',ylabel='양방향 통행 중 내리막 비율 (%)',ylim=(0,100))
    ax.legend(loc='upper right',ncols=2,fontsize=9);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    for ext in ['png','pdf']:fig.savefig(work/f'fig02_downhill_share.{ext}',dpi=220)
    plt.close(fig)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--raw',type=Path,default=RAW);ap.add_argument('--work',type=Path,default=WORK);a=ap.parse_args();a.work.mkdir(parents=True,exist_ok=True)
    t,audit=stations(a.raw,a.work);(a.work/'station_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8');print('STATIONS',audit,flush=True)
    od,daily,qa=aggregate(a.raw,a.work,t);analyze(t,od,daily,qa,a.work)
