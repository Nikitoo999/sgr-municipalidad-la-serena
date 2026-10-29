"""Pruebas de tiempo real (Clase 11): consumers WebSocket y eventos."""
from unittest import mock

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from config.asgi import application
from operaciones.models import Neighbor
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
)
from sgr_core.models import AttentionSubtype, AttentionType


class _RecordingLayer:
    """Channel layer de mentira que registra las llamadas a ``group_send``."""

    def __init__(self):
        self.calls = []

    async def group_send(self, group, message):
        self.calls.append((group, message))


@override_settings(STORAGES=TEST_STORAGES)
class DelegationChatConsumerTests(TransactionTestCase):
    def test_chat_connect_and_broadcast(self):
        async_to_sync(self._run)()

    async def _run(self):
        communicator = WebsocketCommunicator(
            application, "/ws/chat/DEL01/",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_json_to({"message": "hola"})
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(response["type"], "chat")
        self.assertEqual(response["message"], "hola")
        self.assertEqual(response["user"], "Anónimo")
        self.assertIn("timestamp", response)
        await communicator.disconnect()


@override_settings(STORAGES=TEST_STORAGES)
class AttentionLiveConsumerTests(TransactionTestCase):
    def test_attention_consumer_connect(self):
        async_to_sync(self._run)()

    async def _run(self):
        communicator = WebsocketCommunicator(
            application, "/ws/atenciones/DEL01/",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()


@override_settings(STORAGES=TEST_STORAGES)
class AttentionEventEmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coordinador.authorized_delegations.set([cls.d1])
        cls.tipo = AttentionType.objects.create(code="TAT01", name="Social")
        cls.sub = AttentionSubtype.objects.create(
            code="SAT01", name="Ayuda social", attention_type=cls.tipo,
        )
        cls.vecino = Neighbor.objects.create(
            identifier="11.111.111-1", full_name="María González",
        )

    def test_attention_create_emits_event(self):
        layer = _RecordingLayer()
        with mock.patch("portal.crud.attentions.get_channel_layer", return_value=layer):
            self.client.login(username="coordinador", password=DEMO_PASSWORD)
            resp = self.client.post(reverse("attentions_new"), self._post_data())
            self.assertEqual(resp.status_code, 302)

        groups = {group for group, _ in layer.calls}
        self.assertIn("atenciones_DEL01", groups)
        self.assertIn("atenciones_ALL", groups)

        for _group, payload in layer.calls:
            self.assertEqual(payload["type"], "attention_created")
            self.assertIn("ATN-", payload["number"])
            self.assertEqual(payload["solicitante"], "María González")
            self.assertIn("fecha", payload)

    def _post_data(self):
        return {
            "neighbor": str(self.vecino.pk),
            "delegation": str(self.d1.pk),
            "attention_type": str(self.tipo.pk),
            "attention_subtype": str(self.sub.pk),
            "description": "Descripción válida de la atención ingresada.",
        }
