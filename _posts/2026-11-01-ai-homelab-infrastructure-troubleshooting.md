---
layout: post
title: "AI Homelab 트러블슈팅: 같은 URL인데 요청 위치에 따라 결과가 달라진 이유"
subtitle: "집에서 만드는 AI 플랫폼 ③ — Dex OIDC 연동 중 만난 NAT와 소켓 바인딩 문제"
tags: [homelab, kubernetes, k3s, tailscale, oidc, dex, vault, networking]
comments: false
---

[이전 글]({% post_url 2026-10-30-ai-homelab-infrastructure-design %})에서는 K3s, Tailscale, Dex, Vault를 어떤 구조로 구성했는지 정리했다. 이번에는 이 구성 요소들을 연결하면서 발생한 두 가지 문제를 다루려고 한다.

첫 번째는 GitHub와 Dex를 통한 로그인은 성공했지만 Kubernetes API의 인증은 실패한 문제다. 두 번째는 호스트에서는 Dex에 접근할 수 있었지만 Vault 컨테이너에서는 연결하지 못한 문제다.

두 문제 모두 OIDC를 연결하는 과정에서 발생했다. 하지만 애플리케이션 설정만 확인하기보다 요청을 보내는 위치와 실제 패킷 경로를 나눠서 살펴보니, 서로 다른 네트워크 문제가 있었다.

본문은 문제를 재현하고 원인을 구분하는 순서로 정리했다. 명령은 확인 절차를 따라갈 수 있도록 정리한 예시이며, 출력은 필요한 부분만 발췌하거나 명시적으로 요약했다. `<DEX_DNS_NAME>`은 실제 Dex의 Tailscale DNS 이름으로 바꿔야 한다. IP와 컨테이너 이름 등도 자신의 환경에서 확인한 값을 사용해야 한다.

## 1. GitHub 로그인은 되는데 Kubernetes 인증은 실패한다

### 문제 인식

Dex를 minipc에서 Docker Compose로 실행하고, Tailscale Serve를 통해 HTTPS로 접근하도록 구성했다. 초기에는 기본 HTTPS 포트인 443을 사용했다.

의도한 접근 경로는 다음과 같았다.

```text
https://<DEX_DNS_NAME>:443
    ↓
Tailscale Serve
    ↓
호스트의 127.0.0.1:5556
    ↓
Dex 컨테이너
```

브라우저에서는 GitHub 로그인이 진행됐지만, WSL에서 다음 명령을 실행하면 `Unauthorized`가 발생했다.

```bash
kubectl --context=homelab-oidc auth whoami
```

로그인이 성공했는데 API 인증은 실패한다는 점에서, 두 과정이 실제로 어디까지 성공했는지 나눠서 확인할 필요가 있었다.

### 1단계: API 서버가 인증에 실패하는 이유 확인

먼저 인증을 처리하는 K3s API 서버 쪽에서 어떤 오류가 발생했는지 확인했다. minipc의 K3s 서비스 로그는 다음과 같이 조회할 수 있다. 조회 시간 범위는 문제 발생 시점에 맞춘다.

```bash
sudo journalctl -u k3s --since "10 minutes ago" --no-pager
```

당시 로그에서 확인한 내용은 다음과 같다. 아래는 원본 로그 전문이 아니라 핵심 내용의 요약이다.

```text
OIDC 인증기 초기화 반복
issuer 조회 과정에서 TLS 인증서 이름 불일치
응답 인증서는 Traefik 기본 인증서
```

이 결과로 문제를 RBAC 권한 검사보다 앞선 단계로 좁힐 수 있었다.

Kubernetes API 서버는 OIDC 인증을 준비하기 위해 Dex의 discovery endpoint에 접근하고, issuer와 공개키 조회 주소인 `jwks_uri` 등의 정보를 확인한다. 이후 토큰의 서명, issuer, audience, 만료 등을 검증한다.

```text
사용자 측 로그인
브라우저 / 로그인 도구 → GitHub·Dex → 토큰 획득

API 서버의 인증 준비
Dex discovery 조회 → 공개키 정보 확보 → 토큰 검증
```

개별 API 요청마다 discovery를 처음부터 다시 조회한다는 의미는 아니다. 사용자 쪽 로그인과 별개로 API 서버도 issuer에 접근할 수 있어야 한다는 뜻이다.

이번에는 API 서버가 discovery를 조회하는 HTTPS 연결부터 실패했다. 확인해야 할 질문은 다음으로 바뀌었다.

> API 서버가 Dex에 접근하려고 했는데, 왜 Traefik의 인증서를 받고 있는가?

### 2단계: DNS가 다른 서버를 가리키는지 확인

다른 서버의 인증서를 받았다면 먼저 이름 해석 결과를 확인해야 했다. minipc에서 DNS 조회 결과와 자신의 Tailscale IP를 비교했다.

```bash
getent ahostsv4 <DEX_DNS_NAME>
tailscale ip -4
```

DNS가 반환한 주소는 minipc의 Tailscale IP와 일치했다. 적어도 Dex 이름이 엉뚱한 서버 IP로 해석되는 상황은 아니었다.

다음으로 DNS와 HTTP proxy 영향을 배제하고 요청했다.

```bash
curl --noproxy '*' \
  --resolve '<DEX_DNS_NAME>:443:<MINIPC_TAILSCALE_IP>' \
  --connect-timeout 5 --max-time 10 \
  -v \
  'https://<DEX_DNS_NAME>/.well-known/openid-configuration'
```

`--resolve`는 요청할 호스트명과 TLS 검증은 유지하면서 연결할 IP를 고정한다. `--noproxy '*'`는 HTTP proxy를 사용하지 않도록 한다.

이 요청에서도 인증서 검증은 실패했다. 이름 해석이나 HTTP proxy보다, **올바른 IP로 보낸 요청이 이후 실제로 어디에 도달하는지**를 확인해야 했다.

### 3단계: 호스트의 443 요청을 변경하는 NAT 규칙 확인

API 서버와 Dex endpoint가 같은 minipc에 있다는 점이 중요했다. API 서버가 접근하는 Tailscale IP는 호스트 자신이 가진 주소였다.

포트를 listen하는 프로세스뿐 아니라, 소켓에 도달하기 전에 요청의 목적지를 바꾸는 NAT 규칙도 확인했다.

```bash
sudo iptables-save -t nat
```

관련 규칙을 구조적으로 요약하면 다음과 같았다.

```text
OUTPUT
  → 목적지가 LOCAL이면 CNI-HOSTPORT-DNAT

CNI-HOSTPORT-DNAT
  → TCP 목적지 포트가 80 또는 443이면 Pod별 chain

Pod별 chain
  → TCP 443 요청을 ServiceLB Pod:443으로 DNAT
```

CNI hostPort 규칙은 노드 포트를 Pod에 연결하기 위한 것이다. 예를 들어 `hostPort: 443`은 노드의 443 포트로 향하는 요청을 해당 Pod에 연결하도록 하는 설정이다. CNI의 portmap 구현은 목적지 주소를 바꾸는 DNAT 규칙으로 이 동작을 구현할 수 있다.

```text
노드 IP:443 → DNAT → Pod IP:443
```

NAT는 공유기에서만 사용하는 기능이 아니다. Linux 호스트에서도 커널의 규칙을 통해 패킷의 주소와 포트를 변경할 수 있다. `CNI-HOSTPORT-DNAT`는 별도의 서버가 아니라 이 처리를 위한 규칙 묶음인 chain의 이름이다.

이번 환경에서는 K3s의 ServiceLB가 Traefik의 LoadBalancer Service를 노출하면서 hostPort를 사용하고 있었다.

또한 `--dst-type LOCAL`은 목적지가 `127.0.0.1`인지만 검사하는 조건이 아니다. 호스트가 가진 Tailscale IP도 로컬 주소에 해당하므로, 호스트 자신이 보낸 요청이 이 조건에 매칭될 수 있었다.

### 조사 결과: DNS는 맞았지만 실제 TLS 서버가 달랐다

로그, curl 결과, NAT 규칙을 연결하면 다음 경로로 설명할 수 있었다.

```text
K3s API 서버
    ↓
minipc의 Tailscale IP:443으로 discovery 요청
    ↓
NAT OUTPUT의 LOCAL 조건에 매칭
    ↓
CNI hostPort 규칙으로 ServiceLB Pod:443에 DNAT
    ↓
Traefik에 도달
    ↓
Traefik 기본 인증서 반환
    ↓
Dex 호스트명과 인증서 이름 불일치
    ↓
OIDC 인증기 초기화 실패
```

인증서가 없었던 것이 아니라 **의도하지 않은 서버의 인증서를 받은 문제**였다. HTTPS 연결의 TLS 인증서 검증에서 실패했으므로, 토큰 서명을 확인하는 JWKS 검증까지 진행할 수 없었다.

이 때문에 `ss`로 어떤 프로세스가 포트를 listen하는지만 확인해서는 충분하지 않았다. 커널의 NAT 규칙이 소켓에 도달하기 전에 목적지를 변경할 수 있기 때문이다.

이 경로는 당시 로그와 설정을 대조해 분석한 것이며, 첫 번째 문제의 전체 패킷 경로를 캡처한 것은 아니다.

### 해결 방안과 트레이드오프

가능한 해결 방향을 비교하면 다음과 같다. 모든 대안을 실제로 적용해 비교한 것은 아니다.

| 방안 | 장점 | 단점·고려할 점 |
| --- | --- | --- |
| Dex의 외부 HTTPS 포트를 8443으로 분리 | 기존 ingress에 대한 변경이 작고 충돌 범위가 명확함 | issuer와 callback 등 관련 URL을 함께 변경해야 함 |
| Traefik·ServiceLB의 443 노출 구조 변경 | Dex의 기본 HTTPS 포트를 유지할 수 있음 | 기존 ingress와 서비스 노출에 미치는 영향이 큼 |
| Dex를 기존 ingress 뒤로 통합 | HTTPS 진입점을 통합할 수 있음 | 인증 접근이 Kubernetes ingress 구성에 의존하며 추가 설계 필요 |

TLS 검증을 끄거나 K3s가 관리하는 NAT 규칙을 직접 삭제하는 방법은 선택하지 않았다. 전자는 잘못된 endpoint로 연결되는 원인을 해결하지 못하고, 후자는 서비스 노출을 깨뜨리거나 관리 컴포넌트에 의해 다시 생성될 수 있기 때문이다.

### 최종 선택: Dex의 외부 HTTPS 포트를 분리

기존 ingress에 미치는 영향을 줄이기 위해 Tailscale Serve에서 Dex를 노출하는 포트를 8443으로 변경했다.

```text
https://<DEX_DNS_NAME>:8443
    ↓
Tailscale Serve
    ↓
127.0.0.1:5556
    ↓
Dex
```

Dex 내부 HTTP 포트 5556과 Kubernetes API의 기존 LAN 주소·6443 포트는 유지했다. issuer URL이 바뀌므로 다음 설정은 함께 맞췄다.

| 변경 대상 | 변경 내용 |
| --- | --- |
| Tailscale Serve | HTTPS 8443으로 Dex 노출 |
| Tailscale 접근 정책 | 관리 노트북에서 TCP 8443 접근 허용 |
| Dex issuer | `https://<DEX_DNS_NAME>:8443` |
| Dex의 GitHub connector redirect URI | 새 Dex 주소의 `/callback` |
| GitHub OAuth App callback | Dex의 새 callback과 일치 |
| K3s OIDC 설정 | 새 Dex issuer 사용 |
| kubeconfig의 OIDC 로그인 도구 | 같은 issuer 사용 |

GitHub에서 Dex로 돌아오는 callback과 kubectl 로그인 도구의 localhost callback은 서로 다르다. 이번 변경에서는 로그인 도구의 `http://localhost:8000` callback을 유지했다.

변경 후 WSL과 minipc에서 discovery 요청을 확인했다.

```bash
curl --fail --silent --show-error \
  'https://<DEX_DNS_NAME>:8443/.well-known/openid-configuration'
```

다시 로그인한 뒤 OIDC 신원과 권한을 각각 확인했다.

```bash
kubectl --context=homelab-oidc auth whoami

kubectl --context=homelab-oidc \
  auth can-i '*' '*' --all-namespaces

kubectl --context=homelab-oidc get nodes
kubectl --context=homelab-oidc get pods -A
```

개인 OIDC 신원 확인과 RBAC 적용 후 권한·리소스 조회가 성공했다. 인증이 성공한 것과 관리자 권한을 부여한 것은 별개의 단계로 확인했다.

8443이라는 포트 자체가 보안을 강화한 것은 아니다. **기존 443 NAT 경로와 충돌하지 않도록 분리하고, 올바른 TLS endpoint로 연결되게 만든 것**이 해결의 핵심이었다.

## 2. 호스트에서는 Dex에 접근되는데 Vault 컨테이너에서는 안 된다

### 문제 인식

Kubernetes에 이어 Vault에도 GitHub·Dex 기반 OIDC 로그인을 연결하려고 했다.

Vault 역시 브라우저 로그인만으로 동작하지 않는다. Vault 서버 자신이 Dex의 discovery를 조회하고, authorization code를 토큰으로 교환하는 등의 서버 간 통신을 수행해야 한다.

그런데 Vault가 Docker bridge 네트워크에서 실행될 때 같은 Dex URL에 대한 결과가 달랐다.

```text
minipc 호스트 → Dex:8443
성공

Docker bridge의 Vault → Dex:8443
Connection refused
```

원인을 구분하려면 Vault의 OIDC 설정과 네트워크 연결을 나눠서 봐야 했다. 아래에서는 동일한 bridge 환경의 curl 컨테이너로 증상을 재현하고, 패킷과 방화벽 규칙, 소켓 바인딩을 확인하는 순서로 설명한다.

### 1단계: 실제 endpoint와 리스너 확인

먼저 현재 Serve 설정과 소켓을 확인한다. 명령은 minipc 호스트에서 실행한다.

```bash
tailscale version
tailscale ip -4
tailscale serve status

sudo ss -lntpe 'sport = :8443'
```

관련 결과를 발췌하고 호스트명을 치환하면 다음과 같다.

```text
Tailscale: 1.104.2
Tailscale IPv4: 100.64.29.60

https://<DEX_DNS_NAME>:8443 (tailnet only)
|-- / proxy http://127.0.0.1:5556

LISTEN ... 100.64.29.60%tailscale0:8443 ... tailscaled
```

8443은 열려 있었고 Serve의 backend도 Dex로 연결되어 있었다. 주목한 것은 `%tailscale0`였다. 리스너가 IP·포트뿐 아니라 기기 바인딩 정보도 갖고 있었다.

하지만 이 출력만으로 bridge 요청의 거절 원인을 확정할 수는 없다. 실제 요청이 어디까지 가는지와 방화벽의 거절 여부를 확인해야 한다.

### 2단계: 호스트와 컨테이너의 네트워크 차이 확인

호스트가 자신의 Tailscale IP로 요청할 때의 경로를 확인한다.

```bash
TS_IP=$(tailscale ip -4)
ip -4 route get "$TS_IP"
```

결과:

```text
local 100.64.29.60 dev lo table local src 100.64.29.60 uid 1000
    cache <local>
```

호스트의 요청은 VPN 터널을 나갔다가 돌아오는 것이 아니라 로컬 전달 경로를 사용하고 있었다.

컨테이너가 연결되는 네트워크는 다음 명령으로 확인한다.

{% raw %}
```bash
docker network ls

docker ps \
  --format 'table {{.Names}}\t{{.Networks}}\t{{.Ports}}'
```
{% endraw %}

재현 대상은 문제가 발생한 Vault의 bridge 네트워크인 `homelab-vault_default`다. 이 네트워크에 임시 curl 컨테이너를 연결하면 Vault의 설정이나 프로세스를 변경하지 않고도 같은 네트워크에서 Dex에 접근할 수 있는지 확인할 수 있다.

### 3단계: DNS를 배제하고 같은 endpoint에 요청

호스트와 진단 컨테이너에서 같은 URL·IP·포트로 요청한다. 이름 해석 차이를 배제하기 위해 `--resolve`를 사용하고 TLS 검증은 유지한다.

호스트 요청:

```bash
curl --noproxy '*' \
  --resolve '<DEX_DNS_NAME>:8443:100.64.29.60' \
  --connect-timeout 5 --max-time 10 \
  --silent --show-error --verbose \
  --output /dev/null \
  --write-out '\nHTTP=%{http_code} TOTAL=%{time_total}s\n' \
  'https://<DEX_DNS_NAME>:8443/.well-known/openid-configuration'
```

결과 발췌:

```text
SSL certificate verify ok.
HTTP=200
TOTAL=0.031557s
```

기존 Vault bridge에서 요청한다. 해당 이미지가 없으면 다운로드가 발생하며, 컨테이너는 종료 후 자동 삭제된다. Docker 소켓이나 호스트 디렉터리는 마운트하지 않는다.

```bash
docker run --rm \
  --network homelab-vault_default \
  curlimages/curl:8.12.1 \
  --noproxy '*' \
  --resolve '<DEX_DNS_NAME>:8443:100.64.29.60' \
  --connect-timeout 5 --max-time 10 \
  --silent --show-error --verbose \
  --output /dev/null \
  --write-out '\nHTTP=%{http_code} TOTAL=%{time_total}s\n' \
  'https://<DEX_DNS_NAME>:8443/.well-known/openid-configuration'
```

결과 발췌:

```text
connect to 100.64.29.60 port 8443 from 172.20.0.2 port 43068 failed: Connection refused
HTTP=000
TOTAL=0.000311s
```

Vault가 아닌 단순 curl 컨테이너에서도 실패했다. 따라서 Vault의 OIDC role이나 policy를 수정하기 전에 TCP 연결 경로부터 조사해야 했다.

### 4단계: SYN이 어디까지 가는지 패킷 캡처

`Connection refused`만으로는 어디서 연결을 거절했는지 알 수 없다. 별도 터미널에서 캡처를 실행하고 앞의 호스트 요청과 bridge 요청을 각각 한 번씩 수행한다.

```bash
sudo tcpdump -ni any -nn -tttt \
  'host 100.64.29.60 and tcp port 8443'
```

호스트 요청은 `lo`에서 정상적인 연결 수립이 확인됐다. 아래는 주요 필드만 추린 것이다.

```text
lo In  100.64.29.60.49768 > 100.64.29.60.8443  Flags [S]
lo In  100.64.29.60.8443  > 100.64.29.60.49768 Flags [S.]
lo In  100.64.29.60.49768 > 100.64.29.60.8443  Flags [.]
```

`[S]`, `[S.]`, `[.]`는 각각 SYN, SYN-ACK, ACK다. TCP 연결이 성립한 뒤 curl에서 TLS 검증과 HTTP 200도 확인했다.

반면 컨테이너 요청은 다음과 같았다.

```text
vethfa2b670       P   172.20.0.2.43068 > 100.64.29.60.8443  Flags [S]
br-34a5b8b90b46  In  172.20.0.2.43068 > 100.64.29.60.8443  Flags [S]
br-34a5b8b90b46  Out 100.64.29.60.8443 > 172.20.0.2.43068  Flags [R.]
vethfa2b670       Out 100.64.29.60.8443 > 172.20.0.2.43068  Flags [R.]
```

veth와 bridge에서 같은 SYN을 관측한 것이며, 이어 RST-ACK이 반환됐다. 컨테이너의 패킷은 호스트까지 도착했지만 TLS handshake를 시작하기 전에 연결이 거절됐다.

따라서 문제를 **“호스트에 도착하지 못했다”가 아니라 “호스트에 도착했지만 TCP 연결이 거절됐다”**고 좁힐 수 있었다.

다음으로는 RST가 방화벽의 명시적인 거절인지, 요청을 받아줄 소켓이 매칭되지 않은 결과인지 구분해야 했다.

### 5단계: NAT와 방화벽의 거절 여부 확인

```bash
sudo iptables --version
sudo iptables -t nat -S
sudo iptables -t filter -S
sudo nft -a list ruleset
```

환경의 iptables는 `v1.8.10 (nf_tables)`였다. nftables 전체 규칙도 함께 확인하되, iptables가 관리하는 규칙을 수정하거나 초기화하지 않았다.

테스트 패킷의 조건을 기준으로 규칙을 따라갔다.

```text
출발지: 172.20.0.2
목적지: 100.64.29.60
포트:   TCP 8443
유입:   기존 Vault의 Docker bridge
```

확인한 내용은 다음과 같았다.

| 확인 대상 | 결과 |
| --- | --- |
| CNI hostPort DNAT | 80·443에 적용되며 8443은 해당하지 않음 |
| Docker DNAT | localhost의 5556 대상이며 이번 요청과 다름 |
| Kubernetes Service·NodePort | 이번 목적지 IP·포트에 해당하는 변환 없음 |
| Tailscale INPUT 규칙 | 이번 출발지에 매칭되는 DROP 없음 |
| 나머지 INPUT 경로 | 이번 요청에 해당하는 REJECT가 보이지 않음 |
| INPUT 기본 정책 | ACCEPT |

특히 다음 Tailscale 규칙은 목적지가 아니라 **출발지**를 검사한다.

```text
-A ts-input -s 100.64.0.0/10 ! -i tailscale0 -j DROP
```

테스트 컨테이너의 출발지는 `172.20.0.2`였으므로 해당하지 않았다. “tailscale0가 아닌 곳에서 들어왔으니 전부 DROP한다”는 규칙은 아니었다.

또한 이번 목적지는 호스트 자신의 주소다. DNAT가 없다면 로컬 INPUT 경로를 보게 되므로, FORWARD 기본 정책이 DROP이라는 사실만으로 원인을 설명할 수는 없었다.

확인한 규칙상으로는 요청을 다른 곳으로 전달하거나 명시적으로 거절하는 경로가 보이지 않았다. 그러면 다음으로 살펴볼 것은 TCP 수신 소켓의 조건이었다. 방화벽이 허용했다는 것과 해당 패킷을 받아줄 소켓이 존재한다는 것은 별개다.

### 6단계: 같은 이미지에서 네트워크 모드만 변경

호스트의 curl과 컨테이너의 curl이 다르다는 변수도 줄이기 위해, 같은 이미지를 host network로 실행한다.

```bash
docker run --rm \
  --network host \
  curlimages/curl:8.12.1 \
  --noproxy '*' \
  --resolve '<DEX_DNS_NAME>:8443:100.64.29.60' \
  --connect-timeout 5 --max-time 10 \
  --silent --show-error \
  --output /dev/null \
  --write-out '\nHTTP=%{http_code} TOTAL=%{time_total}s\n' \
  'https://<DEX_DNS_NAME>:8443/.well-known/openid-configuration'
```

결과:

```text
HTTP=200
TOTAL=0.025452s
```

같은 이미지와 요청에서도 bridge는 실패하고 host network는 성공했다. 컨테이너 자체의 문제라기보다 **네트워크 namespace와 그에 따른 요청 경로 차이**라는 근거가 됐다.

### 7단계: 기기 바인딩과 호스트 로컬 요청의 관계 확인

여기까지 보면 Serve의 `%tailscale0` 바인딩이 중요한 원인으로 보였다. 하지만 “tailscale0를 실제로 통과한 패킷만 받는다”라고 설명하면 호스트 요청의 성공을 설명할 수 없었다. 실제 호스트 요청은 `lo`에서 관측됐기 때문이다.

먼저 로컬 주소가 어느 기기에 연결되어 있는지 확인한다.

```bash
ip -4 route show table local type local | grep -F '100.64.29.60'
```

결과:

```text
local 100.64.29.60 dev tailscale0 proto kernel scope host src 100.64.29.60
```

앞서 조회한 실제 로컬 전달 경로와 비교하면 다음과 같았다.

```text
로컬 주소의 원래 기기: tailscale0
호스트 자체 요청의 전달 경로: lo
```

커널 버전도 확인했다.

```bash
uname -r
```

```text
6.8.0-147-generic
```

이 결과를 바탕으로 upstream Linux v6.8의 IPv4 라우팅과 TCP 소켓 조회 코드를 대조했다.

[route.c의 로컬 목적지 처리](https://github.com/torvalds/linux/blob/v6.8/net/ipv4/route.c#L2788-L2807)에서는 실제 전달에 loopback을 사용하더라도 원래 라우팅 결과의 기기 정보를 보존한다.

```c
/* make sure orig_oif points to fib result device even
 * though packet rx/tx happens over loopback or l3mdev
 */
orig_oif = FIB_RES_OIF(*res);
```

[라우트 생성 과정](https://github.com/torvalds/linux/blob/v6.8/net/ipv4/route.c#L2593-L2598)에서 이 정보가 저장된다.

```c
rth->rt_iif = orig_oif;
```

소켓 조회에 사용하는 [inet_iif()](https://github.com/torvalds/linux/blob/v6.8/include/net/route.h#L341-L349)는 이 정보가 있으면 우선 사용한다.

```c
if (rt && rt->rt_iif)
    return rt->rt_iif;

return skb->skb_iif;
```

그리고 [기기 바인딩 비교](https://github.com/torvalds/linux/blob/v6.8/include/net/inet_sock.h#L145-L151)에서는 소켓에 지정된 기기와 조회에 전달된 기기 정보를 비교한다.

```c
return bound_dev_if == dif || bound_dev_if == sdif;
```

즉, **tcpdump에서 보이는 전달 인터페이스와 TCP 소켓 조회에 사용하는 기기 정보가 항상 같지는 않다.** 이 동작은 호스트 요청이 loopback으로 전달되면서도 `tailscale0`에 바인딩된 리스너와 연결되는 결과를 설명한다.

### 조사 결과: IP·포트뿐 아니라 소켓의 기기 조건이 달랐다

관측과 소스를 종합한 분석은 다음과 같다.

```text
호스트 / host-network 컨테이너
    ↓
자신의 Tailscale IP로 요청
    ↓
실제 전달은 lo
원래 로컬 경로의 기기 정보는 보존
    ↓
Serve 리스너의 기기 조건과 매칭 가능
    ↓
연결 성공
```

```text
bridge 컨테이너
    ↓
veth → Docker bridge로 호스트에 유입
    ↓
호스트 자체의 로컬 출력 경로와는 다름
    ↓
Serve 리스너의 기기 조건과 맞지 않는 것으로 판단
    ↓
TCP RST 반환
```

목적지가 Tailscale IP라고 해서 외부에서 들어온 패킷의 유입 기기가 자동으로 `tailscale0`로 바뀌지는 않는다.

이 분석은 패킷 캡처, 리스너, 라우팅, 방화벽 규칙과 upstream Linux v6.8 소스를 대조한 결과다. 실제 Ubuntu 커널의 모든 패치나 해당 SYN 처리 시점의 소켓 조회 변수를 직접 추적한 것은 아니라는 점은 구분한다.

### 해결 방안과 트레이드오프

네트워크 경로를 바꾸는 방법을 비교하면 다음과 같다. 아래 대안을 모두 적용해 검증한 것은 아니다.

| 방안 | 장점 | 단점·고려할 점 |
| --- | --- | --- |
| Vault를 host network로 전환 | 기존에 성공한 호스트 경로 활용, Dex issuer와 callback 유지 | 네트워크 namespace 격리가 줄어들고 호스트 localhost 서비스에 접근 가능 |
| 공유 Docker 네트워크와 내부 TLS 구성 | bridge를 유지하며 Vault→Dex 내부 통신 구성 가능 | DNS alias, 내부 HTTPS listener, 인증서 배포·갱신 등 추가 관리 필요 |
| 별도 내부 HTTPS 프록시 구성 | 내부 접근 경로를 명시적으로 제공 가능 | 프록시·인증서·접근 정책 등 운영 대상 증가 |

내부 경로를 사용하더라도 issuer URL과 인증서 이름을 일관되게 유지해야 한다. Docker alias는 이름을 IP로 해석할 뿐 포트를 바꾸지 않는다. 같은 issuer를 유지한다면 내부에서도 그 URL에 맞는 HTTPS endpoint를 제공해야 한다.

Vault의 token 교환만 내부 HTTP 주소로 보내는 방안도 검토했다. 하지만 당시 확인한 [Vault OIDC 설정 API](https://developer.hashicorp.com/vault/api-docs/auth/jwt)에는 token endpoint만 따로 덮어쓰는 일반 설정이 없었다. discovery 조회 주소만 내부로 바꾼다고 응답에 포함된 endpoint들이 자동으로 바뀌는 것도 아니었다.

내부 HTTP를 사용한다면 code와 client secret, token 등의 전송 보호도 별도로 고려해야 한다. 단순히 같은 Docker 네트워크라는 이유로 이 문제가 사라지는 것은 아니다.

### 최종 선택: host network로 성공한 경로 활용

현재 규모에서는 Dex의 endpoint와 인증서 구성을 다시 설계하는 대신, 이미 성공한 호스트 요청 경로를 사용하는 쪽을 선택했다.

같은 curl 이미지를 사용한 비교에서도 bridge에서는 연결이 거절되고 host network에서는 HTTP 200이 반환됐다. 이 차이는 Vault를 host network로 전환하면 호스트의 정상적인 로컬 요청 경로를 사용할 수 있다는 점을 뒷받침한다. 실제 적용한 해결책도 이 방식이었다.

Vault를 host network로 전환하면서 다음을 함께 유지하거나 조정했다.

- 기존 Docker ports 매핑을 제거하고 host network 사용
- API listener를 minipc의 Tailscale IP에 바인딩
- 단일 노드용 cluster listener를 loopback에 바인딩
- TLS와 Vault 인증 유지
- 기존 데이터와 unseal 자료 유지
- 초기화를 반복하지 않고 기존 자료로 unseal

전환 후 Vault의 unseal과 OIDC 로그인이 정상적으로 동작했다.

host network는 모든 상황에서의 정답은 아니다. 컨테이너가 호스트의 localhost 서비스에 접근할 수 있으므로 bridge를 사용할 때와 네트워크 격리 범위가 달라진다. Vault API의 IP 바인딩 역시 방화벽이나 인증을 대신하지 않는다.

또한 이 변경으로 Vault 자체 TLS 인증서 파일의 갱신·배포 책임이 사라지는 것은 아니다. 네트워크 연결 문제와 인증서 수명 관리는 별도의 과제로 봐야 한다.

## 마무리

첫 번째 문제는 **올바른 IP로 요청했지만 NAT 때문에 다른 TLS 서버에 도달한 문제**였다. 두 번째는 **호스트까지 요청이 도착했지만 네트워크 경로와 소켓의 기기 조건이 맞지 않아 연결이 거절된 것으로 분석한 문제**였다.

두 문제 모두 URL과 애플리케이션 설정만 보면 원인을 찾기 어려웠다. 요청을 어디서 생성했는지, 어떤 경로로 전달되는지, 어느 단계에서 실패했는지를 나누고 각 단계의 증거를 확인해야 했다.

이번에는 그 과정을 거치면서 같은 호스트, 같은 IP, 같은 URL이라는 사실만으로 같은 연결 경로를 가정할 수 없다는 것을 배웠다.
