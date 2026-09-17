import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from kanban.models import Board, Task

MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA)
class AnexosTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.a = Tenant.objects.create(name="Alfa", slug="alfa-anx")
        self.b = Tenant.objects.create(name="Beta", slug="beta-anx")
        self.ana = User.objects.create_user("ana@anx.com", "x", tenant=self.a, role=User.Role.COLABORADOR)
        self.bia = User.objects.create_user("bia@anx.com", "x", tenant=self.b, role=User.Role.ADMIN)
        self.task = Task.objects.create(board=Board.objects.create(tenant=self.a, name="B"), title="T")
        self.client.force_authenticate(self.ana)

    def _enviar(self, nome="contrato.pdf", conteudo=b"%PDF-1.4 teste", **extra):
        corpo = {"kind": "kanban_task", "object_id": self.task.id, "file": SimpleUploadedFile(nome, conteudo), **extra}
        return self.client.post("/api/anexos/", corpo, format="multipart")

    def test_envia_lista_baixa_e_exclui(self):
        r = self._enviar()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.json()["name"], r.json()["size"]), ("contrato.pdf", 14))
        lista = self.client.get(f"/api/anexos/?kind=kanban_task&object_id={self.task.id}").json()
        self.assertEqual(len(lista), 1)
        d = self.client.get(f"/api/anexos/{lista[0]['id']}/download/")
        self.assertEqual((d.status_code, b"".join(d.streaming_content)), (200, b"%PDF-1.4 teste"))
        self.assertIn("attachment", d["Content-Disposition"])
        self.assertEqual(self.client.delete(f"/api/anexos/{lista[0]['id']}/").status_code, 204)

    def test_recusa_executavel_alvo_de_outra_empresa_e_nao_vaza(self):
        self.assertEqual(self._enviar(nome="virus.exe").status_code, 400)
        self.assertEqual(self._enviar(kind="nada").status_code, 400)
        anexo = self._enviar().json()["id"]
        self.client.force_authenticate(self.bia)
        self.assertEqual(self.client.get(f"/api/anexos/{anexo}/download/").status_code, 404)
        self.assertEqual(self._enviar().status_code, 400)        # tarefa é da Alfa
