"""Produce the requested Korean probe handoff from verified local results."""
import argparse
import json
import math
from pathlib import Path
import pandas as pd
from probe import RAW,WORK

def load(name):return json.loads((WORK/name).read_text(encoding='utf8'))

def main():
    m=load('metrics.json');c=load('rebalance_metrics.json');r=load('robustness.json');i=load('inferred_metrics.json')
    b=next(x for x in m['station_models'] if x['model']=='net_ratio_joint' and x['term']=='elev10')
    by=next(x for x in m['station_models'] if x['model']=='net_per_day_joint' and x['term']=='elev10')
    d20=next(x for x in m['directions'] if x['dem']=='delta_m' and x['threshold_m']==20 and x['month']=='all')
    base=c['scenarios'][0];s25=c['scenarios'][2]
    raw_n=sum(x['raw_rows'] for x in m['qa']);valid_n=sum(x['valid_duration_rows'] for x in m['qa'])
    qa='\n'.join(f"| {q['month']} | {q['raw_rows']:,} | {q['valid_duration_rows']:,} | {q['matched_rows']:,} | {q['same_station_rows']:,} |" for q in m['qa'])
    monthly='\n'.join(f"| {x['month']} | {x['bikes']:,.0f} | {x['bike_km']:,.0f} | {x['uphill10_bikes']:,.0f} |" for x in c['months'])
    scen='\n'.join(f"| {x['uphill10_flow_shift_fraction']:.0%} | {x['additional_user_uphill_trips']:,.0f} | {x['vehicle_km_equivalent']:,.0f} | {x['kg_co2e']/1000:.2f} | {x['avoided_kg_co2e']/1000:.2f} |" for x in c['scenarios'])
    robust='\n'.join(f"| {x['model']} | {100*x['beta']:.2f} | [{100*x['ci_low']:.2f}, {100*x['ci_high']:.2f}] | {x['n']:,} |" for x in r['models'] if x['term'] in ['elev10','median10'])
    od=m['od_model'][0];corr=next(x for x in m['correlations'] if x['x']=='elevation' and x['y']=='net_ratio')
    inference_carbon=i['straight_line_bike_km']/20*1.3*1.5*c['factor']['kg_co2e_per_vehicle_km']/1000
    # Keep valid standard JSON after older runs that stored NaN for undefined R2.
    def clean(v):
        if isinstance(v,float) and not math.isfinite(v):return None
        if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list):return [clean(x) for x in v]
        return v
    (WORK/'metrics.json').write_text(json.dumps(clean(m),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    manifest=[]
    for p in sorted((RAW/'metadata').glob('*.json')):
        q=json.loads(p.read_text(encoding='utf8'));manifest.append(q)
    pd.DataFrame(manifest).to_csv(WORK/'data_inventory.csv',index=False,encoding='utf-8-sig')
    report=f'''판정: 성립(지형과 이용 불균형의 연관성). 2026년 1·4·6월 {m['n_trips']:,}건, 고도 10m당 순유출률 +{100*b['beta']:.2f}%p; 고도차 20m 초과 내리막/오르막 {d20['down_up']:.3f}배.
탄소: 월별 최소비용 수송 기준모형 {base['kg_co2e']/1000:.2f}tCO2e/3개월; 10m 이상 오르막 보충의 25%를 이용자가 대체하면 조건부 {s25['avoided_kg_co2e']/1000:.2f}tCO2e 감소(실측 아님).
권고: 서울 전역·계절별 검증과 지형을 고려한 보상 설계를 중심으로 진행. 실제 차량 연료·배송 GPS·일별 재고로 탄소 모형을 보정하는 것이 다음 우선순위.

# 언덕이 만드는 탄소: 따릉이 재배치의 역설

작성·취득 기준: 2026-10-12, worker 따릉이 Sol. 사전 탐색 결과이며 제출용 5장 본문은 별도 편집 대상이다.

## 핵심 수치와 판정 범위

- 고도와 순유출률의 Pearson r={corr['pearson']:.3f}, Spearman rho={corr['spearman']:.3f}, 이용 대여소 {m['n_stations']:,}개. 마스터는 2,789개이며 3개월 동안 연결 가능한 이용이 있는 대여소 수가 다르다.
- 순유출률=(대여-반납)/(대여+반납). 자치구·월 고정효과, log(일평균 이용량+1), log(거치규모+1), 국지 DEM 경사 통제 후 고도 10m당 **+{100*b['beta']:.2f}%p**(대여소 군집 95% CI {100*b['ci_low']:.2f}–{100*b['ci_high']:.2f}%p). 이는 대여량의 증가율이 아닌 순유출률의 퍼센트포인트 변화다.
- 같은 통제에서 순유출 대수는 고도 10m당 **+{by['beta']:.2f}대/일**(95% CI {by['ci_low']:.2f}–{by['ci_high']:.2f}). 대여소-월 {m['n_station_month']:,}개를 분석했다.
- 순유출률 회귀 R²={b['r2']:.3f}. 지형(고도+DEM 경사) 추가 시 R² +{m['incremental_r2_terrain']:.3f}. 이는 관측 불균형의 설명력이며 인과기여율이나 탄소의 지형 기여율이 아니다.
- 고도차 **20m 초과** 통행: 내리막 {d20['down']:,}건, 오르막 {d20['up']:,}건, 내리막 비율 {100*d20['down_share']:.2f}% / {d20['down_up']:.3f}배. 10m 초과에서는 1.288배, 30m 초과에서는 1.826배.
- 같은 대여소 쌍의 양방향을 묶고 거리·월·고/저지대 자치구를 통제한 binomial 회귀: 절대 고도차 +10m당 내리막 선택 odds ratio **{math.exp(od['beta']):.3f}**(95% CI {math.exp(od['ci_low']):.3f}–{math.exp(od['ci_high']):.3f}). {m['od_model_pair_months']:,}쌍-월, {m['od_model_trips']:,}통행, 대여소 쌍 군집 표준오차. 고도차>=5m, 직선거리>=100m, 쌍별 월 통행>=10 조건. 같은 쌍은 양방향 직선거리가 같으므로 방향별 단순 거리 구성 차이도 줄였다. 토지이용·통근 목적은 완전히 제거하지 못한다.
- 월별 고도 계수는 1월 +6.75%p, 4월 +6.37%p, 6월 +6.20%p. 겨울·봄·초여름 모두 부호가 같다. 가을·연간 전체로 일반화하지 않는다.
- 10m 초과 내리막/오르막: 평일 7–9시 1.488배, 17–19시 1.199배, 평일 나머지 1.275배, 주말 1.267배. 출퇴근 역방향이 일부 상쇄해도 내리막 우세가 남는다.
- **고도·상대고도의 결과는 강건하다. 국지 경사 그 자체의 독립 효과는 약하다.** 경사 1%p 계수는 순유출률 +0.196%p(p=0.015, 대여소 군집)이지만 자치구 군집에서는 p=0.095; 원시 순유출 대수 회귀에서는 p=0.230. 따라서 “주변 경사만으로 모두 설명”한다고 쓰면 안 된다.

판정은 **‘고지대에서 순유출되고 내리막 통행이 우세한 연관성’에 한정해 성립**이다. 순유출은 재고를 줄이는 압력이며 실제 빈 거치대 시간 비율은 아니다. 트럭이 위로 보충하는 해석은 아래 간접 이동 증거와 일치하지만 차량 운행 원장이 없으므로 실제 트럭 배출량·순 탄소중립 효과·지형의 인과효과까지 입증한 것은 아니다.

## 데이터 목록·출처·라이선스

원본: 설정한 원본 폴더 / 상세 URL·크기·SHA256: 원본 `metadata/*.json`과 작업 `data_inventory.csv`. 원본을 수정하거나 Git에 넣지 않았다.

| 자료 | 범위·기준시점 | 출처 | 이용허락·한계 |
|---|---|---|---|
| 대여·반납 원본 CSV 3개 | 2026-01, 04, 06 월 전체, 공식 게시 2026-07-15 | [서울 OA-15182](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do), infSeq=1, seq=144/148/150 | 공공누리 1유형: 출처표시, 상업적 이용·변경 가능. 로그인 불필요 |
| 대여소 마스터 XLSX | 주분석 2026-06, 과거 좌표 확인 2025-12·06 | [서울 OA-13252](https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do), infSeq=2, seq=24/23/22 | 공공누리 1유형. 2026-06 파일 2,789개; 공통 ID의 좌표 변경 50m 이상 0개 |
| 고도 HGT gzip 2개 | N37E126 / N37E127; 정적 모자이크, 취득 2026-10-12 | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/), [N37E126](https://s3.amazonaws.com/elevation-tiles-prod/skadi/N37/N37E126.hgt.gz), [N37E127](https://s3.amazonaws.com/elevation-tiles-prod/skadi/N37/N37E127.hgt.gz) | Mapzen/USGS 출처표시 및 개별 원천 이용조건. [원천·라이선스](https://github.com/tilezen/joerd/blob/master/docs/attribution.md). 1 arcsecond 약 30m 격자이나 SRTM 원천 명목 품질은 90m일 수 있음; 한국 타일별 원천 footprint를 이번에 개별 판독하지 않음 |
| 차량 배출계수 XLSX | UK DESNZ 2025 v1.0, 취득 2026-10-12 | [공식 full set](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025), Delivery vehicles D30/E30 | UK OGL v3.0. 디젤 Class III 밴 0.27878 kgCO2e/km, CO2만은 0.27712 kg/km. 서울 실차 대리계수 |
| 공식 시민참여 재배치 자료 | 서울시 2024-05-02 발표, 2023 사업실적 | [서울시 보도자료](https://news.seoul.go.kr/traffic/archives/512211) | 읽기·인용 근거; 별도 재배포 권한은 확인하지 않아 원문 재배포하지 않음. 2023년 참여 106,312회, 과다거치 민원 33%·부족신고 13% 감소 발표 |

Terrain attribution: Mapzen; Global GMTED2010 and SRTM terrain data courtesy of the U.S. Geological Survey. DEM은 2000년 SRTM 등 원천을 결합한 것으로 현재 도로·건물·지하 또는 교량의 실제 자전거 높이와 다를 수 있다. bilinear 보간 고도 범위 -1.04–117.32m, 고도 결측 0개. 약 150–185m 폭의 차분을 국지 DEM 경사로 정의했으며 도로 종단경사로 부르지 않는다.

로그인 때문에 중단한 데이터는 없다. 국토지리정보원·NASA 인증 다운로드 대신 무료 AWS DEM을 사용했다. 한국행정연구원 2024 브리프 다운로드는 인증서 검증 오류로 사용하지 않고, 서울시 공식 시민참여 재배치 자료로 대체했다. 실제 배송 GPS·연료·차량제원·전수 재배치 운영 원장은 확보하지 못했다.

## 전처리·검증

| 월 | 원본 행 | 이용시간 1–180분 | 양 끝 마스터 연결 | 동일 대여소 왕복 |
|---|---:|---:|---:|---:|
{qa}
| 합계 | {raw_n:,} | {valid_n:,} | {m['n_trips']:,} | {sum(q['same_station_rows'] for q in m['qa']):,} |

- 생년·성별·이용자 속성은 읽지 않았다. 기본 통행은 이용시간 1–180분을 사용하며 0분 취소·초단시간과 180분 초과를 제외했다. 보고 거리 0인 기록도 유지했다. 방향 비교에서 동일 대여소 왕복만 제외했다.
- 각 월의 대여·반납 합계는 위 표의 해당 연결 건수와 정확히 같다. 3개월 전체 대여·반납 각각의 합계는 {m['n_trips']:,}건이다. OD 합계, 대여소 집계, 일별 집계가 일치한다.
- 대여소 마스터 ID 중복 0개. 2025-12 ↔ 2026-06 공통 2,780개, 2025-06 ↔ 2026-06 공통 2,737개에서 50m 이상 좌표 차이 0개. 마스터의 좌표 미갱신 가능성은 남는다.
- 월별 이용량 100건 미만 대여소-월을 회귀에서 제외했다. 500m 안 다른 대여소가 없는 경우 상대고도는 결측으로 두고 해당 회귀에서만 제외했다.
- 월초·말일을 제외한 완전한 85일의 일별 순유출 양수 합은 {m['daily_net_relocation_proxy_sum']:,.0f}대, 일평균 {m['daily_net_relocation_proxy_mean']:,.0f}대다. 일별 양수 합은 초기/최종 재고 및 운행 중 자전거 때문에 실제 배송 수요와 같지 않다.

고도 10m당 순유출률 계수 강건성:

| 모형 | 계수(%p/10m) | 95% CI(%p) | 대여소-월 |
|---|---:|---:|---:|
{robust}

이용량 가중 회귀에서는 +3.82%p로 줄지만 양수이며 유의하다. DEM 5×5 중앙값을 사용해도 +7.01%p, OD 20m 초과 내리막/오르막 1.692배로 결과 방향이 유지된다. 월·대여소 고정효과를 동시에 두고 고도 계수를 추정한 것은 아니다(시간불변 고도는 대여소 고정효과에 흡수됨).

## 비대여기간 이동의 간접 증거

월 안에서 자전거번호별 원본 전체를 대여시간 순서로 정렬하고, 직전 반납소와 다음 대여소가 다르며 두 위치가 100m 이상 떨어진 연속 기록을 추출했다. 이동 간격 0–72시간인 경우:

- 추정 위치 이동 **{i['inferred_displacements']:,}건**, 합계 {i['straight_line_bike_km']:,.0f} 자전거-km.
- 고도차 10m 초과 오르막 **{i['uphill10']:,}건**, 내리막 **{i['downhill10']:,}건**, 오르막/내리막 **{i['up_down_ratio']:.2f}배**.
- ‘이용자 통행은 내리막, 이용 사이 위치변경은 오르막’이라는 반대 방향성이 관찰된다. 정비 회수·재투입, 기록 누락, 수작업 이동도 포함되므로 전부 트럭 재배치라고 확정하지 않는다. 겹치는 시간 기록은 제외하며 월 경계를 넘겨 연결하지 않는다. 6·24·72·168시간 민감도는 `inferred_moves.csv`.
- 같은 차량 환산 가정을 이 이동에 적용하면 {inference_carbon:.2f}tCO2e이지만 운영 전체의 실측값이 아니다. 월별 순불균형 흐름과 포함 범위가 달라 두 수치를 상·하한으로 해석하지 않는다.

## 재배치·탄소 확장 추정

각 월 순유입 대여소가 공급하고 순유출 대여소가 수요를 갖는 균형 수송문제를 설정했다. `min Σ 거리_ij × 이동자전거_ij`, 공급·수요 제약은 월별 순불균형과 일치시켰다. 거리=대여소 좌표의 haversine 직선거리. 월말 재고를 월초 수준으로 되돌리고 신규·폐기·정비 유출입이 없다는 가정이다. 3개월을 연속 1년으로 외삽하지 않았다.

| 월 | 재고복원 필요 대수(모형) | 최소 자전거-km | 10m 이상 오르막 보충 대수 |
|---|---:|---:|---:|
{monthly}
| 합계 | {c['total_bikes']:,.0f} | {c['total_bike_km']:,.0f} | {c['uphill10_bikes']:,.0f} |

3개 월 모두 HiGHS 최적해, 공급·수요 잔차 0. 차량 경로 최적화가 아니라 수송량 최적화다. 트럭 수, 거점, 도로 연결, 적재·하역 시간, 일중 품절은 제약에 없다.

`차량-km 환산 = 최소 자전거-km / 적재 20대 × 도로 우회 1.3 × 공차·경로 배수 1.5`

`운영 CO2e = 차량-km 환산 × 0.27878 kgCO2e/km`

기준 환산 거리 **{base['vehicle_km_equivalent']:,.0f}km**, 배출 **{base['kg_co2e']/1000:.2f}tCO2e**(CO2만 계산 시 약 {base['vehicle_km_equivalent']*c['factor']['kg_co2_per_vehicle_km']/1000:.2f}t). 적재 20대·도로 1.3·공차 1.5는 실측에 맞춘 계수가 아니라 시나리오 가정이다. 차량 배출계수는 영국 디젤 밴 대리값이며 실제 서울 재배치 차량의 경사·정체·전기차 비중은 반영하지 않았다. Scope 1 운행만 포함하고 전주기·연료 생산·차량/자전거 제조·회피 자동차 통행은 제외했다.

적재 10/20/40대 × 도로 1.0/1.3/1.6 × 공차·경로 1.0/1.5/2.0의 27조합 민감도 **{c['sensitivity_kg_co2e_range'][0]/1000:.2f}–{c['sensitivity_kg_co2e_range'][1]/1000:.2f}tCO2e**. 이것은 통계적 신뢰구간이 아니다. 적재 20대의 이상적 만재 직선 이동 하한은 {c['mathematical_loaded_vehicle_km_lower_bound_Q20']:,.0f} 차량-km이며, 가정 배수를 넣은 51,524km를 수학적 하한이라고 부르지 않는다.

## 제안 시나리오

기준 최적흐름 중 **10m 이상 위로 보충하는 흐름**을 시민의 추가 오르막 대여·반납이 같은 출발/도착 대여소 쌍에서 대체한다고 가정한다. 이는 고지대 전체 순유출을 일괄 x% 줄이는 것과 같지 않다. 대체된 흐름만 제거하고 나머지 경로를 유지하는 조건부 계산이며 참여율·효과 크기를 데이터로 추정한 것은 아니다.

| 오르막 보충 대체율 | 필요 추가 이용자 통행 | 차량-km 환산 | 잔여 tCO2e | 감소 tCO2e |
|---|---:|---:|---:|---:|
{scen}

25% 대체는 3개월 약 **{s25['additional_user_uphill_trips']:,.0f}건**의 추가 오르막 이동, 약 **{s25['avoided_kg_co2e']/1000:.2f}tCO2e** 조건부 감소다. 1월·4월·6월 91일 기준 하루 약 {s25['additional_user_uphill_trips']/91:,.0f}건이다. 대체 통행이 원래 하려던 이동인지, 보상만을 위한 추가 이동인지에 따라 순편익이 달라진다.

추천은 기존 시민참여 재배치 보상에 **고도 상승·거리·고지대 부족 압력**을 함께 적용하는 소규모 실험이다. 출퇴근 시간, 기본 접근성, 안전한 오르막 경로를 고려하고 해당 대여소의 반납 증가 및 배송 부담을 비교한다. 전기자전거는 언덕 부담을 낮추는 수단으로 같은 대체율 시나리오를 적용할 수 있지만, 이번 일반 따릉이 이력만으로 실제 전기자전거 효과를 추정할 수 없다. 충전·배터리 수송·제조 배출을 추가 측정한 뒤 순 탄소효과를 계산해야 한다. 고지대 주민에게 추가 체력 부담을 전가하지 않도록 전기 보조·대중교통 대안을 함께 검토한다.

## 그림 2장

두 그림 모두 **그림 내부 제목 없음**, PNG 220dpi와 벡터 PDF를 저장했다. 지도는 대여소 위치 자체를 그린 점지도이며 별도 배경지도 이용조건이 없다.

1. [대여소 고도·순유출률 지도](fig01_station_map.png) / [PDF](fig01_station_map.pdf). 2026년 1·4·6월 연결 표본 합계, 순유출률 색상은 ±40%에서 포화된다.
2. [거리·고도차별 내리막 비율](fig02_downhill_share.png) / [PDF](fig02_downhill_share.pdf). 100m 이상 OD, 고도차 절대값 10m 이상, 직선거리 구간 통제; 구간 통행 100건 미만은 표시하지 않았다. 50% 기준선을 표시했다.

## 선행 분석

2026-10-12 짧은 탐색. 국내 RISS·KCI·DBpia 검색, 서울시/서울연구원·공모전 사례, GitHub 및 해외 학술자료를 검색했다. 다음은 확인된 관련 자료이며 미발견이 부재를 의미하지 않는다.

| 출처 | 한 줄 요지 | 겹치는 정도 |
|---|---|---|
| [김병권·오태연, 강서구 따릉이 차별양상(KCI)](https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003358192) | 낮은 경사가 강서구의 높은 이용과 관련되고 언덕 지역 전기자전거 대안을 제시; KCI 초록 확인 | 부분: 경사·형평성·전기자전거, 반납 불균형/차량 탄소는 초록에서 확인되지 않음 |
| [김유신(2023), 따릉이 재배치 실시간 수요예측(DBpia)](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12629800) | 대여·반납·기상으로 안전재고와 필요 재배치 수량을 예측하고 관리 앱 시범 적용 | 부분: 불균형·재배치, 지형 연결 탄소 정량화와 다름 |
| [서울시립대 김희조·유다영(2020), 재배치 방안](https://uos-urbanscience.org/archives/uos_portfolio/빅데이터-분석을-통한-서울자전거-따릉이-재배치) | 이용 기록으로 관리구역과 차량 최적경로·재배치량 산정 | 부분: 재배치 최적화, 지형·탄소 연결은 공개 개요에서 미확인 |
| [서울시 시민참여 재배치(2024)](https://news.seoul.go.kr/traffic/archives/512211) | 과다거치 대여·과소거치 반납에 마일리지 지급, 사업실적 발표 | 부분: 이용자 보상은 기존 정책, 고도와 탄소를 연결하는 보상 설계가 추가 요소 |
| [2026 서울 빅데이터 경진대회 사례 ‘따릉이로(路)’](https://data.seoul.go.kr/dataVisual/gallery/galleryView.do?bbsCd=10005&ditcCd=WEB&seq=1f279f7c6a73747509c49990b4c4304f&ver=1) | 공개 사례 검색요약에서 등고선 기반 100m 경사 가중치와 이용 경로 서비스를 확인 | 부분: 지형 활용, 재배치 탄소 모형과 다른 목적; 수상 여부는 확인하지 않음 |
| [Kim·Pelechrinis·Lee(2020), Pittsburgh](https://people.cs.pitt.edu/~injungkim/data/Urbcomp20_20.pdf) | 대여소 쌍의 고도차·거리·계절을 분석하고 고도차의 통행 감소 및 전기자전거·재배치 활용을 논의 | 부분: 고도차 OD 검증이 매우 유사, 탄소 정량 모형은 별도 |
| [Goutam, Citi Bike 재배치 분석](https://goutam.org/projects/citi-bike-rebalances/) | 연속 자전거 기록으로 이동을 역추정해 고지대 보충과 Bike Angels 보상을 검토; 코드 링크 포함 | 부분(핵심 메커니즘 같음): 고도→상향 재배치·이용자 보상, 도시·탄소 추정은 다름 |
| [Geography over Income, Barcelona Bicing(2026)](https://www.mdpi.com/2071-1050/18/13/6529) | 고지대의 낮은 가용성, 전기자전거, 상향 반납 인센티브와 트럭 운영 배출을 연결 | 같음(문제설정·정책 방향): 도시와 정량 추정 방식은 다름. 공개 검색 색인/초록 요약을 확인했으며 본문은 403/429 접근 제한 |
| [Free-floating bike-sharing green relocation(2021)](https://academic.oup.com/tse/article/3/2/132/6211005) | 재배치와 온실가스 목적을 결합한 최적화 연구 | 부분: 재배치 탄소 최적화, 서울 고도 불균형 검증과 다름 |

**우리 차별점:** 2026년 서울 전역 3계절 약 942만 건에서 고도·순유출·OD 방향성을 함께 검증하고, 무료 DEM·공개 코드로 월별 최소 수송 부담 및 가정별 탄소·보상 대체량을 재현한다. 같은 자전거의 비대여기간 이동이 상향 우세한지도 교차 확인한다. 탄소 정량화와 오르막 인센티브 자체의 세계 최초 주장은 하지 않는다.

## 코드·산출물·다음 단계

- 코드: 현재 저장소. `acquire.py`, `probe.py`, `robustness.py`, `rebalance.py`, `infer_moves.py`, `write_report.py`, `report_figures.py`, `summary_figure.py`, `report_tables.py`, `reproduce.py`.
- 작업: 설정한 작업 폴더. 원본과 생성 결과는 Git에 넣지 않는다.
- 주요 집계: `station_total.csv`, `station_month.csv`, `regression.csv`, `robustness.csv`, `directions.csv`, `direction_distance_bins.csv`, `od_model.csv`, `rebalance_months.csv`, `carbon_sensitivity.csv`, `policy_scenarios.csv`, `inferred_moves.csv`, `data_inventory.csv`. 개별 자전거 이동기록은 내보내지 않았다.
- 다음 우선순위: 실제 차량제원/연료 또는 배송거리 자료를 확보해 탄소계수를 보정하고, 고지대 우선 대여소 10–20개에서 인센티브 참여율과 재고/품절 개선을 검증한다. 5장 본문에는 가설·지도·OD 방향성·운영 부담 시나리오·형평성 제안의 흐름으로 구성한다. GitHub 공개 링크 생성 및 제출 PDF 편집은 이번 워커 범위 밖이며 push하지 않았다.
'''
    (WORK/'PROBE.md').write_text(report,encoding='utf8')
    print('WROTE',WORK/'PROBE.md',len(report),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,default=RAW);p.add_argument('--work',type=Path,default=WORK)
    a=p.parse_args();RAW,WORK=a.raw,a.work;main()
