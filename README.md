---
title: SuperBell
emoji: 🔔
colorFrom: blue
colorTo: green
sdk: streamlit
app_file: app.py
pinned: false
license: cc-by-nc-sa-4.0
---

# 🔔 SuperBell — 셀프계산대 상품 자동 카운팅

트레이 위 상품을 **사진 한 장으로 세고 분류하는** AI 웹앱입니다.

## 문제
무인 셀프계산대의 **미스캔·수량 오인식**은 손실과 대기시간을 유발합니다.
바코드가 가려지거나 여러 개를 한 번에 올리면 계산 오류가 나고, 사람이 재확인해야 합니다.
SuperBell은 트레이 전체를 한 번에 인식해 **스캔 누락을 교차검증**합니다.

## 성능 (평가셋 90장 · 학습 미사용)

| 모델 | cAcc↑ | MAE↓ | RMSE↓ | 종류 |
|---|---|---|---|---|
| ZERO 제로샷 (baseline) | 0.178 | 3.944 | 5.176 | ✗ |
| **SuperBell (YOLO11s 파인튜닝)** | **0.678** | **0.467** | **0.943** | ✓ (17 카테고리) |

밀집(hard) 구간에서 이득이 가장 큽니다 — MAE **6.357 → 0.429**.

## 파이프라인 (Superb AI Suite 4단계)
데이터 선별 → 라벨링(GT import · Auto-Label + 검수) → 모델 학습 → 서비스 배포

## 데이터 · 라이선스
- **RPC** (Retail Product Checkout) — CC BY-NC-SA 4.0 · 학습·평가 300장 / 3,623박스
- **SKU110K** — 연구·비상업 공개 (밀집 라벨 seed)
- **AI Hub 상품 이미지** — AI Hub 이용약관 (국내 도메인 보강 2,000장)

본 데모는 **비상업 연구·교육 목적**이며, 화면의 단가는 데모용 가정값입니다.
