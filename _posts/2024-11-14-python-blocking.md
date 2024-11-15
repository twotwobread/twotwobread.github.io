---
layout: post
title: (python) blocking, non-blocking 이해하기
thumbnail-img: /assets/img/avatar-icon.png
tags: [python, 파이썬, blocking, non-blocking, asyncio, 코루틴, coroutine]
---

{: .box-note}
**Note**   
회사 업무 중 코루틴을 다루다가 제어권 관련한 문제가 발생했고 이에 대한 해결 방안 및 개선점에 대해서 살펴보겠습니다.

## 구현 기능 설명
회사 업무 중 ip 캠에서 이미지 프레임을 가져와서 gstreamer 파이프라인에 input 하여 프로세싱한 이미지 프레임을 mjpeg으로 server push하는 api를 만들어야 했습니다. 이를 위해선 다음 두 동작이 필요합니다.  
1. 캠에서 이미지 프레임 가져와서 파이프라인에 삽입하기  
2. 파이프라인에서 프로세싱된 프레임 가져오기  

해당 두 로직은 의존성이 없고 독립적 실행이 필요했고 I/O, 네트워크와 관련된 로직이라 생각해 스레딩이 더 적합하다 판단했습니다. 그래서 코루틴을 이용하여 위 함수들을 구현했습니다.  

## 문제 상황
### 예시 코드
```python
import cv2
import asyncio
import queue

class FrameHandler:
    def __init__(self, address):
        self.is_running = False
        self.address = address
        self.org_frames = queue.Queue()
        self.proc_frames = queue.Queue()
        self.read_task = None
    
    def stop(self):
        self.is_running = False
        if self.read_task:
            self.read_task.cancel()
    
    def __aiter__(self):
        self.is_running = True
        self.read_task = asyncio.create_task(self.read_ipcam_frames())
        return self
        
    async def __anext__(self):
        if not self.is_running:
            raise StopAsyncIteration
        if not self.proc_frames.empty():
            processed_frame = self.proc_frames.get_nowait()
            if processed_frame is not None and processed_frame.any():
                loop = asyncio.get_running_loop()
                _, encoded_frame = await loop.run_in_executor(
                    None, lambda: cv2.imencode(".jpg", processed_frame)
                )
                return (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + encoded_frame.tobytes()
                    + b"\r\n"
                )
    
    async def read_ipcam_frames(self):
        cap = cv2.VideoCapture(self.address)
        if not cap.isOpened():
            print(f"Error: Can't connect ipcam address (addr: {self.address})")
            return
        
        try:
            while self.is_running:
                ret, frame = cap.read()
                if not ret:
                    print(f"Error: Can't read ipcam frame (addr: {self.address})")
                    break
                self.org_frames.put(frame)
                await asyncio.sleep(0)
                
        finally:
            cap.release()
```
문제 상황 재현을 위해서 위와 같이 간단하게 frame handler를 구현했습니다. frame handler는 ipcam frame을 읽어오는 코루틴을 가지고 async generator 구현을 위해서 필요한 내부 구현 메소드들을 추가했습니다. 그리고 pipeline에서 org_frames에 담긴 frame을 읽어가서 processing 후에 proc_frames에 담는다고 가정했습니다.  
위 frame handler를 async for을 이용하여 iterate 하면 하나의 코루틴만 동작할 것 입니다. 그 이유는 코루틴 내부에서 제어권을 놓지 않기 때문에 계속 하나의 코루틴만 제어권을 가집니다. 위와 같은 경우 asyncio.sleep을 넣어주면 제어권을 놓으면서 동작하게 됩니다.  
하지만 sleep을 이용해서 고정된 시간을 쉬게 된다면 그 이상의 fps가 필요한 경우 이를 처리하는 것이 불가능할 수 있다는 생각이 들었습니다 (ipcam의 fps도 엄청 높다는 가정). sleep을 이용하지 않고 제어권을 놓게 하기 위해서 코루틴 내부에서 I/O, 네트워크가 필요한 로직을 코루틴으로 빼내야겠다고 생각을 했습니다.
## 해결 방안
### 예시 코드
```python
import asyncio
import queue
from concurrent.futures import ThreadPoolExecutor

import cv2


class FrameHandler:
    def __init__(self, address):
        self.is_running = False
        self.address = address
        self.org_frames = queue.Queue()
        self.proc_frames = queue.Queue()

        self._thread_executor = ThreadPoolExecutor(max_workers=1)
        self.read_task = None

    def stop(self):
        self.is_running = False
        if self.read_task:
            self.read_task.cancel()

    def __aiter__(self):
        self.is_running = True
        self.read_task = asyncio.create_task(self.read_ipcam_frames())
        return self

    async def __anext__(self):
        if not self.is_running:
            raise StopAsyncIteration

        def get_proc_frame():
            if not self.proc_frames.empty():
                return self.proc_frames.get_nowait()

        loop = asyncio.get_running_loop()
        processed_frame = await loop.run_in_executor(
            self._thread_executor, get_proc_frame
        )
        if processed_frame is not None and processed_frame.any():
            loop = asyncio.get_running_loop()
            _, encoded_frame = await loop.run_in_executor(
                None, lambda: cv2.imencode(".jpg", processed_frame)
            )
            return (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + encoded_frame.tobytes() + b"\r\n"
            )

    async def read_ipcam_frames(self):
        cap = cv2.VideoCapture(self.address)
        if not cap.isOpened():
            print(f"Error: Can't connect ipcam address (addr: {self.address})")
            return

        try:
            while self.is_running:
                await self._push_frame(cap)
                await asyncio.sleep(0)

        finally:
            cap.release()

    async def _push_frame(self, capture):
        loop = asyncio.get_running_loop()

        def _get_frame():
            nonlocal capture
            ret, frame = capture.read()
            if not ret:
                raise StopAsyncIteration

            yuv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            return yuv_frame

        frame = await loop.run_in_executor(self._thread_executor, _get_frame)

        def _push_frame_pipeline():
            nonlocal frame
            self.org_frames.put(frame)

        await loop.run_in_executor(self._thread_executor, _push_frame_pipeline)
```  
read_ipcam_frames 코루틴 내부적으로 코루틴을 호출하도록 수정해서 제어권을 놓을 수 있게 만들었습니다. 이렇게 수정하면 제어권을 놓는 순간 다른 코루틴이 동작하고 다른 코루틴이 제어권을 놓으면 다시 이후 작업들을 실행하는 형태로 동작하게 됩니다.

## 개선점
글을 쓰면서 제가 짠 로직에서의 문제점이 있다는 것을 깨달았습니다. 먼저 비디오 캡처는 CPU 집약적인 로직이라는 점입니다. 그래서 read_ipcam_frames 코드는 멀티 프로세싱으로 도는 것이 더 적합해보입니다. 그렇게 수정된다면 아예 다른 프로세스를 돌리기 때문에 다른 코어를 사용하고 제어권을 크게 신경쓰지 않아도 될것입니다.  
그리고 CPU 집약적인 코드는 제어권을 놓지 않기 때문에 코루틴으로 돌려도 크게 의미가 없는데 위에서 아마 pipeline에 프레임을 담는 과정에서 제어권을 놓았기에 동작할 수 있었지 않나 생각합니다.  
마지막으로 asyncio.sleep(0)으로 실행하게 된다면 지정된 시간만큼 sleep 하지 않고 적절한 시간만큼 sleep을 할 수 있게 구현할 수 있습니다.

## 마무리
위와 같은 문제 상황을 마주하면서 기존에 잘 이해가 되지도 않고 와닿지 않았던 blocking, non-blocking에 대해서 이해했고 동기, 비동기와의 차이점도 확실히 느꼈던 것 같습니다.
