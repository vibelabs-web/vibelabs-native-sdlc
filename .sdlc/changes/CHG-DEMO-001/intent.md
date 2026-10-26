---
change_id: CHG-DEMO-001
revision: 0.1.0
status: draft
author_role: originator
source_refs: [demo-conversation]
approval_ref: null
---
# Intent: 행사 신청 및 대기자 자동 관리

## Problem
운영자가 행사 정원 초과와 취소자 발생 시 참가자/대기자를 수동으로 조정해야 한다.

## Proposed outcome
정원 30명까지 참가자로 확정하며, 그 이후 신청은 순서대로 대기 처리한다. 참가자 취소 시 가장 먼저 대기한 신청자를 승격한다.

## Affected users and systems
행사 신청자, 행사 운영자, 행사 신청 관리 시스템.

## Constraints
확정된 정원은 30명을 초과해서는 안 된다. 선착순 대기 순서를 유지한다.

## Success signals
정원 초과 없음. 정상 신청/대기 상태 구분. 취소 후 선착순 승격.

## Open questions
- 중복 신청 차단 여부: 미결정 (차단 질문)
- 알림 채널: 미결정 (MVP에서 별도 기능 요구 제외 여부 확인)

## Source and review
- 확정 사항: 대화 중 예시 시나리오로 제시한 30명, 대기, 취소 자동 승격을 데모 요구로 사용.
- 검토/승인: **없음**. 실서비스 사용 전 사용자 확인 필수.
