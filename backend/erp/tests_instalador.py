from rest_framework.test import APITestCase

from accounts.models import Tenant, User

from .models import Connector


class InstaladorTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Nordeste Boi", slug="nordesteboi")
        self.root = User.objects.create_user("root@t.com", "x", first_name="Root", role=User.Role.ROOT)
        self.admin = User.objects.create_user("a@nb.com", "x", first_name="A", tenant=self.tenant, role=User.Role.ADMIN)

    def test_so_root_acessa(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/erp/instalador/?tenant={self.tenant.id}").status_code, 403)

    def test_escolher_empresa_cria_conector_e_devolve_scripts(self):
        self.client.force_authenticate(self.root)
        self.assertFalse(Connector.objects.filter(tenant=self.tenant).exists())

        r = self.client.get(f"/api/erp/instalador/?tenant={self.tenant.id}")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        conn = Connector.objects.get(tenant=self.tenant)
        self.assertEqual(d["token"], conn.ingest_token)
        self.assertIn(conn.ingest_token, d["linux"]["oneliner"])
        self.assertTrue(d["linux"]["script_url"].endswith(f"/api/coletor/instalar/{conn.ingest_token}.sh"))
        self.assertEqual(d["linux"]["script_name"], "instalar-nordesteboi.sh")
        self.assertIn("GRANT SELECT", d["dba_script"])

        # Chamar de novo reaproveita o mesmo conector (não duplica).
        self.client.get(f"/api/erp/instalador/?tenant={self.tenant.id}")
        self.assertEqual(Connector.objects.filter(tenant=self.tenant).count(), 1)

    def test_script_pronto_embute_servidor_e_chave(self):
        self.client.force_authenticate(self.root)
        token = self.client.get(f"/api/erp/instalador/?tenant={self.tenant.id}").json()["token"]

        self.client.force_authenticate(None)
        r = self.client.get(f"/api/coletor/instalar/{token}.sh")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertTrue(body.startswith("#!/usr/bin/env bash"))
        self.assertIn(f"--key '{token}'", body)
        self.assertIn('attachment; filename="instalar-nordesteboi.sh"', r["Content-Disposition"])

        r = self.client.get(f"/api/coletor/instalar/{token}.ps1")
        self.assertEqual(r.status_code, 200)
        self.assertIn(f'[string]$Key = "{token}"', r.content.decode())

    def test_script_pronto_com_chave_invalida_e_403(self):
        self.assertEqual(self.client.get("/api/coletor/instalar/nao-existe.sh").status_code, 403)

    def test_nova_chave_invalida_a_anterior(self):
        self.client.force_authenticate(self.root)
        antiga = self.client.get(f"/api/erp/instalador/?tenant={self.tenant.id}").json()["token"]
        nova = self.client.post("/api/erp/instalador/", {"tenant": self.tenant.id}).json()["token"]
        self.assertNotEqual(antiga, nova)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/coletor/instalar/{antiga}.sh").status_code, 403)
        self.assertEqual(self.client.get(f"/api/coletor/instalar/{nova}.sh").status_code, 200)
