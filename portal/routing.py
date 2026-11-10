"""Rutas WebSocket del portal (Clase 11: tiempo real)."""
from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/chat/<str:delegation_code>/', consumers.DelegationChatConsumer.as_asgi()),
    path('ws/atenciones/<str:delegation_code>/', consumers.AttentionLiveConsumer.as_asgi()),
]
