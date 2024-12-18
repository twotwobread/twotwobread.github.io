---
layout: post
title: (Go) 포인터 정리하기 (인터페이스 vs 구현체 리시버 사용)
thumbnail-img: /assets/img/avatar-icon.png
tags: [go, golang, pointer]
---

{: .box-note}
**Trouble Incident**  
개인 프로젝트에서 인터페이스를 만들고 이를 구현하는 구조체를 생성한 후, 인터페이스 타입 변수로부터 구현 객체를 받아 사용하려고 했을 때, 포인터 리시버 메서드를 호출할 수 없었습니다. Go에서 포인터가 어떻게 동작하는지 알아보고, 왜 인터페이스 타입 변수에 값을 할당할 수 없는지 살펴보겠습니다.

## Go에서 포인터 동작
Go에서는 값 타입의 구조체를 생성해도, 값 리시버와 포인터 리시버 모두 사용할 수 있습니다.
```go
import "fmt"

type Dog struct {
	name string
}

func (d *Dog) Eat(food string) {
	fmt.Printf("%s eat %s", d.name, food)
}

...

d := Dog{name: "Max"}
d.Eat("Sushi") -> 잘 동작함.
d = &Dog{name: "Max"}
d.Eat("Gogi") -> 잘 동작함.
```

Go에서는 변수가 참조될 때 내부적으로 자동으로 값이 역참조(dereference)됩니다. 이를 수동으로 하려면 * 연산자를 사용해야 합니다.
```go
v := 10
pV := &v
println(pV)
println(*pV)

// 0x1400007af28
// 10 
```
### 왜 구조체 값을 사용할까요?
포인터 리시버 메서드를 호출할 때 참조를 사용하지 않으면 안 된다고 생각할 수 있습니다. 예를 들어 아래처럼 작성하는 것이 더 맞다고 생각할 수 있습니다.
```go
d := Dog{name: "Max"}
(&d).Eat("Sushi")   // 이렇게 실행해야 한다고 생각할 수 있습니다.
d.Eat("Sushi")      // 그런데 이렇게도 잘 작동합니다. 왜일까요?
```
Go에서는 이러한 편의를 위해 컴파일 시 자동으로 내부적으로 <code>&d</code>가 추가됩니다. 즉, <code>d.Eat("Sushi")</code>는 <code>(&d).Eat("Sushi")</code>로 자동 변환됩니다. 이는 Go 언어의 특별한 편의 기능입니다.

## 인터페이스에서 포인터 동작
이번엔 문제 상황을 재현한 코드를 살펴보겠습니다.
```go
import "fmt"

type Animal interface {
	Eat(string)
	Move(int, int)
	Sleep(int)
}

type Dog struct {
	name string
}

func (d *Dog) Eat(food string) {
	fmt.Printf("%s eat %s", d.name, food)
}

...

var d Animal
d = Dog{ // 컴파일 에러 발생.
    name: tt.fields.name,
}
d.Eat(tt.args.food)
```
위 코드에서 값 타입의 구조체 Dog를 인터페이스 타입인 Animal 변수 d에 할당하려고 할 때 컴파일 오류가 발생합니다. 그 이유는 무엇일까요?

### 원인 분석
이 오류는 Animal이 본질적으로 참조 유형인 인터페이스 유형이기 때문에 발생합니다. Go에서 인터페이스는 추상 유형이므로 직접 인스턴스화할 수 없습니다. 인터페이스를 구현하는 구체적인 유형은 항상 필요하며, 메서드가 포인터 리시버를 사용하는 경우 인터페이스를 구현하는 구조체에 포인터를 전달해야 합니다.

오류를 해결하는 방법은 다음과 같습니다.
```go
d = &Dog{   // 포인터로 할당해야 함
    name: "Max",
}
d.Eat("Sushi")   // 정상 동작
```
따라서 인터페이스는 값 구조체를 직접 복사할 수 없습니다. 추상 유형이므로 구조체에 대한 참조를 받아야 합니다.

## 마무리
프로젝트 도중 리시버와 관련된 오류를 조사하다가 포인터 동작에 대해 더 깊이 알아보았습니다. 결과적으로 포인터와 관련된 중요한 문제는 아니었지만, Go 언어의 편의성 덕분에 이런 자동 변환이 이루어지고 있음을 알게 되었습니다.
수신기와 관련된 이 오류를 조사하는 동안 Go의 포인터 동작을 더 자세히 살펴보았습니다. 이 오류는 포인터 자체와 관련된 주요 문제가 아니라 값 유형과 포인터 유형 간의 자동 변환을 위해 Go 언어에서 제공하는 편의 기능 때문이었습니다.

