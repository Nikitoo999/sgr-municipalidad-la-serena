"""Pruebas de tiempo real (Clase 11): consumers WebSocket y eventos."""
from unittest import mock

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from config.asgi import application
from operaciones.models import Neighbor
from portal.consumers import _user_can_access_delegation
from portal.tests.helpers import (
    DEMO_PASSWORD,
    TEST_STORAGES,
    ensure_roles,
    make_delegation,
    make_employee,
)
from sgr_core.models import AttentionSubtype, AttentionType


@override_settings(STORAGES=TEST_STORAGES)
class ConsumerAuthorizationHelperTests(TestCase):
    """La regla de ámbito del consumer se valida de forma aislada (síncrona)."""

    @classmethod
    def setUpTestData(cls):
        cls.roles = ensure_roles()
        cls.d1 = make_delegation("Centro", "DEL01")
        cls.d2 = make_delegation("La Antena", "DEL02")
        cls.coordinador = make_employee(
            "coordinador", "11.111.111-1", cls.d1, cls.roles["ROL02"],
        )
        cls.coordinador.authorized_delegations.set([cls.d1])
        cls.funcionario_b = make_employee(
            "funcionario_b", "11.111.113-3", cls.d2, cls.roles["ROL04"],
        )

    def test_regla_de_ambito(self):
        # Anónimo: sin acceso a ninguna sala.
        self.assertFalse(_user_can_access_delegation(AnonymousUser(), "DEL01"))
        # Coordinador autorizado a DEL01.
        self.assertTrue(_user_can_access_delegation(self.coordinador.user, "DEL01"))
        # Funcionario de DEL02 no puede escuchar DEL01 (aislamiento).
        self.assertFalse(_user_can_access_delegation(self.funcionario_b.user, "DEL01"))
        # Pero sí puede escuchar su propia delegación.
        self.assertTrue(_user_can_access_delegation(self.funcionario_b.user, "DEL02"))


class _RecordingLayer:
    """Channel layer de mentira que registra las llamadas a ``group_send``."""

    def __init__(self):
        self.calls = []

    async def group_send(self, group, message):
        self.calls.append((group, message))


@override_settings(STORAGES=TEST_STORAGES)
class DelegationChatConsumerTests(TransactionTestCase):
    def setUp(self):
        self.roles = ensure_roles()
        self.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        self.d2 = make_delegation("La Antena", "DEL02", color="#2E7D32")
        self.coordinador = make_employee(
            "coordinador", "11.111.111-1", self.d1, self.roles["ROL02"],
        )
        self.coordinador.authorized_delegations.set([self.d1])
        self.funcionario_b = make_employee(
            "funcionario_b", "11.111.113-3", self.d2, self.roles["ROL04"],
        )

    def _communicator(self, path, user):
        communicator = WebsocketCommunicator(
            application, path, headers=[(b"origin", b"http://localhost")],
        )
        # El usuario se inyecta en el scope: la autorización la decide el
        # consumer en el servidor (nunca el cliente elige libremente la sala).
        communicator.scope["user"] = user
        return communicator

    def test_anonimo_rechazado(self):
        async_to_sync(self._run_anonimo)()

    async def _run_anonimo(self):
        communicator = self._communicator("/ws/chat/DEL01/", AnonymousUser())
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_lector_b_no_escucha_delegacion_ajena(self):
        async_to_sync(self._run_ajeno)()

    async def _run_ajeno(self):
        # funcionario_b pertenece a DEL02: no puede escuchar el chat de DEL01.
        communicator = self._communicator("/ws/chat/DEL01/", self.funcionario_b.user)
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_chat_connect_and_broadcast(self):
        async_to_sync(self._run)()

    async def _run(self):
        communicator = self._communicator("/ws/chat/DEL01/", self.coordinador.user)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_json_to({"message": "hola"})
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(response["type"], "chat")
        self.assertEqual(response["message"], "hola")
        self.assertEqual(response["user"], "coordinador")
        self.assertIn("timestamp", response)
        await communicator.disconnect()


@override_settings(STORAGES=TEST_STORAGES)
class AttentionLiveConsumerTests(TransactionTestCase):
    def setUp(self):
        self.roles = ensure_roles()
        self.d1 = make_delegation("Centro", "DEL01", color="#C62828")
        self.d2 = make_delegation("La Antena", "DEL02", color="#2E7D32")
        self.coordinador = make_employee(
            "coordinador", "11.111.111-1", self.d1, self.roles["ROL02"],
        )
        self.coordinador.authorized_delegations.set([self.d1])
        self.funcionario_b = make_employee(
            "funcionario_b", "11.111.113-3", self.d2, self.roles["ROL04"],
        )

    def _communicator(self, path, user):
        communicator = WebsocketCommunicator(
            application, path, headers=[(b"origin", b"http://localhost")],
        )
        communicator.scope["user"] = user
        return communicator

    def test_anonimo_rechazado(self):
        async_to_sync(self._run_anonimo)()

    async def _run_anonimo(self):
        communicator = self._communicator("/ws/atenciones/DEL01/", AnonymousUser())
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_lector_b_no_escucha_delegacion_ajena(self):
        async_to_sync(self._run_ajeno)()

    async def _run_ajeno(self):
        communicator = self._communicator("/ws/atenciones/DEL01/", self.funcionario_b.user)
        connected, _ = await communicator.connect()
        self.assertFalse(connected)

    def test_attention_consumer_connect(self):
        async_to_sync(self._run)()

    async def _run(self):
        communicator = self._communicator("/ws/atenciones/DEL01/", self.coordinador.user)
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
            # La emisión viaja dentro de transaction.on_commit: se capturan los
            # callbacks y se ejecutan al salir del bloque para poder validarlos.
            with self.captureOnCommitCallbacks(execute=True):
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
            "neighbor_rut": self.vecino.identifier,
            "neighbor_name": self.vecino.full_name,
            "neighbor_phone": "+56 9 1111 1111",
            "delegation": str(self.d1.pk),
            "attention_type": str(self.tipo.pk),
            "attention_subtype": str(self.sub.pk),
            "description": "Descripción válida de la atención ingresada.",
        }
