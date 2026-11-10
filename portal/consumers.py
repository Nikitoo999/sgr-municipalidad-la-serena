"""Consumers de WebSocket (Clase 11: tiempo real).

- ``DelegationChatConsumer``: chat por delegación, difunde mensajes con
  fecha/hora y usuario emisor.
- ``AttentionLiveConsumer``: avisos en vivo de nuevas atenciones por delegación.
"""
from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from portal.access import allowed_delegations, get_role


def _user_can_access_delegation(user, delegation_code):
    """True si el usuario autenticado puede escuchar la sala de esa delegación.

    La decisión vive en el servidor: un usuario anónimo o que no pertenece al
    ámbito de la sala nunca puede suscribirse a eventos ajenos (p. ej. un Lector
    B no puede escuchar la delegación de un Lector A).
    """
    if user is None or not user.is_authenticated:
        return False
    role = get_role(user)
    if role is None:
        return False
    if role.scope == "all":
        return True
    return delegation_code in {d.code for d in allowed_delegations(user)}


class DelegationChatConsumer(AsyncJsonWebsocketConsumer):
    """Chat de la delegación activa."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.delegation_code = self.scope['url_route']['kwargs']['delegation_code']
        if not await database_sync_to_async(_user_can_access_delegation)(user, self.delegation_code):
            await self.close()
            return
        self.room_group_name = f'chat_{self.delegation_code}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message = (content.get('message') or '').strip()
        if not message:
            return
        user = self.scope.get('user')
        username = user.username if user and user.is_authenticated else 'Anónimo'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'user': username,
            },
        )

    async def chat_message(self, event):
        await self.send_json({
            'type': 'chat',
            'user': event.get('user', ''),
            'message': event.get('message', ''),
            'timestamp': timezone.now().strftime('%d-%m-%Y %H:%M'),
        })


class AttentionLiveConsumer(AsyncJsonWebsocketConsumer):
    """Avisos en vivo de nuevas atenciones para una delegación."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.delegation_code = self.scope['url_route']['kwargs']['delegation_code']
        if not await database_sync_to_async(_user_can_access_delegation)(user, self.delegation_code):
            await self.close()
            return
        self.room_group_name = f'atenciones_{self.delegation_code}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def attention_created(self, event):
        await self.send_json({
            'type': 'attention_created',
            'id': event.get('id', ''),
            'number': event.get('number', ''),
            'solicitante': event.get('solicitante', ''),
            'fecha': event.get('fecha', ''),
            'tipo': event.get('tipo', ''),
            'subtipo': event.get('subtipo', ''),
            'delegation': event.get('delegation', ''),
            'delegation_color': event.get('delegation_color', ''),
            'responsable': event.get('responsable', ''),
            'estado': event.get('estado', ''),
            'action': event.get('action', ''),
        })
