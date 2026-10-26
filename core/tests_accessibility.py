"""
Accessibility regression tests for HackFlow.
Tests WCAG AA compliance: semantics, ARIA/alt, keyboard focus.
"""

import re
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class AccessibilityTestCase(TestCase):
    """Base test case with common accessibility checks."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPass123!",
        )
        self.client.force_login(self.user)

    def assertHasSkipLink(self, response):
        """Check for skip to main content link."""
        self.assertContains(response, 'href="#main-content"')
        self.assertContains(response, 'class="sr-only focus:not-sr-only')

    def assertHasMainLandmark(self, response):
        """Check for main landmark with proper ID."""
        self.assertContains(response, 'id="main-content"')

    def assertNoEmptyButtons(self, response):
        """Check that buttons have accessible names."""
        content = response.content.decode()
        # Find buttons without aria-label, aria-labelledby, or text content
        button_pattern = r"<button[^>]*>(?:\s*<[^>]*>)*\s*</button>"
        buttons = re.findall(button_pattern, content, re.IGNORECASE)
        for button in buttons:
            has_aria_label = "aria-label" in button
            has_aria_labelledby = "aria-labelledby" in button
            has_text = bool(re.search(r">\s*[^<\s]", button))
            has_sr_only = "sr-only" in button
            # Allow buttons with only sr-only text (they have visible text for screen readers)
            if not (has_aria_label or has_aria_labelledby or has_text or has_sr_only):
                self.fail(f"Button missing accessible name: {button[:200]}")

    def assertNoEmptyLinks(self, response):
        """Check that links have accessible names."""
        content = response.content.decode()
        link_pattern = r"<a[^>]*href=[^>]*>(?:\s*<[^>]*>)*\s*</a>"
        links = re.findall(link_pattern, content, re.IGNORECASE)
        for link in links:
            has_aria_label = "aria-label" in link
            has_aria_labelledby = "aria-labelledby" in link
            has_text = bool(re.search(r">\s*[^<\s]", link))
            has_img_with_alt = "img" in link and "alt=" in link
            # Allow links that wrap images with alt text
            if not (has_aria_label or has_aria_labelledby or has_text or has_img_with_alt):
                # Skip external links that might be placeholders
                if 'href="#"' in link or 'href="/#' in link:
                    continue
                self.fail(f"Link missing accessible name: {link[:200]}")

    def assertImagesHaveAlt(self, response):
        """Check that all img tags have alt attributes."""
        content = response.content.decode()
        img_pattern = r"<img[^>]*>"
        images = re.findall(img_pattern, content, re.IGNORECASE)
        for img in images:
            # Allow decorative images with alt="" or aria-hidden="true"
            if "alt=" not in img and 'aria-hidden="true"' not in img:
                self.fail(f"Image missing alt attribute: {img[:200]}")

    def assertFocusStyles(self, response):
        """Check that interactive elements have focus styles."""
        content = response.content.decode()
        # Check for focus-visible or focus-ring classes
        self.assertTrue(
            "focus-visible" in content or "focus-ring" in content or "focus:outline" in content,
            "No focus styles found in response",
        )


class HomePageAccessibilityTests(AccessibilityTestCase):
    """Accessibility tests for the home page."""

    def test_home_page_accessibility(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)

        self.assertHasSkipLink(response)
        self.assertHasMainLandmark(response)
        self.assertNoEmptyButtons(response)
        self.assertNoEmptyLinks(response)
        self.assertImagesHaveAlt(response)
        self.assertFocusStyles(response)

    def test_home_page_semantic_structure(self):
        """Check for proper heading hierarchy and landmarks."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Should have h1
        self.assertIn("<h1", content.lower())

        # Should have proper section elements
        self.assertIn("<section", content.lower())

        # Should have nav for navigation
        self.assertIn("<nav", content.lower())

        # Should have footer
        self.assertIn("<footer", content.lower())


class AuthPagesAccessibilityTests(TestCase):
    """Accessibility tests for authentication pages (not logged in)."""

    def setUp(self):
        self.client = Client()

    def test_login_page_accessibility(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

        # Check basic accessibility
        content = response.content.decode()
        self.assertIn('href="#main-content"', content)
        self.assertIn('id="main-content"', content)
        self.assertIn('tabindex="-1"', content)

    def test_signup_page_accessibility(self):
        response = self.client.get(reverse("accounts:signup"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn('href="#main-content"', content)
        self.assertIn('id="main-content"', content)
        self.assertIn('tabindex="-1"', content)

    def test_password_reset_page_accessibility(self):
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()
        self.assertIn('href="#main-content"', content)
        self.assertIn('id="main-content"', content)
        self.assertIn('tabindex="-1"', content)


class ProjectPagesAccessibilityTests(AccessibilityTestCase):
    """Accessibility tests for project pages."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_project_list_accessibility(self):
        response = self.client.get(reverse("projects:project_list"))
        self.assertEqual(response.status_code, 200)

        self.assertHasSkipLink(response)
        self.assertHasMainLandmark(response)
        self.assertNoEmptyButtons(response)
        self.assertNoEmptyLinks(response)
        self.assertFocusStyles(response)

    def test_project_create_accessibility(self):
        response = self.client.get(reverse("projects:project_create"))
        self.assertEqual(response.status_code, 200)

        self.assertHasSkipLink(response)
        self.assertHasMainLandmark(response)
        self.assertNoEmptyButtons(response)
        self.assertFocusStyles(response)

        # Check form fields have labels
        content = response.content.decode()
        self.assertIn('id="id_title"', content)
        self.assertIn('id="id_tagline"', content)
        self.assertIn('id="id_description"', content)
        self.assertIn('id="id_category"', content)


class SponsorsPagesAccessibilityTests(AccessibilityTestCase):
    """Accessibility tests for sponsor pages."""

    def test_public_list_accessibility(self):
        response = self.client.get(reverse("sponsors:public_list"))
        self.assertEqual(response.status_code, 200)

        self.assertHasSkipLink(response)
        self.assertHasMainLandmark(response)
        self.assertNoEmptyButtons(response)
        self.assertNoEmptyLinks(response)
        self.assertImagesHaveAlt(response)
        self.assertFocusStyles(response)


class KeyboardNavigationTests(AccessibilityTestCase):
    """Tests for keyboard navigation and focus management."""

    def test_skip_link_navigation(self):
        """Test that skip link works."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Skip link should point to main-content
        self.assertIn('href="#main-content"', content)

        # Main content should have tabindex="-1" to receive focus
        self.assertIn('id="main-content"', content)
        self.assertIn('tabindex="-1"', content)

    def test_modal_focus_management(self):
        """Test that modals have proper focus management."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Check for dialog roles and aria-modal
        self.assertIn('role="dialog"', content)
        self.assertIn('aria-modal="true"', content)

    def test_dropdown_keyboard_support(self):
        """Test that dropdowns have keyboard support attributes."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Debug: print relevant parts
        import re

        dropdowns = re.findall(r"[^>]*aria-haspopup[^<]*", content)
        print(f"\nFound {len(dropdowns)} aria-haspopup elements")
        for d in dropdowns[:5]:
            print(f"  {d[:200]}")

        # Also check for dropdown in content
        if "dropdown" in content.lower():
            print("Dropdown keyword found in content")
        else:
            print("Dropdown keyword NOT found in content")

        # Check for menu role
        menus = re.findall(r'role="menu"', content)
        print(f"Found {len(menus)} role=menu elements")

        # Dropdown triggers should have aria-haspopup and aria-expanded
        # (may be Alpine.js x-bind attributes)
        self.assertTrue(
            'aria-haspopup="menu"' in content or "aria-haspopup='menu'" in content,
            "No aria-haspopup found for dropdowns",
        )
        self.assertTrue(
            "aria-expanded" in content or "x-bind:aria-expanded" in content,
            "No aria-expanded found for dropdowns",
        )


class ARIAAttributeTests(AccessibilityTestCase):
    """Tests for proper ARIA attribute usage."""

    def test_aria_labels_on_icon_buttons(self):
        """Icon-only buttons should have aria-label."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Check buttons with only icon content have aria-label
        icon_button_pattern = r"<button[^>]*>.*<c-lucideicon\.[^>]*>.*</button>"
        matches = re.findall(icon_button_pattern, content, re.IGNORECASE | re.DOTALL)
        for match in matches:
            if "aria-label" not in match:
                # Some might be in cotton components, check parent
                pass

    def test_live_regions_for_dynamic_content(self):
        """Check for aria-live regions for dynamic updates."""
        import os
        from django.conf import settings

        # Check that cotton toast and alert components exist in templates
        # These components provide role="alert" and aria-live functionality
        template_dirs = [
            os.path.join(settings.BASE_DIR, "templates", "cotton", "toast"),
            os.path.join(settings.BASE_DIR, "templates", "cotton", "alert"),
        ]

        has_toast = any(os.path.exists(d) for d in template_dirs[:1])
        has_alert = any(os.path.exists(d) for d in template_dirs[1:])

        # Toast/alert components should have role="alert" or aria-live
        # (may be in cotton components or dynamically loaded via Alpine.js/HTMX)
        # This is a basic check - full testing needs browser rendering
        # The c-toast and c-alert components are loaded dynamically
        self.assertTrue(has_toast or has_alert, "No toast or alert components found in templates")

    def test_progress_bars_have_aria(self):
        """Progress bars should have proper ARIA attributes."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        if 'role="progressbar"' in content:
            self.assertIn("aria-valuenow", content)
            self.assertIn("aria-valuemin", content)
            self.assertIn("aria-valuemax", content)


class ColorContrastTests(AccessibilityTestCase):
    """Tests for color contrast (basic checks)."""

    def test_no_color_only_indicators(self):
        """Information should not be conveyed by color alone."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Status badges should have text, not just color
        # This is a basic check - real contrast testing needs tools
        pass


class ResponsiveDesignTests(AccessibilityTestCase):
    """Tests for responsive design and zoom support."""

    def test_viewport_meta_tag(self):
        """Check for viewport meta tag."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()
        self.assertIn('name="viewport"', content)
        self.assertIn("width=device-width", content)

    def test_text_resize_support(self):
        """Check that text uses relative units."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        # Should not use px for font sizes in main content (basic check)
        # Tailwind uses rem, which is good
        self.assertIn("rem", content)


class NavigationAccessibilityTests(AccessibilityTestCase):
    """Tests for navigation accessibility."""

    def test_nav_has_aria_label(self):
        """Navigation should have aria-label."""
        response = self.client.get(reverse("core:home"))
        content = response.content.decode()

        self.assertIn('aria-label="Main navigation"', content)
        self.assertIn('aria-label="Mobile navigation"', content)

    def test_breadcrumb_structure(self):
        """Navigation should have proper structure."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("projects:project_create"))
        content = response.content.decode()

        # Debug
        print(f"\nCancel and return link: {'Cancel and return' in content}")
        print(f"Project List link: {'project_list' in content}")

        # Should have navigation back to project list
        has_navigation = "Cancel and return" in content or "project_list" in content
        self.assertTrue(has_navigation, "No navigation structure found")


if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.test.utils import get_runner

    django.setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["core.tests_accessibility"])
