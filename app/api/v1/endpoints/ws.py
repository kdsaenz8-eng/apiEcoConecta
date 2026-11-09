"""
Endpoint y Gestor de WebSockets en tiempo real para EcoConecta (app/api/v1/endpoints/ws.py).
Permite la actualización automática e instantánea del mapa de rutas, asignaciones y cambios de estado
sin necesidad de recargar la página.
"""
from typing import List
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSockets en Tiempo Real"])


class ConnectionManager:
    """Administra las conexiones activas de WebSockets para difusión de eventos en tiempo real."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        """Difunde un evento en formato JSON a todos los clientes conectados en tiempo real."""
        disconnected = []
        payload = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)
        for dead_conn in disconnected:
            self.disconnect(dead_conn)


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Canal bidireccional WebSocket para actualizaciones del mapa y solicitudes en vivo."""
    await ws_manager.connect(websocket)
    try:
        # Enviar mensaje de bienvenida y confirmación de enlace
        await websocket.send_text(json.dumps({
            "type": "CONNECTION_ESTABLISHED",
            "message": "Conectado al canal en tiempo real de EcoConecta",
            "municipality": "Antioquia"
        }))
        while True:
            data = await websocket.receive_text()
            # Si el cliente envía un evento o ping, se procesa o retransmite
            try:
                event_data = json.loads(data)
                if event_data.get("type") in ["PICKUP_CREATED", "PICKUP_ASSIGNED", "STATUS_CHANGED"]:
                    await ws_manager.broadcast(event_data)
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

