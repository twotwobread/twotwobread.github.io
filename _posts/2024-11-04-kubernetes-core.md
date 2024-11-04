---
layout: post
title: (k8s) 쿠버네티스 클러스터 관리 리소스 및 주요 컴포넌트 분석
thumbnail-img: /assets/img/avatar-icon.png
tags: [k8s, kubernetes, 쿠버네티스, cka]
---

{: .box-note}
**Note**
회사의 인프라 관리를 위해 사용되며 지원이 제공되는 기술로, CKA 자격증 취득을 목표로 한 Kubernetes 학습 기록입니다.

## 쿠버네티스란?
공식 문서에 따르면, **쿠버네티스(Kubernetes)**는 "컨테이너화된 워크로드와 서비스를 관리하기 위한 이식 가능하고 확장 가능한 오픈소스 플랫폼"입니다. 쉽게 말해, 쿠버네티스는 컨테이너의 운영과 배포를 효율적으로 관리하는 플랫폼입니다.

### 쿠버네티스 아키텍처
![alt text](/assets/img/k8s-core1.png)  
쿠버네티스는 클러스터라는 컴퓨팅 리소스의 집합으로, 이 안에는 컨테이너를 실행하는 물리적 또는 가상 머신인 노드로 구성됩니다. 클러스터는 마스터 노드와 워커 노드로 구분됩니다.
- 마스터 노드는 클러스터의 리소스를 관리하고, 클러스터 상태 저장, 리소스 할당, 요청 처리 등 주요 관리 기능을 수행합니다.
- 워커 노드는 컨테이너화된 워크로드를 실행하고 관리하는 역할을 합니다.

### 마스터 노드의 주요 컴포넌트
#### ETCD
ETCD는 키-값(key-value) 형식의 데이터베이스로, 클러스터의 모든 상태 정보를 저장합니다. 파드, 노드, 설정(config), 시크릿(secret), 계정(account), 역할(role) 등 클러스터 전반의 상태를 기록하며, kubectl 명령어로 클러스터에 요청을 보낼 때 이 정보를 사용합니다.
#### Kube-API Server
Kube-API Server는 클러스터 내 모든 상태 변경 작업의 중심입니다. kubectl CLI로 요청된 작업을 처리하고, ETCD와 상호작용하여 클러스터의 상태를 업데이트합니다. 이는 ETCD와 직접 통신하는 유일한 컴포넌트입니다.
#### Kube Controller Manager
Kube Controller Manager는 클러스터 상태를 지속적으로 모니터링하고 필요한 조치를 취합니다. 예를 들어, 노드 장애 시 해당 노드의 파드를 다른 노드로 이동시킵니다. 클러스터의 안정성과 일관성을 유지하는 핵심 역할을 하며, Kube-API Server와 지속적으로 통신합니다.
#### Kube Scheduler
Kube Scheduler는 파드를 적절한 노드에 할당하는 역할을 합니다. 파드의 리소스 요구 사항, 노드의 상태 등을 고려해 파드를 배치합니다. 이후 파드의 생성 및 관리는 Kubelet이 담당합니다.
#### Kubelet
Kubelet은 워커 노드에서 마스터 노드와 통신하는 유일한 컴포넌트로, 노드에서 파드의 생성 및 삭제를 담당합니다. 컨테이너 런타임을 통해 파드를 생성하고 모니터링하여 Kube-API Server에 상태를 보고합니다.  
(추가) 클러스터 배포를 위해서 kubeadm 툴 사용 시 kubeadm은 다른 컴포넌트들과 다르게 자동으로 kubelet을 배포하지 않아서 수동으로 워커 노드들에 kubelet을 설치해줘야 합니다.
#### Kube-proxy
클러스터 내에서 모든 파드는 다른 모든 파드들에 접근할 수 있는데 이는 pod networking solution을 클러스터에 배포해 모든 파드들이 연결되는 모든 노드들에 걸친 가상 네트워크를 구성하기 때문입니다.
하지만 서비스는 파드같은 컨테이너가 아니라서 파드 네트워크에 조인할 수 없는데 서비스 정의 시 파드 간 통신이 가능한 이유는 Kube-Proxy 덕분입니다. Kube-proxy는 각 노드에서 실행되며, 클러스터 내 파드 간 네트워킹 및 트래픽 포워딩 규칙을 관리합니다. 이를 통해 클러스터 내부의 네트워크 및 서비스 기능을 제공합니다.  

### 쿠버네티스 주요 컴포넌트
k8s에는 컨테이너 관리, 운영, 통신 등을 위한 컴포넌트들이 존재합니다. 이에 대해서 알아보도록 하겠습니다.
#### Pod
- Pod는 쿠버네티스에서 가장 작은 단위의 컴포넌트이며, 하나 이상의 컨테이너를 캡슐화합니다.
- 일반적으로 하나의 컨테이너가 포함되지만, 로깅 및 로컬 통신을 위해 여러 컨테이너가 하나의 Pod에 함께 존재할 수 있습니다.
> yaml 예시
	```
	apiVersion: v1
	kind: Pod
	metadata:
	name: myapp-pod
	labels:
		name: myapp
		type: front
	
	spec:
	containers:
	- name: nginx-container
		image: nginx
	```
#### ReplicaSets
- ReplicaSet은 항상 일정 수의 파드가 실행되도록 보장하며, 로드 밸런싱 및 스케일링을 지원합니다.
- 노드의 자원이 부족할 경우, 다른 노드에 파드를 생성합니다.
> yaml 예시
	```
	apiVersion: apps/v1
	kind: ReplicaSet
	metadata:
	name: myapp-replica
	labels:
		name: myapp
		type: front
	
	spec:
	template:
		metadata:
		name: myapp-pod
		labels:
			name: myapp
			type: front
		containers:
		- name: nginx-container
		image: nginx
	replicas: 3
	selector:
		matchLabels:
		type: front
	```
- ```kubectl scale --replicas=6 replicaset myapp-replica``` 와 같이 type, name 넣어서 scale 변경이 가능.
#### Deployment
- Deployment는 파드와 ReplicaSet을 관리하며, 애플리케이션의 배포 및 관리를 자동화합니다.
- 롤링 업데이트, 스케일링, 버전 관리 등의 기능을 수행합니다.
> yaml 예시
	```
	apiVersion: apps/v1
	kind: Deployment
	metadata:
	labels:
		app: deploy
	spec:
	replicas: 3
	selector:
		matchLabels:
		app: deploy
	template:
		metadata:
		labels:
			app: deploy
		spec:
		containers:
		- name: nginx
			image: nginx
	```
#### Service
- Service는 컴포넌트 간의 통신을 가능하게 합니다.
- Service types
	- NodePort: 노드의 특정 포트를 외부로 export하여 노드 IP와 포트를 통해 파드에 접근합니다. (노드 포트의 범위는 30000 ~ 32767 입니다)
		![alt text](/assets/img/k8s-core2.png)  
	- ClusterIP는 내부에서 노드에서의 통신을 위해서 사용합니다. -> 파드는 생성되면 동적인 IP가 할당됩니다. 하지만 이런 동적 IP는 파드가 다시 뜨면 또 바뀌고 하기 때문에 내부 통신을 위한 정적 IP를 할당합니다.
	- LoadBalancer: 외부 트래픽을 규칙에 따라 여러 파드로 분산합니다.
		![alt text](/assets/img/k8s-core3.png)  
		- 그림처럼 특정 url로 접근했을 때 이 트래픽을 규칙에 의해 특정 파드의 특정 포트로 포워딩을 할 수 있습니다. 이를 통해서 트래픽을 균등하게 분산하여 안정적이고 확장 가능한 서비스를 제공할 수 있습니다.
#### Namespace
- Namespace는 서비스, 디플로이먼트 등 관련된 리소스를 그룹화하여 클러스터 내 여러 애플리케이션 리소스를 효율적으로 관리할 수 있도록 도와줍니다.

## 마무리
이 문서는 과거 학습한 내용을 바탕으로 정리한 것입니다. 잘못된 부분이나 개선할 표현이 있다면 피드백 부탁드립니다.

## Reference
- [k8s docs](https://kubernetes.io/ko/docs)
- [Udemy CKA 강의](https://www.udemy.com/course/certified-kubernetes-administrator-with-practice-tests/?srsltid=AfmBOoqnCrbfruYv66Esw2aE0Gqa7F8slLiwiY8ImTcR6el4vZptiHq-)
