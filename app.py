# SuperBell — 매장·물류 현장 재고 정합성 자동 점검
#
# 모드① 입고 검수 대조 : superbell_intake.pt (YOLO11s · RPC 300장 · 17 상위 카테고리)
#                        cAcc 0.678 / MAE 0.467 (ZERO 제로샷 대비 MAE 8.4배 개선)
# 모드② 진열 결품 점검 : superbell_shelf.pt  (YOLO11s · 서울시 국내 진열대 898장 · 5 매대 카테고리)
#
# 설계 원칙: AI는 "센다"까지만 하고, 판단은 기준값(발주서·기준 진열량)과의 대조가 한다.
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from ultralytics import YOLO

# ──────────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────────
INTAKE_WEIGHTS = ["weights/superbell_intake.pt", "weights/superbell_final.pt"]
SHELF_WEIGHTS = ["weights/superbell_shelf.pt"]

# 모드② 매대 카테고리 한글 표기
SHELF_KO = {
    "snack": "과자", "sauce": "소스·장류", "processed": "즉석식품",
    "noodle": "라면", "can": "죽·캔",
}

# 모드② 잔여율 판정 기준 (기준 진열량 대비)
OK_RATIO, LOW_RATIO = 0.70, 0.30

# 모드별 기본 신뢰도 임계값 — 각 평가셋에서 개수 오차(MAE)가 최소였던 값
#   모드① RPC 90장   : 0.50   (cAcc 0.678 / MAE 0.467)
#   모드② 서울시 178장: 0.20   (cAcc 0.337 / MAE 1.893) — 매대는 작고 겹쳐 낮은 값이 유리
CONF_INTAKE, CONF_SHELF = 0.50, 0.20

INTAKE_PERF = """**모드① 성능** (RPC 평가셋 90장 · 학습 미사용)

| | ZERO 제로샷 | SuperBell |
|---|---|---|
| cAcc↑ | 0.178 | **0.678** |
| MAE↓ | 3.944 | **0.467** |
| RMSE↓ | 5.176 | **0.943** |

밀집(hard) 구간 MAE 6.357 → **0.429**
"""

st.set_page_config(page_title="SuperBell — 재고 정합성 자동 점검",
                   page_icon="🔔", layout="wide")


# ──────────────────────────────────────────────────────────────
# 모델 로딩 (경로별로 1회만)
# ──────────────────────────────────────────────────────────────
@st.cache_resource
def load_model(path: str):
    return YOLO(path)


def find_weights(candidates):
    for c in candidates:
        if Path(c).exists():
            return c
    return None


@st.cache_data
def load_shelf_metrics():
    p = Path("shelf_metrics.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def predict(model, img, conf):
    t0 = time.time()
    res = model.predict(img, conf=conf, imgsz=640, verbose=False)[0]
    return res, time.time() - t0


def pick_image(key: str, label: str, sample_dir: Path):
    """업로드 위젯 + 샘플 버튼. 고른 이미지를 세션에 담아 돌려준다."""
    up = st.file_uploader(label, type=["jpg", "jpeg", "png"], key=f"up_{key}")
    if up:
        st.session_state[f"img_{key}"] = Image.open(up).convert("RGB")

    samples = sorted(sample_dir.glob("*.jpg")) if sample_dir.exists() else []
    if samples:
        st.caption("또는 샘플로 바로 보기 — 파일명의 숫자가 정답 개수입니다")
        for col, sp in zip(st.columns(len(samples)), samples):
            if col.button(sp.stem, key=f"btn_{key}_{sp.stem}", use_container_width=True):
                st.session_state[f"img_{key}"] = Image.open(sp).convert("RGB")
    return st.session_state.get(f"img_{key}")


def show_detection(img, res, elapsed, conf):
    c1, c2 = st.columns(2)
    c1.image(img, caption="입력 이미지", use_container_width=True)
    c2.image(res.plot()[:, :, ::-1], caption="탐지 결과", use_container_width=True)
    st.caption(f"추론 {elapsed:.2f}초 · 신뢰도 임계값 {conf:.2f}")


def counts_of(res, names):
    return Counter(names[int(c)] for c in res.boxes.cls)


def md_table(df: pd.DataFrame) -> str:
    """DataFrame → 마크다운 표. (tabulate 의존을 피하려고 직접 만듭니다)"""
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |",
             "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 헤더
# ──────────────────────────────────────────────────────────────
st.title("🔔 SuperBell — 매장·물류 현장 재고 정합성 자동 점검")
st.caption("사진 한 장으로 밀집된 상품을 세어 **장부와 실물의 차이**를 잡아냅니다. "
           "재고 오차가 실제로 발생하는 두 지점 — 입고 검수와 진열 결품 — 을 하나의 계수 모델로 자동화합니다.")

with st.expander("이 앱이 푸는 문제 (30초 요약)", expanded=False):
    st.markdown(
        "유통 현장의 재고는 **장부와 실물이 상시 어긋납니다.** 어긋남은 두 지점에서 만들어집니다.\n\n"
        "**① 입고 검수** — 점포·물류센터는 납품 상자를 열어 품목별 수량을 **손으로 셉니다.** "
        "피크 시간과 겹치면 눈대중으로 끝나고, 오배송·수량 부족이 그대로 '정상 입고'로 장부에 올라갑니다. "
        "**이 순간부터 재고 데이터 자체가 틀립니다.**\n\n"
        "**② 진열 결품** — 장부엔 재고가 있는데 매대는 비어 있는 상태(phantom inventory)를 "
        "직원이 수천 SKU의 매대를 **눈으로 훑어** 찾습니다. 발견이 늦을수록 판매 기회가 사라집니다. "
        "진열 결품만으로 유통사 연매출의 약 **8%** 가 손실됩니다.\n\n"
        "두 작업은 결국 **\"밀집돼 놓인 상품을 사람이 눈으로 센다\"** 는 동일 작업입니다. "
        "그래서 하나의 계수 모델로 두 지점을 동시에 자동화합니다."
    )

# ──────────────────────────────────────────────────────────────
# 사이드바
# ──────────────────────────────────────────────────────────────
st.sidebar.header("성능")
st.sidebar.caption("신뢰도(confidence) 임계값은 **각 모드 탭 안에** 있습니다 — "
                   "모드마다 개수 오차가 최소인 값이 다르기 때문입니다.")
st.sidebar.markdown("---")
st.sidebar.markdown(INTAKE_PERF)

_sm = load_shelf_metrics()
if _sm and _sm.get("best"):
    b = _sm["best"]
    st.sidebar.markdown(
        f"""**모드② 성능** (서울시 val {_sm.get('val_images', '?')}장)

| cAcc↑ | MAE↓ | RMSE↓ |
|---|---|---|
| **{b['cAcc']}** | **{b['MAE']}** | **{b['RMSE']}** |

최적 conf {b['conf']}
"""
    )
st.sidebar.markdown("---")
st.sidebar.caption("데이터: RPC (CC BY-NC-SA 4.0) · 서울시 상품 표지 이미지(공공데이터) · "
                   "AI Hub 상품 이미지 · 플랫폼: Superb AI Suite")

tab1, tab2 = st.tabs(["📦 모드① 입고 검수 대조", "🧺 모드② 진열 결품 점검"])


# ══════════════════════════════════════════════════════════════
# 모드 ① 입고 검수 대조
# ══════════════════════════════════════════════════════════════
with tab1:
    st.subheader("납품 검수 — 발주 수량과 실물을 자동 대조")
    st.markdown("검수대에 펼친 상품을 찍으면 카테고리별 수량을 세고, **발주 수량과 비교해 과부족을 표시**합니다. "
                "지금은 사람이 손으로 세어 발주서와 맞춰 보는 작업입니다.")

    wpath = find_weights(INTAKE_WEIGHTS)
    if wpath is None:
        st.error(f"모델 파일을 찾을 수 없습니다: {INTAKE_WEIGHTS}")
        st.stop()

    model1 = load_model(wpath)
    names1 = model1.names

    conf = st.slider("신뢰도(confidence) 임계값", 0.10, 0.90, CONF_INTAKE, 0.05,
                     key="conf_intake",
                     help="평가셋에서 개수 오차(MAE)가 최소였던 값이 기본값입니다. "
                          "낮추면 많이 잡되 오탐↑, 높이면 놓침↑.")
    img1 = pick_image("intake", "검수대 사진을 올려주세요", Path("samples/intake"))
    if img1 is None:
        st.info("이미지를 업로드하거나 위의 샘플 버튼을 눌러주세요.")
    else:
        res1, el1 = predict(model1, img1, conf)
        show_detection(img1, res1, el1, conf)

        n1 = len(res1.boxes)
        if n1 == 0:
            st.warning("상품을 찾지 못했습니다. 임계값을 낮추거나 검수대 전체가 나오게 다시 촬영해 주세요.")
        else:
            counts1 = counts_of(res1, names1)
            avg_conf = float(res1.boxes.conf.mean())

            st.markdown("#### 1) 발주 수량 입력")
            st.caption("실서비스에서는 이 값을 **발주서(WMS)** 에서 자동으로 읽어 옵니다. "
                       "데모에서는 직접 입력해 대조 결과를 확인합니다.")
            base = pd.DataFrame(
                [{"카테고리": k, "발주 수량": v} for k, v in counts1.most_common()]
            )
            edited = st.data_editor(
                base, key="po_editor", hide_index=True, use_container_width=True,
                column_config={
                    "카테고리": st.column_config.TextColumn(disabled=True),
                    "발주 수량": st.column_config.NumberColumn(min_value=0, step=1),
                },
            )

            st.markdown("#### 2) 검수 대조 결과")
            rows = []
            for _, r in edited.iterrows():
                cat = r["카테고리"]
                po = int(r["발주 수량"])
                actual = int(counts1.get(cat, 0))
                diff = actual - po
                status = "일치" if diff == 0 else ("부족" if diff < 0 else "초과")
                mark = {"일치": "✅ 일치", "부족": "🔴 부족", "초과": "🟠 초과"}[status]
                rows.append({"카테고리": cat, "발주 수량": po, "실물(AI 계수)": actual,
                             "차이": diff, "판정": mark})
            df1 = pd.DataFrame(rows)

            n_mismatch = int((df1["차이"] != 0).sum())
            total_diff = int(df1["차이"].abs().sum())

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("총 상품 개수", f"{n1}개")
            m2.metric("카테고리 수", f"{len(df1)}종")
            m3.metric("불일치 카테고리", f"{n_mismatch}종",
                      delta=None if n_mismatch == 0 else f"-{n_mismatch}", delta_color="inverse")
            m4.metric("평균 신뢰도", f"{avg_conf:.2f}")

            if n_mismatch == 0:
                st.success("✅ **검수 합격** — 발주 수량과 실물이 모두 일치합니다.")
            else:
                st.error(f"🔔 **검수 불합격** — {n_mismatch}개 카테고리에서 총 {total_diff}개 차이가 있습니다. "
                         "아래 표의 '부족/초과' 항목을 확인하세요.")

            left, right = st.columns([3, 2])
            left.dataframe(df1, use_container_width=True, hide_index=True)
            right.bar_chart(df1.set_index("카테고리")["실물(AI 계수)"])

            report = ["# 입고 검수 리포트 (SuperBell)", "",
                      f"- 총 상품 개수: {n1}개 / 카테고리 {len(df1)}종",
                      f"- 판정: {'합격' if n_mismatch == 0 else '불합격'} "
                      f"(불일치 {n_mismatch}종 · 총 차이 {total_diff}개)",
                      f"- 신뢰도 임계값 {conf:.2f} · 평균 신뢰도 {avg_conf:.2f}", "",
                      md_table(df1)]
            st.download_button("📄 검수 리포트 내려받기 (.md)",
                               "\n".join(report), file_name="검수리포트.md",
                               mime="text/markdown")

            st.caption("※ cAcc(개수 완전 일치 비율)가 곧 **검수 자동화 성공률**입니다 — "
                       "검수는 '몇 개쯤'이 아니라 '발주 수량과 정확히 같은가'를 판정하는 작업이기 때문입니다.")


# ══════════════════════════════════════════════════════════════
# 모드 ② 진열 결품 점검
# ══════════════════════════════════════════════════════════════
with tab2:
    st.subheader("진열 점검 — 매대 잔여량과 결품 경보")
    st.markdown("매대를 찍으면 남은 상품 수를 세고, **기준 진열량과 비교해 결품·부족을 경보**합니다. "
                "지금은 직원이 매대를 순회하며 눈으로 확인하는 작업입니다.")

    wpath2 = find_weights(SHELF_WEIGHTS)
    if wpath2 is None:
        st.info(
            "🔧 **모드② 모델은 아직 준비 중입니다.**\n\n"
            "국내 진열대 데이터(서울시 상품 표지 이미지 898장 · 5개 매대 카테고리)로 학습 중이며, "
            "`weights/superbell_shelf.pt` 가 배치되면 이 탭이 자동으로 활성화됩니다.\n\n"
            "그동안 **모드①(입고 검수 대조)** 은 완전히 동작합니다."
        )
    else:
        model2 = load_model(wpath2)
        names2 = model2.names

        conf = st.slider("신뢰도(confidence) 임계값", 0.10, 0.90, CONF_SHELF, 0.05,
                         key="conf_shelf",
                         help="매대는 상품이 작고 겹쳐 보여 검수대보다 낮은 임계값에서 "
                              "개수 오차가 최소가 됩니다.")

        st.markdown("#### 1) 기준 진열량 정하기")
        mode = st.radio(
            "기준을 어떻게 정할까요?",
            ["기준 사진으로 자동 계산 (권장)", "숫자로 직접 입력"],
            horizontal=True, key="shelf_base_mode",
        )
        st.caption("실서비스에서는 이 값이 **플래노그램 기준 진열량**으로 대체됩니다. "
                   "데모에서는 매대가 가득 찬 사진 또는 직접 입력값을 기준으로 씁니다.")

        base_counts = None
        if mode.startswith("기준 사진"):
            imgb = pick_image("shelf_base", "기준(가득 찬) 매대 사진", Path("samples/shelf"))
            if imgb is not None:
                resb, _ = predict(model2, imgb, conf)
                base_counts = counts_of(resb, names2)
                c1, c2 = st.columns([1, 2])
                c1.image(resb.plot()[:, :, ::-1], caption="기준 상태", use_container_width=True)
                c2.write({SHELF_KO.get(k, k): v for k, v in base_counts.items()})

        st.markdown("#### 2) 현재 매대 점검")
        img2 = pick_image("shelf_now", "지금 매대 사진을 올려주세요", Path("samples/shelf"))

        if img2 is None:
            st.info("점검할 매대 사진을 올리거나 샘플 버튼을 눌러주세요.")
        else:
            res2, el2 = predict(model2, img2, conf)
            show_detection(img2, res2, el2, conf)
            now_counts = counts_of(res2, names2)

            cats = sorted(set(list(now_counts.keys()) + list((base_counts or {}).keys())))
            if not cats:
                st.warning("상품을 찾지 못했습니다. 임계값을 낮추거나 매대 전체가 나오게 다시 촬영해 주세요.")
            else:
                if base_counts is None:
                    manual = pd.DataFrame([{"매대 카테고리": SHELF_KO.get(c, c),
                                            "기준 진열량": int(now_counts.get(c, 0))} for c in cats])
                    manual = st.data_editor(
                        manual, key="shelf_editor", hide_index=True, use_container_width=True,
                        column_config={
                            "매대 카테고리": st.column_config.TextColumn(disabled=True),
                            "기준 진열량": st.column_config.NumberColumn(min_value=0, step=1),
                        },
                    )
                    ko2en = {SHELF_KO.get(c, c): c for c in cats}
                    base_counts = Counter({ko2en[r["매대 카테고리"]]: int(r["기준 진열량"])
                                           for _, r in manual.iterrows()})

                rows = []
                for c in cats:
                    ref = int(base_counts.get(c, 0))
                    now = int(now_counts.get(c, 0))
                    ratio = (now / ref) if ref > 0 else 1.0
                    if ref == 0:
                        state = "기준없음"
                    elif ratio >= OK_RATIO:
                        state = "정상"
                    elif ratio >= LOW_RATIO:
                        state = "부족"
                    else:
                        state = "결품 위험"
                    mark = {"정상": "✅ 정상", "부족": "🟠 부족",
                            "결품 위험": "🔴 결품 위험", "기준없음": "— 기준없음"}[state]
                    rows.append({"매대 카테고리": SHELF_KO.get(c, c), "기준 진열량": ref,
                                 "현재(AI 계수)": now, "부족 수량": max(0, ref - now),
                                 "잔여율": round(ratio, 2), "상태": mark})
                df2 = pd.DataFrame(rows).sort_values("잔여율")

                n_alert = int(df2["상태"].str.contains("부족|결품").sum())
                need = int(df2["부족 수량"].sum())
                worst = df2.iloc[0]

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("현재 진열 수량", f"{len(res2.boxes)}개")
                m2.metric("점검 카테고리", f"{len(df2)}종")
                m3.metric("보충 필요 수량", f"{need}개")
                m4.metric("최저 잔여율", f"{worst['잔여율']:.0%}")

                if n_alert == 0:
                    st.success("✅ **정상** — 모든 매대가 기준 진열량의 70% 이상을 유지하고 있습니다.")
                else:
                    st.error(f"🔔 **보충 필요** — {n_alert}종에서 결품·부족이 감지됐습니다. "
                             f"가장 급한 곳: **{worst['매대 카테고리']}** (잔여율 {worst['잔여율']:.0%})")

                left, right = st.columns([3, 2])
                left.dataframe(df2, use_container_width=True, hide_index=True)
                right.bar_chart(df2.set_index("매대 카테고리")["잔여율"])
                st.caption(f"판정 기준 — 잔여율 {OK_RATIO:.0%} 이상 정상 · "
                           f"{LOW_RATIO:.0%}~{OK_RATIO:.0%} 부족 · {LOW_RATIO:.0%} 미만 결품 위험. "
                           "실서비스에서는 이 경보가 **보충 지시·자동 발주**로 연결됩니다.")

st.markdown("---")
st.caption("SuperBell · Superb AI × BDAI 해커톤 · 비상업 연구·교육 목적 데모 — "
           "밀집(dense)을 분할(partition)로, 분할을 정확한 계수(count)로, 계수를 차이 경보(bell)로.")
