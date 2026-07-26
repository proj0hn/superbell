# SuperBell — 셀프계산대 상품 자동 카운팅 데모 앱
#
# 모델: YOLO11s 파인튜닝 (RPC 300장 · 17 상위 카테고리)
# 성능: 평가셋 90장 기준 cAcc 0.678 / MAE 0.467 (ZERO 제로샷 대비 MAE 8.4배 개선)
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image
from ultralytics import YOLO

# 데모용 가정 단가 (원) — 실서비스에서는 POS 상품 마스터와 연동
PRICES = {
    "puffed_food": 1800, "dried_fruit": 2500, "dried_food": 3000,
    "instant_drink": 2000, "instant_noodles": 1200, "dessert": 2200,
    "drink": 1500, "alcohol": 4000, "milk": 2500, "canned_food": 2800,
    "chocolate": 2000, "gum": 1000, "candy": 1200, "seasoner": 3500,
    "personal_hygiene": 4500, "tissue": 3000, "stationery": 1200,
}

PERF_TABLE = """**모델 성능** (평가셋 90장 · 학습 미사용)

| | ZERO 제로샷 | SuperBell |
|---|---|---|
| cAcc↑ | 0.178 | **0.678** |
| MAE↓ | 3.944 | **0.467** |
| RMSE↓ | 5.176 | **0.943** |

밀집(hard) 구간 MAE 6.357 → **0.429**
"""

st.set_page_config(page_title="SuperBell", page_icon="🔔", layout="wide")


@st.cache_resource
def load_model():
    return YOLO("weights/superbell_final.pt")


model = load_model()
NAMES = model.names

st.title("🔔 SuperBell — 셀프계산대 상품 자동 카운팅")
st.caption("트레이 사진 한 장으로 상품 개수와 종류를 자동 집계합니다. "
           "밀집·겹침 구간까지 세는 것이 목표입니다.")

# 사이드바
conf = st.sidebar.slider("신뢰도(confidence) 임계값", 0.10, 0.90, 0.50, 0.05)
st.sidebar.caption("기본값 0.50 — 평가셋에서 개수 오차(MAE)가 최소였던 값. "
                   "낮추면 많이 잡되 오탐↑, 높이면 놓침↑.")
st.sidebar.markdown("---")
st.sidebar.markdown(PERF_TABLE)
st.sidebar.markdown("---")
st.sidebar.caption("데이터: RPC (CC BY-NC-SA 4.0) · 플랫폼: Superb AI Suite")

# 입력
img = None
up = st.file_uploader("트레이 이미지를 올려주세요", type=["jpg", "jpeg", "png"])
if up:
    img = Image.open(up).convert("RGB")

samples = sorted(Path("samples").glob("*.jpg")) if Path("samples").exists() else []
if samples:
    st.write("**또는 샘플로 바로 보기** (파일명의 숫자 = 정답 개수)")
    for col, sp in zip(st.columns(len(samples)), samples):
        if col.button(sp.stem, use_container_width=True):
            img = Image.open(sp).convert("RGB")

if img is None:
    st.info("이미지를 업로드하거나 위의 샘플 버튼을 눌러주세요.")
    st.stop()

# 추론
t0 = time.time()
res = model.predict(img, conf=conf, imgsz=640, verbose=False)[0]
elapsed = time.time() - t0

col1, col2 = st.columns(2)
col1.image(img, caption="입력 이미지", use_container_width=True)
col2.image(res.plot()[:, :, ::-1], caption="탐지 결과", use_container_width=True)

n = len(res.boxes)
if n == 0:
    st.warning("상품을 찾지 못했습니다. 임계값을 낮추거나 트레이 전체가 나오게 다시 촬영해 주세요.")
    st.stop()

# 집계
counts = Counter(NAMES[int(c)] for c in res.boxes.cls)
df = pd.DataFrame([
    {"카테고리": k, "수량": v, "단가(원)": PRICES.get(k, 0), "금액(원)": v * PRICES.get(k, 0)}
    for k, v in counts.most_common()
])
total = int(df["금액(원)"].sum())
avg_conf = float(res.boxes.conf.mean())

m1, m2, m3, m4 = st.columns(4)
m1.metric("총 상품 개수", f"{n}개")
m2.metric("카테고리 수", f"{len(df)}종")
m3.metric("예상 결제 금액", f"{total:,}원")
m4.metric("평균 신뢰도", f"{avg_conf:.2f}")
st.caption(f"추론 {elapsed:.2f}초 · 임계값 {conf:.2f}")

st.subheader("🧾 카테고리별 집계")
left, right = st.columns([3, 2])
left.dataframe(df, use_container_width=True, hide_index=True)
right.bar_chart(df.set_index("카테고리")["수량"])

st.caption("※ 단가는 **데모용 가정값**입니다. "
           "실서비스에서는 POS 상품 마스터와 연동해 실제 판매가로 대체됩니다.")
