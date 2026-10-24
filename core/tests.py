from django.test import SimpleTestCase


class HomePageTests(SimpleTestCase):
    def test_home_page_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HackFlow")
        self.assertContains(response, "Neon Nights 2026")
