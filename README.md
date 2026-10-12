# 언덕이 만드는 탄소: 따릉이 재배치의 역설

서울 따릉이의 고도·대여/반납 불균형을 분석하고, 공개 자료 기반 재배치 탄소와 오르막 반납 보상 시나리오를 재현합니다.

보고서 「언덕이 만드는 탄소: 따릉이 재배치의 역설」의 그림 1–5와 표 1–2를 생성하는 코드입니다. 차량 연료·GPS 실측 보정은 하지 않습니다. 원본 데이터, 개별 이용/자전거 기록, 생성 그림, 보고서 서식 및 제출자 개인정보는 이 저장소에 포함하지 않습니다.

## 설치와 경로

Python 3.12와 Git이 필요합니다. 원본 약 1.8GB 외에 환경·집계·최적화 작업 공간을 확보하세요. 설치와 계산은 로컬 디스크에서 합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux에서는 이후 명령의 실행기를 `.venv/bin/python`으로 바꿉니다. `requirements.lock.txt`는 실행 환경의 고정 버전이며 `requirements.txt`가 이를 참조합니다.

기본 입력은 `data/raw/`, 출력은 `outputs/`입니다. 다른 위치의 기존 자료를 쓸 때는 아래 환경변수에 해당 폴더를 지정하거나 각 명령의 `--raw`, `--work`를 사용합니다. 환경변수는 자동으로 `.env`에서 읽지 않습니다.

| 설정 | 기본값 | 용도 |
|---|---|---|
| `BIKE_RAW_DIR` | 저장소의 `data/raw/` | 원본 파일·취득 메타데이터 |
| `BIKE_WORK_DIR` | 저장소의 `outputs/` | 분석 집계·보고서 그림·표 |
| `BIKE_FONT` | `Malgun Gothic` | 한글 글꼴; 다른 OS에서는 설치된 한글 글꼴 이름으로 지정 |

예를 들어 기본 상대경로를 환경변수로 명시할 수 있습니다. 사용자의 로컬 경로는 코드에 기록하지 않습니다.

```powershell
$env:BIKE_RAW_DIR = Join-Path $PWD 'data/raw'
$env:BIKE_WORK_DIR = Join-Path $PWD 'outputs'
$env:BIKE_FONT = 'Malgun Gothic'
```

## 데이터 받기와 이용조건

모두 무료 공개 자료이며 API 키나 로그인이 필요하지 않습니다. `acquire.py`는 서울시 이력·대여소와 DEM을 받습니다. 재현 실행 중 DESNZ 계수와 OSM 경계가 없으면 추가로 받습니다. 이미 있는 원본은 보존하며 서울시 파일은 취득 메타데이터의 크기와 대조합니다.

| 자료 | 사용 시점·파일 | 공식 출처·이용조건 |
|---|---|---|
| 따릉이 대여·반납 이력 | 2026년 1·4·6월 전체; `trips_202601.csv`, `trips_202604.csv`, `trips_202606.csv` | [서울 열린데이터광장 OA-15182](https://data.seoul.go.kr/dataList/OA-15182/F/1/datasetView.do), 공공누리 제1유형(출처표시) |
| 대여소 마스터 | 주분석 2026-06; 좌표 점검 2025-12·06; `stations_YYYYMM.xlsx` 3개 | [서울 열린데이터광장 OA-13252](https://data.seoul.go.kr/dataList/OA-13252/F/1/datasetView.do), 공공누리 제1유형 |
| DEM | `N37E126.hgt.gz`, `N37E127.hgt.gz`; 약 30m 격자 | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/), [Mapzen/Tilezen 출처·원천별 이용조건](https://github.com/tilezen/joerd/blob/master/docs/attribution.md). Mapzen; Global GMTED2010 and SRTM terrain data courtesy of the U.S. Geological Survey. 격자 간격과 원천 품질은 다를 수 있음 |
| 차량 배출계수 | `ghg-conversion-factors-2025-full-set.xlsx`; Delivery vehicles!D30 | [UK DESNZ 2025 full set](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025), UK Open Government Licence v3.0 |
| 서울 행정경계 | `seoul_boundary_osm.geojson`; relation 2297418, 2026-10-12 스냅샷 | [OpenStreetMap](https://www.openstreetmap.org/relation/2297418), © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright). 그림 출처에도 표시 |
| 시민참여 재배치 제도 | 2024-05-03 게시 보도자료; 그림/수치 계산 입력은 아님 | [서울시 뉴스](https://news.seoul.go.kr/traffic/archives/512211), 출처 인용만 하며 원문 재배포 안 함 |

취득 URL·시점·라이선스·SHA256은 원본 폴더의 `metadata/`에 저장합니다. 표 생성 단계에서 실제 사용 원본의 SHA256도 출력합니다. 공식 파일 URL이 바뀌면 위 데이터 페이지에서 같은 기준시점 파일을 받아 정해진 이름으로 저장하세요. 서울시 파일을 수동으로 받았다면 크기·SHA256·출처·시점·라이선스가 있는 `metadata/파일명.json`을 함께 기록하세요. 추가로 받는 OSM 경계는 현행 스냅샷이므로 원본 해시가 달라지면 지도 윤곽도 달라질 수 있습니다.

## 재현 명령 순서

처음에는 원본을 내려받고, **비어 있는 작업 폴더**에서 전체 분석을 실행합니다.

```powershell
.\.venv\Scripts\python.exe acquire.py
.\.venv\Scripts\python.exe reproduce.py
```

`python reproduce.py --download` 한 명령으로 두 단계를 실행할 수도 있습니다. 원본이 이미 있는 외부 폴더를 사용할 때는 `--raw 입력폴더 --work 새작업폴더`를 전달합니다. 원본·대여소·분석 정의가 바뀌면 새 작업 폴더를 써야 하며, 이전 원본의 OD/연속 이동 캐시를 재사용하지 않습니다.

실행 순서는 아래와 같습니다. 모든 스크립트가 설정된 경로를 공유합니다.

```powershell
.\.venv\Scripts\python.exe probe.py
.\.venv\Scripts\python.exe robustness.py
.\.venv\Scripts\python.exe rebalance.py
.\.venv\Scripts\python.exe infer_moves.py
.\.venv\Scripts\python.exe write_report.py
.\.venv\Scripts\python.exe report_figures.py
.\.venv\Scripts\python.exe summary_figure.py
.\.venv\Scripts\python.exe report_tables.py
```

기존 집계에서 그림·표만 다시 만들려면 `python reproduce.py --figures-only`를 사용합니다. `report_tables.py`는 실제 계산값이 보고서 기준 수치와 일치하는지 검사하므로 다른 기간 자료에는 별도 기준 검토가 필요합니다. 한국어 글꼴이 없으면 그림 생성 전에 설치하거나 `BIKE_FONT`를 바꾸세요.

## 보고서 그림·표 대응

보고서의 12cm 폭판 스크립트를 이 저장소로 정리했습니다. 파일명의 F번호와 보고서 번호는 다음과 같습니다.

| 보고서 | 출력 파일(설정한 작업 폴더 기준) |
|---|---|
| 그림 1: 서울 지도 | `report/figs/F1_서울_고도와_순유출률.png` |
| 그림 2: 고도별 순유출률 | `report/figs/F3_고도구간별_평균_순유출률.png` |
| 그림 3: 내리막/오르막 비 | `report/figs/F2_고도차별_내리막_우세.png` |
| 그림 4: 탄소 시나리오 | `report/figs/F4_재배치_탄소_정책시나리오.png` |
| 그림 5: 요약 | `report/figs/F5_분석결과_요약.png` |
| 표 1: 활용 데이터 | `report/tables/table1_data_sources.csv` |
| 표 2: 월별 재배치 | `report/tables/table2_rebalance_report.csv` |

그림은 300dpi PNG, F1–F4는 PDF도 생성합니다. 캡션·출처·가정은 `report/figs/README.md`, 표는 `report/tables/README.md`, 반올림 전 수치는 `table2_rebalance_full_precision.csv`와 `report_numbers.json`에서 확인합니다. 검증 결과는 `report/tables/verification.json`, 실행 순서·소요시간은 `reproduction_run.json`에 저장합니다. 보고서 PDF/HWPX 자체와 공모전 신청서 생성은 공개 코드 범위에 포함하지 않습니다.

## 핵심 결과와 해석 범위

- 2026년 1·4·6월 9,761,201건 중 9,427,594건, 이용 대여소 2,773개를 분석했습니다.
- 순유출률은 `(대여−반납)/(대여+반납)`입니다. 자치구·월·이용량·거치 규모·DEM 경사를 통제한 고도 10m 상승은 순유출률 **+6.45%p**와 연결됩니다(대여소 군집 95% CI 5.81–7.08%p; 8,152개 대여소-월).
- 고도차 10·20·30m 초과 통행의 내리막/오르막 비는 **1.288·1.583·1.826배**입니다. 임계값 표본은 중첩됩니다. 같은 대여소 쌍과 거리 구간을 이용한 별도 검증도 수행합니다.
- 월별 재고 복원 최소비용 수송은 **414,293대·528,453 자전거-km**입니다. 10m 이상 오르막 보충은 239,247대입니다.
- 적재 20대·도로 우회 1.3·공차/경로 1.5, UK 디젤 밴 계수 **0.27878kgCO2e/차량-km**를 가정하면 3개월 운영 배출은 **14.36tCO2e**입니다. 오르막 보충 25%·50%를 시민 이동이 대체하면 **11.79·9.21t**으로 줄어드는 조건부 시나리오입니다.

순유출률은 재고 감소 압력이며 실제 빈 거치대 시간을 관측한 값이 아닙니다. 월별 최적 수송은 실제 트럭 경로·차량 대수·일중 재고를 재현하지 않습니다. 정책 참여율, 지형의 인과기여, 실차 배출, 따릉이 전체의 순 탄소효과를 입증한 결과로 해석하지 않습니다. 적재·도로·공차 가정의 27조합에서 기준 배출은 3.68–47.14t이며 통계적 신뢰구간이 아닙니다. 전기자전거 충전·제조·정비 및 자동차 대체 효과는 포함하지 않습니다.

## 공개 검사와 라이선스

```powershell
.\.venv\Scripts\python.exe audit_public.py
```

모든 Git 객체(도달 불가능 객체 포함), 전체 참조의 커밋, 공개 대상 작업 파일에서 비밀값 패턴·개인 절대경로·데이터/생성 파일·1MiB 초과 파일을 검사합니다. 검사기는 의심 값 자체를 출력하지 않습니다. 자동 검사는 모든 형태의 비밀값 부재를 보증하지 않으므로 공개 전 파일 목록도 확인합니다. 이번 정리·검증 기록은 [공개 전 검사 기록](docs/PUBLICATION_CHECK.md)에 있습니다.

코드는 [MIT License](LICENSE)로 공개합니다. 원본 데이터의 공공누리·Mapzen/원천 조건·OGL·ODbL은 각각 유지되며 코드의 MIT가 이들 데이터에 적용되지는 않습니다. 그림 재사용 시 README에 적힌 데이터 출처를 함께 표시하세요. 이 작업에서는 push하지 않습니다.
