"""Pruebas del motor de cumplimiento (3.6): logrado, tope, meta 0 y semáforo."""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from operaciones.calculos import (
    calcular_cumplimiento, logrado_por_item, puntaje_item, razon_logro, semaforo,
)
from operaciones.models import Activity,EmployeeFeedback, Evidence, Task
from portal.tests.helpers import ensure_roles, make_delegation, make_employee
from sgr_core.models import InstitutionalGoal, Period, Position, PositionItemGoal, ProjectItem
from django.core.exceptions import ValidationError

class FormulasTests(SimpleTestCase):
    def test_puntaje_proporcional(self):
        self.assertEqual(puntaje_item(razon_logro(45, 90), 25), Decimal("12.50"))

    def test_tope_de_120_por_ciento(self):
        self.assertEqual(puntaje_item(razon_logro(200, 90), 25), Decimal("30.00"))

    def test_meta_cero_cumple_si_hubo_algo(self):
        self.assertEqual(razon_logro(3, 0), Decimal("1"))
        self.assertEqual(razon_logro(0, 0), Decimal("0"))

    def test_semaforo(self):
        self.assertEqual(semaforo(Decimal("0.5"), Decimal("0.5")), "verde")
        self.assertEqual(semaforo(Decimal("0.35"), Decimal("0.5")), "amarillo")
        self.assertEqual(semaforo(Decimal("0.2"), Decimal("0.5")), "rojo")
        self.assertEqual(semaforo(Decimal("0"), Decimal("0")), "verde")


class CumplimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        roles = ensure_roles()
        delegacion = make_delegation("Centro", "DEL01", color="#C62828")
        cls.periodo = Period.objects.create(
            name="Trimestre Oct-Dic 2026",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), quarter=4,
        )
        cargo = Position.objects.create(code="CAR02", name="Gestor Social")
        cls.item_a = ProjectItem.objects.create(code="MTX01", name="Atención social")
        cls.item_b = ProjectItem.objects.create(code="MTX05", name="Emergencia")
        PositionItemGoal.objects.create(position=cargo, item=cls.item_a, period=cls.periodo, weight=80, target_value=10)
        PositionItemGoal.objects.create(position=cargo, item=cls.item_b, period=cls.periodo, weight=20, target_value=0)

        cls.ana = make_employee("ana", "10.000.001-1", delegacion, roles["ROL04"],
                                first_name="Ana", last_name="Pérez")
        cls.ana.position = cargo
        cls.ana.save()
        meta = InstitutionalGoal.objects.create(name="Meta", weight=100, period=cls.periodo, delegation=delegacion)
        cls.tarea = Task.objects.create(goal=meta, title="Tarea", due_date=date(2026, 12, 1), assigned_to=cls.ana)

    def actividad(self, dia, item, validada=True, estado=Activity.Status.DONE):
        act = Activity.objects.create(
            task=self.tarea, name="Act", execution_date=dia, status=estado, item=item,
        )
        Evidence.objects.create(activity=act, is_validated=validada)
        return act

    def test_solo_cuentan_actividades_realizadas_y_validadas(self):
        self.actividad(date(2026, 10, 5), self.item_a)
        self.actividad(date(2026, 10, 6), self.item_a, validada=False)
        self.actividad(date(2026, 10, 7), self.item_a, estado=Activity.Status.PENDING)
        Activity.objects.create(task=self.tarea, name="Sin ítem", execution_date=date(2026, 10, 8),
                                status=Activity.Status.DONE)
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {self.item_a.pk: 1})

    def test_maximo_siete_actividades_por_dia(self):
        for _ in range(9):
            self.actividad(date(2026, 10, 5), self.item_a)
        self.assertEqual(logrado_por_item(self.ana, self.periodo)[self.item_a.pk], 7)

    def test_actividades_fuera_del_trimestre_no_cuentan(self):
        self.actividad(date(2026, 9, 30), self.item_a)
        self.assertEqual(logrado_por_item(self.ana, self.periodo), {})

    def test_calculo_completo_con_meta_cero(self):
        for dia in range(5, 10):
            self.actividad(date(2026, 10, dia), self.item_a)   # 5 de 10 -> razón 0,5
        self.actividad(date(2026, 10, 12), self.item_b)        # emergencia: meta 0, cumple
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        por_item = {fila["item"].code: fila for fila in res["items"]}
        self.assertEqual(por_item["MTX01"]["puntaje"], Decimal("40.00"))
        self.assertEqual(por_item["MTX05"]["puntaje"], Decimal("20.00"))
        self.assertEqual(res["puntaje_total"], Decimal("60.00"))
        self.assertEqual(res["porcentaje"], Decimal("60.00"))
        self.assertEqual(res["semaforo"], "amarillo")

    def test_funcionario_sin_cargo_devuelve_resultado_vacio(self):
        sin_cargo = make_employee("sin", "10.000.009-9", self.ana.delegation, self.ana.role)
        res = calcular_cumplimiento(sin_cargo, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["items"], [])

    def feedback(self, tipo, dia, archivo=None):
        return EmployeeFeedback.objects.create(
            employee=self.ana, kind=tipo, date=dia, description="Prueba", file=archivo,
        )

    def cinco_actividades(self):
        for dia in range(5, 10):
            self.actividad(date(2026, 10, dia), self.item_a)   # 5 de 10 -> 40 puntos
        self.actividad(date(2026, 10, 12), self.item_b)        # emergencia -> 20 puntos

    def test_felicitacion_sin_respaldo_no_suma(self):
        self.feedback(EmployeeFeedback.Kind.PRAISE, date(2026, 11, 2))
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["felicitaciones"], 0)
        self.assertEqual(res["bonus"], Decimal("0"))

    def test_felicitaciones_con_respaldo_tienen_tope_de_tres(self):
        self.cinco_actividades()
        for dia in range(1, 6):
            self.feedback(EmployeeFeedback.Kind.PRAISE, date(2026, 11, dia), "respaldos/2026/11/aviso.pdf")
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["felicitaciones"], 5)
        self.assertEqual(res["bonus"], Decimal("30"))
        self.assertEqual(res["puntaje_total"], Decimal("90.00"))

    def test_reclamo_resta_puntaje(self):
        self.cinco_actividades()
        self.feedback(EmployeeFeedback.Kind.COMPLAINT, date(2026, 11, 3))
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["reclamos"], 1)
        self.assertEqual(res["puntaje_total"], Decimal("40.00"))

    def test_el_puntaje_no_baja_de_cero(self):
        self.feedback(EmployeeFeedback.Kind.COMPLAINT, date(2026, 11, 3))
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["puntaje_total"], Decimal("0.00"))

    def test_registros_fuera_del_trimestre_no_cuentan(self):
        self.feedback(EmployeeFeedback.Kind.COMPLAINT, date(2026, 9, 1))
        res = calcular_cumplimiento(self.ana, self.periodo, hoy=date(2026, 12, 31))
        self.assertEqual(res["reclamos"], 0)

    def test_felicitacion_sin_archivo_no_pasa_la_validacion(self):
        registro = EmployeeFeedback(
            employee=self.ana, kind=EmployeeFeedback.Kind.PRAISE,
            date=date(2026, 11, 2), description="Sin archivo",
        )
        with self.assertRaises(ValidationError):
            registro.clean()