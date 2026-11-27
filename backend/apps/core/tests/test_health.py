from django.test import TestCase


class HealthTest(TestCase):
    def test_health_ok(self):
        r = self.client.get("/api/health/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["database"], "ok")
