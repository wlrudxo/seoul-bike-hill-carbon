"""Report draft figures: 12.2 cm insertion width, Korean typography, 300 dpi.

Reads verified probe outputs; does not fit or calibrate vehicle operations.
OSM boundary is a new, separately attributed cartographic input only.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy import stats
from scipy.ndimage import map_coordinates
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.path import Path as PlotPath
from PIL import Image, ImageOps, ImageDraw

from settings import RAW, WORK, FONT
# Adapted from the report/figs12 12cm scripts (2026-10-12), based on a65c1ed.

NAVY='#183B56'
TEAL='#078C8C'
ORANGE='#EA8337'
GRAY='#647887'
LIGHT='#E4ECEF'
WIDTH=4.8
DPI=300

def configure():
    plt.rcParams.update({
        'font.family':FONT,'font.size':11.5,
        'axes.labelsize':12,'xtick.labelsize':11,'ytick.labelsize':11,
        'legend.fontsize':10.5,'text.color':NAVY,'axes.labelcolor':NAVY,
        'xtick.color':NAVY,'ytick.color':NAVY,'axes.edgecolor':NAVY,
        'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,
        'axes.linewidth':.7,'savefig.facecolor':'white','figure.facecolor':'white',
        'pdf.fonttype':42,'ps.fonttype':42,
    })
    from matplotlib.font_manager import findfont, FontProperties
    path=findfont(FontProperties(family=FONT),fallback_to_default=False)
    print('FONT',path,flush=True)

def boundary(raw):
    file=raw/'seoul_boundary_osm.geojson'
    if not file.exists():
        r=requests.get('https://nominatim.openstreetmap.org/search',params={
            'city':'Seoul','country':'South Korea','format':'jsonv2',
            'polygon_geojson':1,'limit':1},headers={
            'User-Agent':'TransportCompetitionTerrainFigure/1.0 (research visualization)'},timeout=30)
        r.raise_for_status();result=r.json()[0]
        obj={'type':'Feature','properties':{k:result[k] for k in ['display_name','osm_type','osm_id','licence']},'geometry':result['geojson']}
        content=json.dumps(obj,ensure_ascii=False).encode('utf8');file.write_bytes(content)
        record={'file':file.name,'url':r.url,'retrieved':dt.datetime.now(dt.timezone.utc).isoformat(),'license':result['licence'],'period':'OSM live snapshot on retrieval date','bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        (raw/'metadata'/f'{file.name}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    obj=json.loads(file.read_text(encoding='utf8'));g=obj['geometry']
    polygons=[g['coordinates']] if g['type']=='Polygon' else g['coordinates']
    return polygons

def terrain(raw,polygons):
    vertices=np.concatenate([np.array(p[0]) for p in polygons])
    x0,y0=vertices.min(axis=0);x1,y1=vertices.max(axis=0)
    pad=.007;x0-=pad;x1+=pad;y0-=pad;y1+=pad
    lon=np.linspace(x0,x1,850);lat=np.linspace(y0,y1,740)
    xx,yy=np.meshgrid(lon,lat);zz=np.full(xx.shape,np.nan)
    for origin in [126,127]:
        data=gzip.decompress((raw/f'N37E{origin:03d}.hgt.gz').read_bytes())
        n=int(np.sqrt(len(data)/2));grid=np.frombuffer(data,dtype='>i2').reshape(n,n).astype(float)
        grid[grid==-32768]=np.nan;sel=(xx>=origin)&(xx<origin+1)
        zz[sel]=map_coordinates(grid,[(38-yy[sel])*(n-1),(xx[sel]-origin)*(n-1)],order=1,mode='nearest')
    points=np.column_stack([xx.ravel(),yy.ravel()]);inside=np.zeros(len(points),dtype=bool)
    for p in polygons:
        region=PlotPath(np.array(p[0])).contains_points(points)
        for hole in p[1:]:region&=~PlotPath(np.array(hole)).contains_points(points)
        inside|=region
    zz[~inside.reshape(xx.shape)]=np.nan
    return xx,yy,zz,(x0,x1,y0,y1)

def save(fig,out,name):
    assert all(not ax.get_title() for ax in fig.axes), 'Report figures must have no internal title'
    file=out/f'{name}.png'
    fig.savefig(file,dpi=DPI,bbox_inches='tight',pad_inches=.035)
    # A vector companion helps later PDF typesetting; PNG is the primary deliverable.
    fig.savefig(out/f'{name}.pdf',bbox_inches='tight',pad_inches=.035)
    plt.close(fig)
    with Image.open(file) as im:
        assert abs(im.info.get('dpi',(0,0))[0]-DPI)<.1
        record={'file':file.name,'pixels':list(im.size),'dpi':DPI,
                'physical_width_cm':im.width/DPI*2.54,'figsize_width_in':WIDTH}
    print('SAVED',record,flush=True)
    return record

def f1(raw,work,out,stations):
    polys=boundary(raw);xx,yy,z,extent=terrain(raw,polys)
    fig=plt.figure(figsize=(WIDTH,4.75))
    ax=fig.add_axes([.012,.175,.866,.81])
    shade=LinearSegmentedColormap.from_list('terrain_gray',['#FFFFFF','#E8EBE9','#BCC7C7','#7F9298'])
    ax.imshow(z,origin='lower',extent=extent,cmap=shade,vmin=0,vmax=500,interpolation='bilinear')
    ax.contour(xx,yy,z,levels=[50,100,200,400],colors='#839493',linewidths=.25,alpha=.5)
    for p in polys:
        outer=np.array(p[0]);ax.plot(outer[:,0],outer[:,1],color='#9CAAAE',lw=.55,zorder=2)
    cmap=LinearSegmentedColormap.from_list('net_outflow',[NAVY,'#D7EFEB',ORANGE])
    marker=ax.scatter(stations.lon,stations.lat,c=stations.net_ratio*100,
        s=6.2,cmap=cmap,norm=TwoSlopeNorm(vmin=-40,vcenter=0,vmax=40),
        edgecolors='none',alpha=.93,zorder=3,rasterized=True)
    ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect(1/np.cos(np.radians(37.55)))
    ax.set_axis_off()
    # Geographic scale; five kilometers in longitude at Seoul's latitude.
    x,y=extent[0]+.018,extent[2]+.014;dx=5/(111.32*np.cos(np.radians(37.55)))
    ax.plot([x,x+dx],[y,y],color=NAVY,lw=1.8);ax.text(x+dx/2,y+.004,'5 km',ha='center',va='bottom',fontsize=10)
    ax.annotate('N',xy=(extent[0]+.018,extent[3]-.030),xytext=(extent[0]+.018,extent[3]-.065),
        ha='center',fontsize=11,arrowprops={'arrowstyle':'-|>','color':NAVY,'lw':1})
    cbax=fig.add_axes([.17,.105,.55,.025]);cb=fig.colorbar(marker,cax=cbax,orientation='horizontal',extend='both')
    cb.set_ticks([-40,-20,0,20,40]);cb.ax.tick_params(labelsize=10,pad=2,length=2)
    cb.set_label('순유출률 (%)',fontsize=11,labelpad=1)
    fig.text(.115,.118,'순유입',ha='right',va='center',fontsize=11,color=NAVY)
    fig.text(.775,.118,'순유출',ha='left',va='center',fontsize=11,color=ORANGE)
    zax=fig.add_axes([.897,.28,.017,.50]);sm=plt.cm.ScalarMappable(norm=Normalize(0,500),cmap=shade)
    zcb=fig.colorbar(sm,cax=zax,ticks=[0,100,300,500]);zcb.set_label('배경 DEM 고도 (m)',labelpad=5,fontsize=10.5)
    zcb.ax.tick_params(labelsize=9.5,length=2,pad=2)
    return save(fig,out,'F1_서울_고도와_순유출률')

def f2(work,out):
    d=pd.read_csv(work/'directions.csv')
    d=d[(d.dem=='delta_m')&(d.month=='all')&d.threshold_m.isin([10,20,30])].sort_values('threshold_m')
    assert np.allclose(d.down_up,[1.288142422112907,1.5825657666927193,1.825716352656245])
    d.to_csv(out/'F2_핵심수치.csv',index=False,encoding='utf-8-sig')
    fig,ax=plt.subplots(figsize=(WIDTH,3.05));fig.subplots_adjust(left=.12,right=.99,bottom=.20,top=.93)
    bars=ax.bar(range(3),d.down_up,width=.55,color=[NAVY,TEAL,ORANGE],zorder=3)
    ax.axhline(1,color=GRAY,lw=1,ls=(0,(4,3)),zorder=2)
    ax.text(-.48,2.06,'점선: 내리막과 오르막 통행이 같은 경우(1배)',ha='left',va='top',fontsize=9.5,color=GRAY,zorder=5)
    for bar,ratio,down,up in zip(bars,d.down_up,d.down,d.up):
        ax.text(bar.get_x()+bar.get_width()/2,ratio+.045,f'{ratio:.3f}배',ha='center',va='bottom',fontsize=15,fontweight='bold',color=bar.get_facecolor())
    ax.set(xticks=range(3),xticklabels=[f'{x}m 초과' for x in d.threshold_m],
           ylabel='내리막 / 오르막 통행 수 (배)',ylim=(0,2.08),xlim=(-.5,2.5))
    ax.set_yticks([0,.5,1,1.5,2]);ax.grid(axis='y',color=LIGHT,lw=.6);ax.set_axisbelow(True)
    ax.set_xlabel('출발·도착 대여소의 고도차',labelpad=5)
    return save(fig,out,'F2_고도차별_내리막_우세')

def bin_means(stations):
    s=stations.copy();s['bin_lower_m']=(s.elevation//10*10).astype(int);rows=[]
    for lo,g in s.groupby('bin_lower_m'):
        values=g.net_ratio.to_numpy()*100;n=len(values);mean=values.mean()
        ci=stats.t.ppf(.975,n-1)*values.std(ddof=1)/np.sqrt(n) if n>=2 else np.nan
        # Intersect t intervals with the known [-100%,100%] parameter space.
        rows.append({'bin_lower_m':int(lo),'bin_upper_m':int(lo+10),'n_stations':n,'mean_pct':float(mean),
                     'ci_low_pct':float(max(-100,mean-ci)) if n>=2 else np.nan,
                     'ci_high_pct':float(min(100,mean+ci)) if n>=2 else np.nan})
    return pd.DataFrame(rows)

def f3(work,out,stations,metrics):
    b=bin_means(stations);b.to_csv(out/'F3_고도구간_평균과_CI.csv',index=False,encoding='utf-8-sig')
    beta=next(x for x in metrics['station_models'] if x['model']=='net_ratio_joint' and x['term']=='elev10')
    fig,ax=plt.subplots(figsize=(WIDTH,3.75));fig.subplots_adjust(left=.115,right=.99,bottom=.25,top=.98)
    for row in b.itertuples():
        color=TEAL if row.bin_lower_m<80 else ORANGE
        if row.n_stations>=2:
            err=np.array([[row.mean_pct-row.ci_low_pct],[row.ci_high_pct-row.mean_pct]])
            ax.errorbar(row.bin_lower_m+5,row.mean_pct,yerr=err,fmt='o',markersize=5.5,
                markerfacecolor=color if row.n_stations>=10 else 'white',markeredgecolor=color,
                color=color,elinewidth=1.1,capsize=2.5,zorder=4)
        else:ax.scatter(row.bin_lower_m+5,row.mean_pct,s=28,facecolors='white',edgecolors=GRAY,zorder=4)
    ax.plot(b.bin_lower_m+5,b.mean_pct,color=TEAL,lw=1.1,alpha=.55,zorder=2)
    ax.axhline(0,color=GRAY,lw=.8,zorder=2)
    ax.set(xlim=(-11,121),ylim=(-28,106),ylabel='평균 순유출률 (%)')
    ax.set_xticks(b.bin_lower_m+5,labels=['<0' if x<0 else str(x) for x in b.bin_lower_m])
    ax.tick_params(axis='x',labelsize=10,pad=3)
    ax.set_yticks([-20,0,20,40,60,80,100]);ax.grid(axis='y',color=LIGHT,lw=.6);ax.set_axisbelow(True)
    ax.set_xlabel('고도 구간 하한 (m; 구간 폭 10m)',labelpad=23)
    # A separate N row makes sparse high-altitude bins visible at report scale.
    ax.text(-.075,-.125,'대여소 수',transform=ax.transAxes,ha='right',va='center',fontsize=9.2,color=GRAY)
    for row in b.itertuples():
        ax.text(row.bin_lower_m+5,-.125,str(row.n_stations),transform=ax.get_xaxis_transform(),ha='center',va='center',fontsize=9.2,color=GRAY)
    ax.text(5,94,"다른 조건을 같게 맞추면\n"+f"고도 10m당 +{100*beta['beta']:.2f}%p",
        ha='left',va='top',fontsize=11.5,fontweight='bold',color=NAVY,
        bbox={'facecolor':'white','edgecolor':'none','pad':3},zorder=5)
    return save(fig,out,'F3_고도구간별_평균_순유출률'),b

def f4(work,out):
    s=pd.read_csv(work/'policy_scenarios.csv');s=s[s.uphill10_flow_shift_fraction.isin([0,.25,.5])].copy()
    s['tonnes_co2e']=s.kg_co2e/1000;s['avoided_tonnes_co2e']=s.avoided_kg_co2e/1000
    s.to_csv(out/'F4_시나리오_핵심수치.csv',index=False,encoding='utf-8-sig')
    fig,ax=plt.subplots(figsize=(WIDTH,3.3));fig.subplots_adjust(left=.12,right=.99,bottom=.22,top=.94)
    bars=ax.bar(range(3),s.tonnes_co2e,width=.57,color=[NAVY,TEAL,ORANGE],zorder=3)
    for j,(bar,row) in enumerate(zip(bars,s.itertuples())):
        ax.text(j,row.tonnes_co2e+.22,f'{row.tonnes_co2e:.2f}t',ha='center',va='bottom',fontsize=15,fontweight='bold',color=bar.get_facecolor())
        if j:
            pct=row.avoided_tonnes_co2e/s.tonnes_co2e.iloc[0]*100
            ax.text(j,row.tonnes_co2e*.52,f'-{row.avoided_tonnes_co2e:.2f}t\n(-{pct:.1f}%)',
                ha='center',va='center',fontsize=13,fontweight='bold',color='white',linespacing=1.45)
    ax.set(xticks=range(3),xticklabels=['기준모형','오르막 보충\n25% 대체','오르막 보충\n50% 대체'],
        ylabel='운영 배출 추정 (tCO₂e / 3개월)',ylim=(0,16.5),xlim=(-.5,2.5))
    ax.set_yticks([0,5,10,15]);ax.grid(axis='y',color=LIGHT,lw=.6);ax.set_axisbelow(True)
    ax.text(.98,.98,'공개 자료 기반 추정',transform=ax.transAxes,ha='right',va='top',fontsize=10.5,color=GRAY)
    return save(fig,out,'F4_재배치_탄소_정책시나리오')

def readme(out,meta,metrics,bins):
    table='\n'.join(f"| {x['file']} | {x['pixels'][0]}×{x['pixels'][1]} | {x['physical_width_cm']:.2f}cm |" for x in meta)
    btable='\n'.join(f"| [{int(x.bin_lower_m)}, {int(x.bin_upper_m)}) | {x.n_stations} | {x.mean_pct:.2f} | {'미산출(n=1)' if x.n_stations<2 else f'[{x.ci_low_pct:.2f}, {x.ci_high_pct:.2f}]'} |" for x in bins.itertuples())
    text=f'''# 보고서용 최종 그림 세트

2026-10-12 · F1–F4 · PNG 300dpi + 동일 내용 PDF. 모든 그림 내부 제목 없음, {FONT}, 남색 `#183B56`·청록 `#078C8C`·강조 주황 `#EA8337`. 본문 삽입 폭 **{WIDTH*2.54:.1f}cm** 기준 `figsize` 폭 {WIDTH:.1f}인치, 주요 글자 11–15pt. 여백 제거에 따라 실제 PNG 물리 폭은 아래와 같으며 문서에서는 비율 유지·{WIDTH*2.54:.1f}cm 폭으로 삽입한다.

| 파일 | PNG 픽셀 | 300dpi 물리 폭 |
|---|---:|---:|
{table}

코드: `report_figures.py`. 실행: `python report_figures.py` (기존 probe 집계 필요; 차량 연료·GPS 실측 보정 없음). `summary_figure.py`가 같은 집계로 F5를 생성한다. 보고서 번호는 그림 1=F1, 그림 2=F3, 그림 3=F2, 그림 4=F4, 그림 5=F5다.

## 공통 데이터·해석

- 기간: 2026년 1·4·6월 전체. 이용시간 1–180분, 대여/반납소가 2026-06 마스터에 모두 연결된 **9,427,594건**. 동일 대여소 왕복은 대여소 불균형 집계에 포함하고 방향 비교에서 제외.
- 순유출률 `(대여-반납)/(대여+반납)×100`. 양수는 보충이 필요한 방향, 음수는 사용자 통행으로 자전거가 쌓이는 방향의 압력. **실제 품절시간·재고량을 측정한 지표는 아니다.**
- 서울시 [대여이력 OA-15182](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do), [대여소 OA-13252](https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do), 취득 2026-10-12, 공공누리 1유형(출처표시·상업적 이용·변경 가능).
- DEM: [AWS Terrain Tiles / Mapzen Skadi](https://registry.opendata.aws/terrain-tiles/), N37E126·N37E127. 1 arcsecond 약 30m 격자, 원천의 명목 품질은 90m일 수 있음. 현재 도로·교량 높이 또는 실제 통행 경로 누적 상승고도와 다를 수 있다. [출처 표시](https://github.com/tilezen/joerd/blob/master/docs/attribution.md): Mapzen; global GMTED2010 and SRTM terrain data courtesy of the U.S. Geological Survey.
- 배출계수: [UK DESNZ 2025 full set](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025), `Delivery vehicles!D30`, 디젤 Class III 밴 0.27878kgCO2e/차량-km, UK OGL v3.0. 서울 실제 차량 조성을 확인한 값이 아닌 공개 대리계수. Scope 1 운행만 포함.

## F1 서울 고도와 대여소 순유출률

파일: [PNG](F1_서울_고도와_순유출률.png) / [PDF](F1_서울_고도와_순유출률.pdf)

**핵심 수치:** 이용이 있는 2,773개 대여소. 순유출률 색상 ±40%에서 포화(색상 막대의 삼각형으로 표시). 배경은 DEM 고도 0–500m, 등고선 50·100·200·400m. 지도 윤곽은 OSM 서울특별시 행정경계. 점의 위치별 고도와 불균형을 함께 보여준다.

**캡션 초안:** “서울의 고지대 대여소에서는 순유출이, 저지대에서는 순유입이 두드러진다. 점의 색은 2026년 1·4·6월 대여·반납의 순유출률, 배경 음영과 등고선은 DEM 고도를 나타낸다. 이는 자전거 부족·축적 압력이며 실제 빈 대여소 비율을 뜻하지 않는다.”

**출처:** `station_total.csv`, 원본 DEM 2타일, [OSM 서울특별시 경계 relation 2297418](https://www.openstreetmap.org/relation/2297418), Nominatim 2026-10-12 취득. 경계 데이터 © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright). 원본 경계는 설정한 원본 폴더의 `seoul_boundary_osm.geojson` 및 `metadata/seoul_boundary_osm.geojson.json`; 보고서의 그림 출처에 OSM attribution을 포함한다.

## F2 고도차가 커질수록 내리막 통행 우세

파일: [PNG](F2_고도차별_내리막_우세.png) / [PDF](F2_고도차별_내리막_우세.pdf)

| 절대 고도차 조건 | 내리막 통행 | 오르막 통행 | 내리막/오르막 |
|---|---:|---:|---:|
| 10m 초과 | 1,099,816 | 853,800 | 1.288배 |
| 20m 초과 | 319,922 | 202,154 | 1.583배 |
| 30m 초과 | 116,090 | 63,586 | 1.826배 |

세 막대는 **서로 중첩된 임계값 표본**이며 서로 배타적인 구간이 아니다. 30m 초과 통행은 20m·10m 초과에도 포함된다. 1배 점선은 양방향 통행 수가 같음을 뜻한다. 이 그림은 단순 통행 비율이며 거리 통제 회귀결과 자체는 아니다(별도 probe에서 거리 구간·OD 회귀 검증 완료).

**캡션 초안:** “출발·도착 대여소의 고도차가 10·20·30m를 초과하는 통행에서 내리막 이용은 오르막보다 각각 1.288·1.583·1.826배 많았다. 고도차가 큰 통행일수록 이용 방향의 비대칭이 커졌다. 각 임계값 표본은 중첩되며 동일 대여소 왕복은 제외했다.”

**출처:** `directions.csv`(bilinear DEM, 전체 3개월), 원천 서울시 대여이력·대여소 및 AWS DEM. 그림 수치는 `F2_핵심수치.csv`.

## F3 고도 10m 구간별 평균 순유출률

파일: [PNG](F3_고도구간별_평균_순유출률.png) / [PDF](F3_고도구간별_평균_순유출률.pdf)

**핵심 수치:** 점·연결선은 3개월 대여소별 순유출률을 고도 10m 구간에서 **동일 가중 산술평균**한 원자료 요약. 수염은 대여소 간 표준오차와 Student t를 이용한 평균의 95% 신뢰구간, 지표의 가능한 범위 [-100%,100%]와 교차해 표시. n=1인 0m 미만 구간은 신뢰구간을 산출하지 않았다. 속이 빈 점은 n<10; 고지대 소표본 신뢰구간을 강한 일반화 근거로 쓰지 않는다. 대여소 간 공간 상관을 반영하지 않은 구간별 기술통계 CI다.

**별도 회귀 주석:** 자치구·월 고정효과, 국지 DEM 경사, log 이용량, log 거치 규모 통제 후 **+6.45%p/10m**, 대여소 군집 95% CI **+5.81~+7.08%p**. 8,152개 대여소-월. 원자료 구간 평균/CI와 통제 후 회귀계수/CI는 다른 통계이며 하나의 회귀선으로 합치지 않았다.

**캡션 초안:** “대여소 고도가 높아질수록 순유출률이 커졌다. 점은 고도 10m 구간별 대여소 평균, 수염은 평균의 95% 신뢰구간이다. 별도 회귀에서도 자치구·월·이용량·거치 규모·DEM 경사를 통제한 고도 10m 상승은 순유출률 6.45%p 증가와 연결됐다(95% CI 5.81–7.08%p). 고지대 일부 구간은 표본이 적다.”

| 고도 구간(m) | 대여소 수 | 평균(%) | 95% CI(%) |
|---|---:|---:|---:|
{btable}

**출처:** `station_total.csv`, `metrics.json`의 `net_ratio_joint/elev10`. 그림용 집계 `F3_고도구간_평균과_CI.csv`.

## F4 공개 자료 기반 재배치 탄소 추정과 정책 시나리오

파일: [PNG](F4_재배치_탄소_정책시나리오.png) / [PDF](F4_재배치_탄소_정책시나리오.pdf)

| 시나리오 | 배출 추정(tCO2e/3개월) | 기준 대비 감소 | 필요한 추가 이용자 오르막 통행 |
|---|---:|---:|---:|
| 기준모형 | 14.36 | - | 0 |
| 오르막 보충 25% 대체 | 11.79 | 2.57t, 17.9% | 약 59,812건 |
| 오르막 보충 50% 대체 | 9.21 | 5.15t, 35.9% | 약 119,624건 |

**재배치 부담:** 월말 재고를 월초 수준으로 복원하는 최소비용 수송 기준으로 414,293대, 최소 528,453 자전거-km. 이 중 10m 이상 위로 보충하는 흐름 239,247대, 378,919 자전거-km. 실제 배송 경로·재고·트럭 대수가 아니다.

**가정:** `차량-km = 최소 자전거-km ÷ 적재 20대 × 도로 우회 1.3 × 공차·경로 배수 1.5`. `CO2e = 차량-km × 0.27878kg/km`. 기준 51,524 차량-km 환산. 25% 시나리오 42,288km, 50% 시나리오 33,052km. 실제 차량 연료·GPS 보정은 하지 않았다.

**정책 대체의 정의:** 최소비용 흐름 중 고도 10m 이상 상승하는 보충의 일부를, 동일 출발·도착 대여소에서 이용자의 추가 오르막 통행으로 대체하고 나머지 흐름을 유지한다. 대체율은 가정이며 관측된 참여율·인과효과가 아니다. 고지대 전체 순유출의 25%를 일괄 감소시킨다는 뜻도 아니다. 전기자전거·인센티브에 적용하려면 해당 이용자 이동을 실제 유도한다는 조건이 필요하다.

**불확실성:** 적재 10/20/40대 × 도로 1.0/1.3/1.6 × 공차·경로 1.0/1.5/2.0의 27조합에서 기준 배출 3.68–47.14tCO2e. 이는 가정 민감도 범위이며 통계적 신뢰구간이 아니다. 충전·제조·정비·회피 자동차 통행은 포함하지 않아 따릉이 전체의 순 탄소효과로 해석하지 않는다.

**캡션 초안:** “공개 이용이력과 DEM으로 계산한 최소 재배치 부담에 차량 운행 가정을 적용하면, 3개월 기준 운영 배출은 14.36tCO2e로 추정된다. 10m 이상 오르막 보충의 25%·50%를 이용자 이동이 대체하는 조건에서 배출은 각각 11.79·9.21tCO2e로 감소한다. 적재 20대·도로 우회 1.3·공차/경로 1.5 및 영국 공개 디젤 밴 배출계수를 적용한 시나리오 추정이다.”

**출처:** `policy_scenarios.csv`, `rebalance_metrics.json`, 서울시 이력·대여소, AWS DEM, UK DESNZ 2025 공개 배출계수. 그림 수치는 `F4_시나리오_핵심수치.csv`.

## 검수

PNG의 300dpi 메타데이터, 원 집계와 핵심 수치 일치, 모든 고도 구간의 대여소 합계 2,773개, F4 배출·감소량 산술을 검사한다. 각 그림은 이미지로 열어 글자·범례·주석·여백과 겹침을 확인한다. 원본 데이터·환경은 커밋하지 않고 그림 생성 코드와 재현 안내만 커밋한다. push하지 않는다.
'''
    (out/'README.md').write_text(text,encoding='utf8')
    (out/'figure_manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')

def preview(work,out,meta):
    cards=[]
    for item in meta:
        im=Image.open(out/item['file']).convert('RGB');im.thumbnail((1050,800))
        canvas=Image.new('RGB',(1100,850),'#f1f4f5');canvas.paste(im,((1100-im.width)//2,30));ImageDraw.Draw(canvas).text((20,820),item['file'].split('_')[0],fill=NAVY)
        cards.append(canvas)
    sheet=Image.new('RGB',(2200,1700),'white')
    for i,card in enumerate(cards):sheet.paste(card,((i%2)*1100,(i//2)*850))
    sheet.save(out/'preview.png')

def main(raw,work,out=None,width=4.8):
    global WIDTH
    WIDTH=width
    configure();out=out or work/'report'/'figs';out.mkdir(parents=True,exist_ok=True)
    s=pd.read_csv(work/'station_total.csv');m=json.loads((work/'metrics.json').read_text(encoding='utf8'))
    meta=[f1(raw,work,out,s),f2(work,out)];third,bins=f3(work,out,s,m);meta+=[third,f4(work,out)]
    assert bins.n_stations.sum()==m['n_stations']==2773
    assert np.isclose((pd.read_csv(out/'F4_시나리오_핵심수치.csv').kg_co2e+pd.read_csv(out/'F4_시나리오_핵심수치.csv').avoided_kg_co2e).std(),0,atol=1e-8)
    readme(out,meta,m,bins);preview(work,out,meta)
    print('COMPLETE',out,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--raw',type=Path,default=RAW);parser.add_argument('--work',type=Path,default=WORK);parser.add_argument('--out',type=Path);parser.add_argument('--width',type=float,default=4.8);args=parser.parse_args();main(args.raw,args.work,args.out,args.width)
