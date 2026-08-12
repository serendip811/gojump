# 아파트 고점 지수 iOS Prototype

서울 주택 시장의 여섯 가지 과열 신호를 보여주는 SwiftUI 앱과 WidgetKit 위젯 프로토타입입니다. 앱은 GitHub Pages에 배포된 최신 시장 스냅샷을 읽고, 연결할 수 없으면 마지막 저장 데이터 또는 내장 샘플을 표시합니다.

## 실행

```sh
xcodegen generate
open GoJump.xcodeproj
```

Xcode에서 `GoJump` 스킴과 iPhone 시뮬레이터를 선택해 실행합니다. 실제 기기에서 App Group을 사용하려면 Apple Developer 계정에 맞는 Team과 App Group 식별자로 변경해야 합니다.

앱의 기본 데이터 주소는 아래 GitHub Pages 정적 JSON입니다.

```text
https://serendip811.github.io/gojump/api/v1/markets/seoul/snapshot.json
```

로컬 백엔드를 시험할 때는 `project.yml`의 `GOJUMP_SNAPSHOT_URL`을 `http://127.0.0.1:8080/v1/markets/seoul/snapshot`으로 임시 변경하고 다음 명령으로 fixture 서버를 실행합니다.

```sh
python3 -m backend.server --port 8080
```

국토부 실거래가 키를 사용한 실행법은 [backend/README.md](backend/README.md)를 참고하세요. 데이터 주소를 변경했다면 `xcodegen generate`를 다시 실행합니다.

## GitHub Pages 정적 API

운영 앱은 별도 상시 서버 대신 GitHub Actions가 정기 생성한 JSON을 GitHub Pages에서 읽을 수 있습니다.

1. 저장소 `Settings > Secrets and variables > Actions`에 아래 Repository secrets를 등록합니다.
   - `DATA_GO_KR_SERVICE_KEY`
   - `ECOS_API_KEY`
   - `HOUSTAT_API_KEY`
2. `Settings > Pages > Build and deployment`의 Source를 `GitHub Actions`로 선택합니다.
3. `Publish static market API` workflow를 처음 한 번 수동 실행합니다.
4. 배포된 JSON 주소가 다음과 같이 응답하는지 확인합니다.

```text
https://serendip811.github.io/gojump/api/v1/markets/seoul/snapshot.json
```

워크플로는 매일 서울 시간 오전 6시 17분에 실행됩니다. 최초 실행은 최근 60개월 실거래를 SQLite에 채우므로 오래 걸릴 수 있으며 이후 실행은 Actions cache를 복원해 증분 갱신합니다. 생성 또는 검증이 실패하면 Pages 배포 단계가 실행되지 않아 직전 정상 JSON이 유지됩니다.

## 구조

- `GoJumpApp`: 온보딩, 홈, 지표 상세, 계산법, 설정
- `GoJumpWidget`: Small·Medium 위젯
- `Shared`: 앱과 위젯이 함께 사용하는 모델과 점수 계산
- `GoJumpTests`: 점수 단계와 가중치 계산 테스트
- `backend`: 국토부 실거래가 수집기와 GoJump 스냅샷 API
