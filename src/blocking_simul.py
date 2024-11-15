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


if __name__ == "__main__":
    IPCAM_ADDR = "rtsp://dudaji:Enekwl2022!@dudajicam.iptimecam.com:21168/stream_ch00_0"
