---
layout: post
title: "Agent 개발 환경: Paseo, Tailscale 기반 개발 환경 구축"
subtitle: "결과는 GUI에서 읽고, 작업은 로컬과 minipc에 나눠 실행하기"
tags: [ai-agent, pi, paseo, tailscale, wsl]
comments: false
---

Paseo와 같은 Agent 오케스트레이션 도구가 필요했던 이유는 네 가지였다. **결과를 읽기 편한 인터페이스, 결과 확인을 위한 도구 이동 줄이기, 애플리케이션을 닫아도 작업 유지하기, 다른 서버의 리소스 활용하기**다.

## 어떤 점을 바꾸고 싶었는가

### 1. 가장 많이 하는 작업은 Agent의 결과를 읽는 일이었다

Agent를 사용하면서 내가 가장 많이 하는 일은 생성된 코드나 설계, 설명을 읽고 리뷰하는 것이었다. 그래서 출력의 가독성이 중요하다고 느꼈다. 같은 내용이라도 인터페이스에서 보기 어렵게 표시되면 눈에 잘 들어오지 않았고, 내용을 이해하는 데도 영향을 줬다.

긴 텍스트와 코드 블록을 터미널에서 읽는 대신, 문서와 코드를 구분해서 보여주는 GUI에서 검토하고 싶었다. 단순히 화면을 예쁘게 만드는 것보다, 가장 많은 시간을 쓰는 읽기와 리뷰 작업에 맞는 인터페이스가 필요하다고 생각했다.

### 2. 결과를 확인하기 위해 도구를 옮겨 다니고 싶지 않았다

결과물에 대한 이해를 돕기 위해서 이미지나 다이어그램을 생성하는 경우가 많았는데 TUI에서는 이미지나 Mermaid 같은 결과를 출력하는 것들을 지원하지 않았다.

Agent가 이미지를 생성하면 탐색기에서 파일을 찾아 열고, Mermaid 코드 기반의 다이어그램은 TUI로 출력할 수 있는 형태로 바꿔달라고 요청했다. 대화하다가 다른 앱으로 이동하고 다시 돌아오는 과정이 작업의 연속성을 끊는다고 느꼈다.

![Windows Terminal의 Pi TUI에서 다이어그램 파일을 생성했지만 이미지 대신 텍스트 출력만 보이는 화면]({{ '/assets/img/pi-agent-tui.png' | relative_url }})

*기존 TUI 환경에서는 다이어그램을 이미지 파일로 생성해도 대화 화면에서 바로 확인할 수 없었다.*

그래서 대화뿐 아니라 파일 확인과 편집, 결과 검토까지 같은 작업 공간에서 할 수 있는 도구를 원했다. Paseo는 대화 GUI에 파일 편집기와 Diff, 터미널 등을 함께 제공한다.

### 3. 화면을 닫는 것과 작업을 끝내는 것을 분리하고 싶었다

Paseo에서는 GUI 애플리케이션이 아니라 Daemon이 Agent 세션을 관리한다. 화면을 닫더라도 실행 호스트의 Daemon과 Agent가 살아 있으면 작업을 계속할 수 있다.

기존 환경과의 차이는 GUI 클라이언트와 실행 환경을 분리하고, 다른 디바이스에서도 그 세션에 접근할 수 있다는 것이다. 특히 minipc에서 실행한 작업은 노트북을 꺼도 영향을 받지 않는다.

### 4. 노트북뿐 아니라 다른 서버의 리소스도 활용하고 싶었다

집에는 상시 운영하는 Ubuntu minipc가 있었다. 집중해서 개발할 때는 노트북에서 세션을 열고 작업하고 오래 걸리는 작업은 minipc에 맡겨 가지고 있는 리소스를 함께 활용하고 싶었다.

Paseo는 여러 호스트에 Daemon을 실행하고 연결할 수 있다. GUI에서 실행 호스트를 선택하는 것뿐 아니라, Paseo CLI를 통해 메인 Agent가 다른 호스트의 서브 Agent에 작업을 요청하는 흐름으로도 확장할 수 있다. 로컬 세션 자체를 옮기는 것이 아니라, 원격 호스트에 별도 작업을 만들고 결과를 받는 방식이다.

## 왜 Paseo를 선택했는가

비교한 도구는 herdr와 Orca였다.

[herdr](https://github.com/herdrdev/herdr)는 터미널 세션 유지와 여러 머신의 Agent 상태 관리에 강점이 있다. 내가 검토한 herdr CLI는 인터페이스적인 강점도 없었고 이미 나는 tmux에 익숙해서 터미널 자체를 바꾸기는 원치 않았다.. 이번 목적은 터미널 관리 도구를 바꾸는 것보다 결과를 읽는 인터페이스를 바꾸는 데 있었기 때문에 선택하지 않았다.

[Orca](https://github.com/stablyai/orca)는 GUI, Worktree 기반 병렬 작업, Diff 리뷰와 Git 연동을 제공한다. Orca는 채팅 화면을 제공하는데 모든 Agent들에 대해서 제공이 되고 있진 않고 내가 사용하는 pi agent는 지원이 안되고 oh my pi까지만 되는 것 같아서 선택하지 않았다.

[Paseo](https://github.com/getpaseo/paseo)를 선택한 이유는 기존 Pi를 유지하면서 **각 호스트의 Daemon에 Desktop·모바일·CLI로 접근하는 구조**가 원하는 방식과 잘 맞았기 때문이다. 이미 구축된 Tailscale을 통한 직접 연결도 공식적으로 안내하고 있어, 새 접근 환경을 만들기보다 기존 환경에 붙이는 방향으로 구성하기 좋았다.

## 기존 환경과 변경한 환경

![기존 로컬 tmux·Pi TUI 환경과 Paseo Desktop·모바일 및 WSL·minipc Daemon 연결 구조 비교]({{ '/assets/img/pi-paseo-architecture.svg' | relative_url }})

*왼쪽은 기존 로컬 TUI 환경, 오른쪽은 Paseo를 통한 로컬·원격 연결 구조다.*

기존에는 노트북 WSL의 tmux에서 Pi를 직접 실행했다. 대화와 결과 확인은 TUI 중심이었고, 표시하기 어려운 결과는 다른 도구로 열어야 했다. 세션은 tmux 안에서 유지할 수 있었지만, 실행 호스트인 노트북이 꺼지면 로컬 작업도 중단됐다.

새 환경에서는 Windows에 Paseo Desktop을 두고, WSL과 minipc에 각각 Paseo Daemon을 실행한다. Pi는 각 Daemon이 관리하는 실행 호스트에서 작업한다. 그림의 초록색 점선 경계는 Windows 노트북·iPhone·minipc가 함께 연결된 기존 Tailscale 사설 네트워크(Tailnet)를 나타낸다. 회색 화살표는 노트북 내부의 로컬 연결, 초록색 화살표는 Desktop과 모바일에서 minipc로 접근하는 경로다.

- **WSL:** 로컬 소스 코드를 다루는 집중 개발에 사용한다.
- **minipc:** 오래 걸리는 작업과 노트북을 종료한 뒤에도 이어갈 작업을 실행한다.
- **Desktop·iPhone:** 실행 호스트의 세션에 연결해 대화하고 결과를 확인한다.

핵심은 **작업을 실행하는 장비와 대화하는 장비가 다르다는 것**이다. minipc에서 작업을 시작했다면 노트북을 끄고 iPhone으로 같은 세션에 접속할 수 있다.

### 네트워크는 기존 Tailscale을 그대로 사용했다

Tailscale은 이미 노트북과 집 내부망의 minipc를 연결하는 용도로 설정돼 있었다. 이번에는 그 사설 접근 경로를 Paseo 연결에도 그대로 사용했다.

모바일에서 접근하기 위해 Daemon 포트를 공개 인터넷에 노출할 필요는 없었다. 허용된 디바이스가 Tailscale을 통해 minipc의 Daemon에 연결하도록 구성하는 방향이다. 프로젝트 파일 수정과 명령 실행이 가능한 Agent의 제어 경로인 만큼, 편의성뿐 아니라 접근 범위를 제한하는 것도 중요했다.

이것은 공개 노출을 피하는 설계이며, Tailscale만으로 모든 보안 설정이 끝난다는 뜻은 아니다. Daemon의 수신 주소, 방화벽과 접근 정책, 클라이언트 인증은 함께 관리해야 한다.

### Pi와 프로젝트 설정은 유지했다

실제 작업을 수행하는 Agent는 기존 Pi다. 프로젝트의 공통 지침과 Skills 등 Harness는 리포지토리에서 Git으로 관리하고, 사용자 범위 Skills와 Extensions는 각 호스트의 Pi 실행 사용자 환경에 둔다.

Paseo로 접근 방식은 통합하지만 호스트 간 파일이 자동으로 동기화되는 것은 아니다. 작업에 필요한 저장소와 의존성, 인증 정보는 각 호스트에 준비하고, 코드 변경은 기존 Git 워크플로로 관리한다.

## 달라진 작업 흐름

### GUI에서 읽고, 필요한 부분은 직접 수정하기

Agent의 응답을 읽고 파일을 확인하는 기본 인터페이스를 TUI에서 Paseo GUI로 바꿨다. Markdown 초안처럼 직접 손보는 편이 빠른 결과물은 파일 편집기로 수정하고, 코드 변경은 Diff로 검토하는 흐름을 사용할 수 있다.

목표는 모든 작업을 Agent에게 요청하는 것이 아니라, Agent의 결과를 읽고 내가 수정하는 과정까지 한 작업 공간에서 이어가는 것이다.

<img src="{{ '/assets/img/pi-agent-paseo.png' | relative_url }}" alt="Paseo Desktop에서 Agent와 대화하면서 생성한 구조 이미지를 확인하는 화면" loading="lazy" style="display: block; width: 100%; max-width: 640px; height: auto; margin: 0 auto;">

*Paseo Desktop에서는 생성한 구조 이미지를 대화 안에서 확인하고, 바로 수정 요청을 이어갈 수 있었다.*

### 노트북을 닫고 모바일에서 대화 이어가기

minipc에서 실행한 작업은 노트북의 Paseo 화면과 분리돼 있다. 노트북을 종료한 뒤에도 minipc가 켜져 있고 Daemon과 Agent가 실행 중이면 모바일에서 기존 대화를 확인하고 후속 요청을 보낼 수 있다.

모바일로 개발 환경 전체를 대체하려는 것은 아니다. 결과를 확인하고 다음 지시를 보내기 위해 노트북을 다시 열 필요가 없다는 점이 중요한 변화다.

<img src="{{ '/assets/img/pi-agent-mobile.png' | relative_url }}" alt="iPhone의 Paseo에서 homelab-infra 프로젝트의 Agent 세션과 응답을 확인하는 화면" loading="lazy" style="display: block; width: 100%; max-width: 380px; height: auto; margin: 0 auto;">

*모바일 Paseo에서 프로젝트의 다음 작업을 질문하고 Agent의 응답을 확인하는 화면이다.*

### 다른 호스트의 Agent에 작업 맡기기

여러 호스트를 등록해두면 직접 실행 위치를 고르는 데서 더 나아가, 메인 Agent가 Paseo CLI로 다른 호스트의 Agent에 작업을 요청하는 방식도 사용할 수 있다. 예를 들어 로컬에서는 구현을 진행하고, minipc에는 별도 코드 분석이나 문서 작성을 맡기는 식이다.

## 정리

이번 구성에서 바꾼 것은 Pi 자체가 아니라 **결과를 읽는 인터페이스와 작업을 실행하는 위치**다.

Paseo GUI에서 대화와 결과 검토를 이어가고, Daemon이 실행 호스트에서 세션을 관리하도록 나눴다. 로컬 개발은 WSL에 남기고, 장시간 작업은 minipc에 맡긴다. 원격 연결에는 이미 구축한 Tailscale을 재사용해 Daemon을 공개 인터넷에 직접 노출하지 않는 방향으로 구성했다.

읽기와 리뷰에 집중할 수 있는 화면, 불필요한 도구 이동 감소, 클라이언트 종료와 독립적인 실행, 여러 호스트의 활용. 이 네 가지가 이번 환경을 구성한 기준이다.

## 참고 자료

- [herdr 공식 저장소](https://github.com/herdrdev/herdr)
- [Orca 공식 저장소](https://github.com/stablyai/orca)
- [Paseo 공식 저장소 — 편집기, 모바일, Daemon 및 CLI 안내](https://github.com/getpaseo/paseo)
- [Paseo Connectivity](https://paseo.sh/docs/connectivity)
