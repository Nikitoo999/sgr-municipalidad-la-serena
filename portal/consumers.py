"""Consumers de WebSocket (Clase 11: tiempo real).

- ``DelegationChatConsumer``: chat por delegación, difunde mensajes con
  fecha/hora y usuario emisor.
- ``AttentionLiveConsumer``: avisos en vivo de nuevas atenciones por delegación.
"""
from django.utils import timezone

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class DelegationChatConsumer(AsyncJsonWebsocketConsumer):
    """Chat de la delegación activa."""

    async def connect(self):
        self.delegation_code = self.scope['url_route']['kwargs']['delegation_code']
        self.room_group_name = f'chat_{self.delegation_code}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
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
        self.delegation_code = self.scope['url_route']['kwargs']['delegation_code']
        self.room_group_name = f'atenciones_{self.delegation_code}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
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
