# keepalive 재활성화 가이드

> **지금 상태: 꺼져 있음(비활성).** 앱은 정상 동작 중이며, 발표 직전에만 켜면 됩니다.
> 최종 갱신 2026-08-17

---

## 0. 30초 요약

| 항목 | 내용 |
|---|---|
| 지금 파일 위치 | `.github/workflows/keepalive.yml.disabled` |
| 켜는 법 | 파일 이름을 **`keepalive.yml`** 로 바꾸고 커밋·push (내용 수정 불필요) |
| 끄는 법 | 다시 **`keepalive.yml.disabled`** 로 되돌리기 |
| 켜야 할 시점 | **발표 3~4일 전 (8/19 화)** — 그 전에는 불필요 |
| 안 켜도 되는가 | 됩니다. **발표 15분 전에 URL을 직접 한 번 여는 것**이 가장 확실한 대비책입니다 |

**앱 URL** — <https://superbell-auto-counter.streamlit.app>
**헬스체크** — <https://superbell-auto-counter.streamlit.app/healthz> → `{"status":"ok"}`

---

## 1. 원래 왜 실패했는가 (2026-08-08 ~ 08-17, "All jobs have failed")

실패한 런: <https://github.com/proj0hn/superbell/actions/runs/31857694663>

### 원인 — 앱이 아니라 **핑 스크립트**가 죽은 것

구버전 워크플로의 마지막 두 줄이 문제였습니다.

```bash
code=$(curl -sSL ... "$URL/healthz")   # ← 이건 200 OK. 정상.
curl -sSL -o /dev/null ... "$URL/"     # ← ★ 여기서 죽음
```

Streamlit Community Cloud의 **루트 경로(`/`)는 세션 쿠키를 심기 위해 303 리다이렉트를 반복**합니다.
`-L`(리다이렉트 따라가기)을 켜면 curl이 이 루프를 계속 따라가다가 **50회 한도**에 걸립니다.

```
curl: (47) Maximum (50) redirects followed
```

curl이 **exit code 47**로 종료 → GitHub Actions의 `run:` 블록은 `bash -e`로 실행되므로
**그 줄에서 잡 전체가 즉시 중단** → 화면에는 "All jobs have failed"로 표시.

### 검증 (2026-08-17 재현)

```
$ curl -sSL --max-time 60 ".../healthz"   → 200  {"status":"ok"}      ✅ 앱 정상
$ curl -sSL --max-time 60 ".../"          → curl: (47) Max redirects  ❌ 스크립트만 실패
```

> 💡 **결론: 앱은 한 번도 죽은 적이 없습니다.** 헬스체크는 매번 200이었고, keepalive의 목적(핑 보내기)도
> 실제로는 달성되고 있었습니다. 빨간 X 표시만 났던 것입니다.
> 그래서 이 기능을 꺼도 **잃는 것이 없습니다.**

### 고친 내용 (`.disabled` 파일에 이미 반영됨)

| 구버전 | 신버전 | 이유 |
|---|---|---|
| `curl -sSL "$URL/"` | `curl -sS --max-redirs 3 "$URL/" \|\| true` | `-L` 제거 + 실패 무시. 루트의 303은 **정상 응답**이므로 성공 판정에서 제외 |
| (없음) | `set -uo pipefail` (`-e` 제외) | 중간 줄이 실패해도 잡이 죽지 않게. 판정은 마지막 `test` 한 줄로만 |
| `curl -sSL "$URL/healthz"` | `curl -sS ... \|\| echo "000"` | 네트워크 순단 시 빈 값 대신 `000`이 들어가 판정이 명확해짐 |
| (없음) | `concurrency` · `timeout-minutes: 5` | 러너 지연 시 중복 실행 방지 · 매달림 방지 |

---

## 2. 켜는 법 (발표 3~4일 전 · 소요 2분)

### 방법 A — GitHub 웹에서 (권장, 클릭만)

1. <https://github.com/proj0hn/superbell> 접속 → `.github` → `workflows` 폴더로 이동
2. `keepalive.yml.disabled` 파일 클릭
3. 우측 상단 **연필 아이콘(Edit this file)** 클릭
4. 화면 맨 위 **파일명 입력칸**의 `keepalive.yml.disabled` 를 → **`keepalive.yml`** 로 수정
   (뒤의 `.disabled` 7글자만 지우면 됩니다)
5. 우측 상단 **Commit changes...** → **Commit changes** 클릭

### 방법 B — 로컬에서 (git)

```bash
cd "C:\Users\yohan\Documents\Competition\[BDAI] Superb AI 밀집 상품 분석\app"
git mv .github/workflows/keepalive.yml.disabled .github/workflows/keepalive.yml
git commit -m "chore: keepalive 재활성화 (발표 대비)"
git push
```

### 켠 직후 반드시 할 것 — **수동으로 한 번 돌려서 초록불 확인**

스케줄(cron)은 최대 6시간 뒤에나 돌기 때문에, 켜자마자 손으로 한 번 실행해 확인합니다.

1. 저장소 상단 **Actions** 탭 클릭
2. 왼쪽 목록에서 **keepalive** 선택
3. 우측 **Run workflow ▾** → 브랜치 `main` 확인 → **Run workflow** 버튼
4. 20~30초 뒤 새로고침 → 실행 항목 클릭 → **초록 체크(✅)** 확인
5. 로그를 열면 아래처럼 나와야 정상입니다:

```
healthz: 200 / {"status":"ok"}
root: 303 (303이면 정상)
```

> ⚠️ `Run workflow` 버튼이 안 보이면, 아직 `keepalive.yml`(확장자 `.yml`)로 이름이 안 바뀐 것입니다.
> GitHub는 `.github/workflows/` 안의 `.yml` / `.yaml` 파일만 워크플로로 인식합니다.

---

## 3. 끄는 법

발표가 끝나면 되돌립니다 (Actions 무료 사용량 절약).

- **웹**: 위 방법 A와 동일하게, 파일명을 다시 `keepalive.yml.disabled` 로 수정 후 커밋
- **로컬**: `git mv .github/workflows/keepalive.yml .github/workflows/keepalive.yml.disabled && git commit -m "chore: keepalive 비활성화" && git push`
- **임시로만 멈추기**: Actions 탭 → keepalive → 우측 `···` → **Disable workflow**
  (파일은 그대로 두고 스케줄만 정지. 다시 켤 때 **Enable workflow**)

---

## 4. ⭐ 발표 당일 체크리스트 (keepalive보다 이쪽이 훨씬 중요)

무료 Streamlit 앱은 **장시간 미사용 시 대기(sleep) 상태**로 들어가고, 깨어나는 데 **10~30초**가 걸립니다.
keepalive는 이 확률을 낮출 뿐이며, **100% 보장은 발표 직전 수동 접속뿐입니다.**

| 시점 | 할 일 |
|---|---|
| **발표 전날 (8/21)** | URL 접속 → 모드①·② 샘플 각 1회 실행해 정상 확인 |
| **발표 30분 전** | URL 접속해 앱 깨우기 (첫 로딩이 느리면 20초 기다릴 것) |
| **발표 15분 전** | **시크릿 창**으로 다시 접속 — 로그인 없이 열리는지 확인 (심사위원 환경과 동일) |
| **발표 5분 전** | 발표에 쓸 탭을 **미리 열어 두고 그대로 유지** (탭을 닫으면 세션이 끊깁니다) |
| **발표 직전** | 모드① 샘플을 **한 번 미리 실행** — 모델이 메모리에 캐시되어 실연 때 즉시 응답합니다 |

> 💾 **메모리 1GB 주의:** 모드①·② 모델을 둘 다 로드하면 메모리가 늘어납니다.
> 데모 중 탭을 여러 번 오가지 말고 **모드① → 모드② 순서로 한 번씩만** 진행하세요.

### 앱이 안 뜰 때 (30초 내 복구)

1. 20초 기다린다 (기동 중일 수 있음) → 새로고침
2. 그래도 안 되면 화면 우측 하단 **`Manage app`** → **Reboot app** (재기동 1~2분)
3. **그동안 데모 영상으로 전환** — <https://youtu.be/4um42wJ8n08>
4. 최후: 로컬 실행 `python -m streamlit run app.py` (앱 폴더에서)

> 🔒 **3중 대비:** 배포 URL → 데모 영상 → 로컬 실행.
> 발표 노트북에 **영상 파일을 미리 다운로드**해 두면 네트워크가 끊겨도 데모가 죽지 않습니다.
