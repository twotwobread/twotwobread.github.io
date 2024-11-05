---
layout: post
title: (k8s) 쿠버네티스 스케줄링 분석
thumbnail-img: /assets/img/avatar-icon.png
tags: [k8s, kubernetes, 쿠버네티스, cka]
---

{: .box-note}
**Note**
해당 포스팅에서는 쿠버네티스에서 파드를 배포할 때 어떤 스케줄링 기법을 사용하는지에 대해서 알아보겠습니다.

## 쿠버네티스 스케줄링이란?
스케줄링이란 단어를 가장 많이 접했을 때가 OS 공부 시에 프로세스 스케줄링을 위해서 어떤 알고리즘들이 사용되는지 학습 시 가장 많이 접했습니다.
쿠버네티스에서의 스케줄링은 파드를 어떤 노드에 배포할 것인가를 Node Scheduler를 통해서 결정하는데 해당 포스팅에서는 어떤 방식으로 스케줄링하고 원하는 노드에 스케줄링 하기 위해서 쿠버네티스에서 제공하는 여러 기법들에 대해서 알아보겠습니다.
  
### 쿠버네티스 스케줄링 동작 방식
먼저 스케줄러의 주요 목적은 리소스 사용을 최적화하고 애플리케이션이 원활하고 효율적으로 실행되도록 만드는 것입니다. 이를 위해서 쿠버네티스 스케줄러는 두 가지 단계를 거쳐 스케줄링합니다.  
1. 필터링: 노드에 가용 가능한 리소스 사용량(CPU, MEM) 및 노드 용량 (최대 리소스), 네트워크 지연 최소화 (affinity & anti-affinity), taints 및 tolerations 등과 같은 기준으로 필터링을 거칩니다.
2. 스코어링: 필터링을 거친 노드들을 리소스 활용, 노드 용량, pod affinity 및 anti-affinity, 파드 간 통신 요구 사항, 사용자 정의 제약 조건 등에 의하여 점수를 매기고 점수가 높은 노드가 파드를 호스팅 하기 위한 우선권을 가집니다.  

### 쿠버네티스 스케줄링 기법
앞서 살펴 본 스케줄링 동작 방식들의 기준에 맞게 파드 생성 시 spec을 관리한다면 원하는 노드에 파드를 할당할 수 있습니다. 쿠버네티스에서는 이를 위해서 3가지 스케줄링 기법을 제공합니다.
#### 1. Taints & Tolerations
해당 기법은 특정 노드에 파드가 할당되는 것을 막기 위한, 제한을 위한 설정입니다. Udemy 강의에서는 Pod를 모기, Taints를 모기약, Tolerations를 모기약에 대한 면역이라고 비유했습니다. Taints를 노드에 뿌려서 Pod가 할당되지 못하게 막지만 Pod가 Tolerations을 가지고 있다면 해당 노드에 할당될 수 있는 느낌입니다.  
- Taints는 effect를 설정할 수 있습니다.
	- NoSchedule: 스케줄링 X
	- PreferNoSchedule: 노드에 파드가 할당되지 않게 노력 (무조건 X) -> 클러스터 내 리소스 부족 시 할당 가능. 
	- NoExecute: 스케줄링 X, 기존 할당된 파드들도 할당 해제  

- 예시  
	- 특정 노드에 taints 설정 -> 해당 키와 value에 관한 tolerations이 없는 파드는 스케줄링 불가능 (NoSchedule).  
		```kubectl taints nodes <node-name> app=myapp:NoSchedule```  
	- tolerations yaml 예시 -> Equal은 key, value 모두 일치해야 하고 Exists는 key만 일치하면 됩니다.  
		```yaml  
		apiVersion: v1
		kind: Pod
		metadata:
			name: myapp-pod
		spec:
			containers:
			- name: nginx-container
				image: nginx
			tolerations:
			- key: app
				operator: Equal
				value: myapp
				effect: NoSchedule
		```
  
  
#### 2. Node Selector
해당 기법은 노드에 라벨을 부여하여 특정 노드에 파드를 할당하기 위한 설정입니다. 이는 특정 파드에 요구되는 리소스가 큰 경우나 특정 노드에만 파드에 필요한 리소스가 존재하는 경우에 사용할 수 있습니다.  
업무 중 Node Selector를 쓴 경우가 특정 파드에서 NPU를 이용하여 추론을 돌리는 코드가 있었는데 NPU가 클러스터 내의 노드 중 하나에만 존재했어서 해당 노드에 라벨을 부여하고 Node Selector를 이용해서 간단하게 사용한 경험이 있습니다.  
- 예시  
	- CLI  
		```kubectl label nodes <node-name> key:value```
	- yaml
		```yaml
		apiVersion: v1
		kind: Pod
		metadata:
		spec:
			containers:
			- name: nginx-container
				image: nginx
			nodeSelector:
				key: value 
		```  

#### 3. Node Affinity
해당 기법은 Node Selector처럼 라벨을 부여하여 특정 노드에 스케줄링 하기 위한 설정인데 더 구체적으로 노드를 선택할 수 있는 기능입니다. Node Selector 이용 시에는 라벨이 일치해야 한다는 조건만 존재했지만 Node Affinity는 OR, NOT과 같은 논리 연산자 사용이 가능합니다.  
yaml 예시를 먼저 보고 추가적인 설명을 진행하겠습니다.
- yaml 예시  
	```yaml
	apiVersion: v1
	kind: Pod
	metadata:
	name: test-pod
	spec:
		containers:
		- name: test-container
			image: nginx
		affinity:
			nodeAffinity:
				requiredDuringSchedulingIgnoredDuringExecution:
					nodeSelectorTerms:
					- matchExpressions:
					  - key: size
					  	operator: In
					  	values:
					  	- Large
					  	- Medium
	```
	- 노드 선택 조건이 size를 키로 가지는 라벨이 [Large, Medium] 두 값 중 하나와 일치하는지를 판단.  
- Node Affinity Type
    - requiredDuringSchedulingIgnoredDuringExecution
		- ```required```: 이 조건은 반드시 충족되어야 함 (필수 조건)
		- ```DuringScheduling```: Pod가 처음 스케줄링될 때 이 규칙을 적용
		- ```IgnoredDuringExecution```: Pod가 이미 실행 중일 때는 이 규칙을 무시
		- 즉, Pod 스케줄링 시 일치하는 노드를 찾지 못하면 스케줄링 하지 않고 노드 라벨이 나중에 변경되더라도 실행 중인 Pod는 영향받지 않습니다.
        - 이는 포드 배치(placement)가 중요한 경우 사용합니다.
    - preferredDuringSchedulingIgnoredDuringExecution
		- ```preferred```: 무조건 충족 X
		- ```DuringScheduling```: Pod가 처음 스케줄링될 때 이 규칙을 적용
		- ```IgnoredDuringExecution```: Pod가 이미 실행 중일 때는 이 규칙을 무시
		- 즉, Pod 스케줄링 시 일치하는 노드를 찾지 못해도 룰을 무시하고 이용가능한 노드에 할당하고 노드 라벨이 나중에 변경되더라도 실행 중인 Pod는 영향받지 않습니다.
        - 이는 워크로드 실행이 더 중요한 경우 사용
    - requieredDuringSchedulingRequiredDuringExecution (planned)
		- ```required```: 이 조건은 반드시 충족되어야 함 (필수 조건)
		- ```DuringScheduling```: Pod가 처음 스케줄링될 때 이 규칙을 적용
		- ```RequiredDuringExecution```: Pod가 이미 실행 중일 때에도 규칙 적용
        - 즉, Pod 스케줄링 시 일치하는 노드 찾지 못하면 스케줄링 하지 않고 노드 라벨이 나중에 변경되면 실행 중인 Pod에 영향을 줌. (파드 퇴출)   
 
#### (추가)
만약 특정 노드에만 특정 파드들이 할당이 되고 나머지는 다른 노드에 할당되게 하려면 어떻게 하면 될까요??  
이를 위해선 특정 노드에 특정 파드들이 할당되도록 Node Selector or Node Affinity를 사용하고 나머지가 해당 노드에 할당되지 않게 하기 위해서 Taints를 이용하여 막아주고 할당되어야 하는 파드들에는 Toleration을 걸어줘야 합니다.  
Taints & Tolerations만 이용하게 되면 특정 노드에만 파드가 할당되게 만들 수 없기 때문에 이를 혼합해줘야합니다.

## 마무리
이 문서는 과거 학습한 내용을 바탕으로 정리한 것입니다. 잘못된 부분이나 개선할 표현이 있다면 피드백 부탁드립니다.

## Reference
- [k8s docs](https://kubernetes.io/ko/docs)
- [Udemy CKA 강의](https://www.udemy.com/course/certified-kubernetes-administrator-with-practice-tests/?srsltid=AfmBOoqnCrbfruYv66Esw2aE0Gqa7F8slLiwiY8ImTcR6el4vZptiHq-)
- [k8s sheduling](https://romanglushach.medium.com/kubernetes-scheduling-understanding-the-math-behind-the-magic-2305b57d45b1)
