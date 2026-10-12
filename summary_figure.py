"""Report figure 5. Adapted from report/figs12/summary_figure.py (2026-10-12)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from settings import WORK, FONT
import argparse
import json
NAVY, TEAL, ORANGE, GRAY, LIGHT = "#183B56", "#078C8C", "#EA8337", "#647887", "#E4ECEF"

plt.rcParams.update({
    "font.family": FONT, "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "text.color": NAVY, "axes.labelcolor": NAVY, "xtick.color": NAVY, "ytick.color": NAVY, "axes.edgecolor": NAVY,
    "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": .6,
    "savefig.facecolor": "white", "figure.facecolor": "white",
})

from PIL import Image

def main(work=WORK, out=None):
    SRC = OUT = out or work/'report'/'figs'
    m=json.loads((work/'metrics.json').read_text(encoding='utf8'))
    beta=next(x['beta'] for x in m['station_models'] if x['model']=='net_ratio_joint' and x['term']=='elev10')
    f3 = pd.read_csv(SRC / "F3_고도구간_평균과_CI.csv", encoding="utf-8-sig")
    f2 = pd.read_csv(SRC / "F2_핵심수치.csv", encoding="utf-8-sig").sort_values("threshold_m")
    f4 = pd.read_csv(SRC / "F4_시나리오_핵심수치.csv", encoding="utf-8-sig")
    f4 = f4[f4.uphill10_flow_shift_fraction.isin([0, .25, .5])]

    fig, (a, b, c) = plt.subplots(1, 3, figsize=(4.8, 2.35), gridspec_kw={"width_ratios": [1.25, 1, 1], "wspace": .7})
    fig.subplots_adjust(left=.09, right=.995, bottom=.2, top=.97)

    # 가: 고도 구간별 평균 순유출률(대여소 10곳 이상 구간은 채운 점)
    x = f3.bin_lower_m + 5
    a.axhline(0, color=GRAY, lw=.7, zorder=1)
    a.plot(x, f3.mean_pct, color=TEAL, lw=1.2, alpha=.6, zorder=2)
    big = f3.n_stations >= 10
    a.scatter(x[big], f3.mean_pct[big], s=14, color=TEAL, zorder=3)
    a.scatter(x[~big], f3.mean_pct[~big], s=14, facecolor="white", edgecolor=ORANGE, lw=1, zorder=3)
    a.set(xlabel="대여소 고도 (m)", ylabel="평균 순유출률 (%)", ylim=(-10, 78), xlim=(-8, 122), xticks=[0, 30, 60, 90])
    a.grid(axis="y", color=LIGHT, lw=.5); a.set_axisbelow(True)
    a.text(0, 76, f"고도 10m당\n+{beta*100:.2f}%p", fontsize=8, fontweight="bold", va="top")

    # 나: 고도차 초과 구간별 내리막/오르막 통행 비
    bars = b.bar(range(3), f2.down_up, width=.6, color=[NAVY, TEAL, ORANGE], zorder=3)
    b.axhline(1, color=GRAY, lw=.8, ls=(0, (4, 3)), zorder=2)
    for bar, v in zip(bars, f2.down_up):
        b.text(bar.get_x() + bar.get_width() / 2, v + .04, f"{v:.2f}배", ha="center", va="bottom", fontsize=8, fontweight="bold", color=bar.get_facecolor())
    b.set(xticks=range(3), xticklabels=[f"{t}m" for t in f2.threshold_m], xlabel="출발·도착 고도차 초과", ylabel="내리막 / 오르막 (배)", ylim=(0, 2.15), xlim=(-.7, 2.6))
    b.grid(axis="y", color=LIGHT, lw=.5); b.set_axisbelow(True)

    # 다: 오르막 보충 대체율별 재배치 탄소
    bars = c.bar(range(3), f4.tonnes_co2e, width=.6, color=[NAVY, TEAL, ORANGE], zorder=3)
    for bar, v in zip(bars, f4.tonnes_co2e):
        c.text(bar.get_x() + bar.get_width() / 2, v + .25, f"{v:.2f}t", ha="center", va="bottom", fontsize=8, fontweight="bold", color=bar.get_facecolor())
    c.set(xticks=range(3), xticklabels=["0%", "25%", "50%"], xlabel="오르막 보충 대체율", ylabel="tCO2e / 3개월", ylim=(0, 17), xlim=(-.8, 2.6))
    c.grid(axis="y", color=LIGHT, lw=.5); c.set_axisbelow(True)

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "F5_분석결과_요약.png", dpi=300, bbox_inches="tight", pad_inches=.03)
    plt.close(fig)
    with Image.open(OUT / "F5_분석결과_요약.png") as im:
        assert abs(im.info['dpi'][0]-300)<.1
        item={'file':'F5_분석결과_요약.png','pixels':list(im.size),'dpi':300,
              'physical_width_cm':im.width/300*2.54,'figsize_width_in':4.8}
    manifest=OUT/'figure_manifest.json'
    items=json.loads(manifest.read_text(encoding='utf8'))
    items=[x for x in items if x['file']!=item['file']]+[item]
    manifest.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
    notes=OUT/'README.md'
    text=notes.read_text(encoding='utf8').split('\n## F5 분석결과 요약')[0]
    text+="\n## F5 분석결과 요약(보고서 그림 5)\n\n[PNG](F5_분석결과_요약.png). 고도별 순유출률·내리막 우세·탄소 시나리오를 한 장에 묶었다. 수치는 F2·F3·F4와 동일하며 원자료 구간 평균과 통제 후 고도 계수는 다른 통계다. 캡션: ‘고도가 높은 대여소의 순유출과 내리막 통행 우세는 상향 보충 부담으로 이어진다. 탄소는 공개 자료 기반 조건부 모형 추정이다.’ 출처: 서울시·AWS/Mapzen·UK DESNZ.\n"
    notes.write_text(text,encoding='utf8')
    print('SAVED', item, flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=WORK);p.add_argument('--out',type=Path)
    a=p.parse_args();main(a.work,a.out)
