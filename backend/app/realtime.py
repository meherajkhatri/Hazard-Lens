import asyncio

from fastapi import WebSocket


class EventHub:
    def __init__(self):
        self.clients: dict[WebSocket, asyncio.Queue] = {}

    def subscribe(self, socket):
        queue = asyncio.Queue(maxsize=100)
        self.clients[socket] = queue
        return queue

    def unsubscribe(self, socket):
        self.clients.pop(socket, None)

    async def publish(self, event):
        for socket, queue in list(self.clients.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self.unsubscribe(socket)
                # A slow dashboard must reconnect and refresh incidents over REST.
                try:
                    await asyncio.wait_for(socket.close(code=1013), timeout=1)
                except (RuntimeError, TimeoutError):
                    pass
