from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from . import services
from .forms import JoinTeamForm, TeamForm
from .models import Hackathon, SkillProfile, Team, TeamMember

User = get_user_model()

@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BaseTeamTestCase(TestCase):
    password = "S3curePassw0rd!"

    def setUp(self):
        self.leader = User.objects.create_user("leader", "leader@example.com", self.password)
        self.member = User.objects.create_user("member", "member@example.com", self.password)
        self.outsider = User.objects.create_user("outsider", "outsider@example.com", self.password)
        self.hackathon = Hackathon.objects.create(
            title="Hack Tunis", start_date=date(2026, 12, 1), end_date=date(2026, 12, 3)
        )
        self.team = services.create_team(
            leader=self.leader,
            name="Alpha Team",
            description="Une équipe de test",
            hackathon=self.hackathon,
            max_members=4,
        )

    def login(self, user):
        self.client.force_login(user)


# ---------------------------------------------------------------- Modèles
class ModelTests(BaseTeamTestCase):
    def test_str(self):
        self.assertEqual(str(self.team), "Alpha Team (Hack Tunis)")

    def test_leader_is_first_member(self):
        membership = self.team.members.get(user=self.leader)
        self.assertEqual(membership.role, TeamMember.Role.LEADER)

    def test_unique_team_name_per_hackathon(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Team.objects.create(
                name="Alpha Team", hackathon=self.hackathon, leader=self.member
            )

    def test_unique_member_per_team(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TeamMember.objects.create(team=self.team, user=self.leader)

    def test_name_min_length_validator(self):
        team = Team(name="ab", hackathon=self.hackathon, leader=self.leader, max_members=4)
        with self.assertRaises(ValidationError) as ctx:
            team.full_clean()
        self.assertIn("name", ctx.exception.message_dict)

    def test_max_members_bounds(self):
        for bad in (1, 7):
            team = Team(name="Bounds", hackathon=self.hackathon, leader=self.leader, max_members=bad)
            with self.assertRaises(ValidationError):
                team.full_clean()

    def test_is_full(self):
        team = services.create_team(
            leader=self.member, name="Small", description="", hackathon=Hackathon.objects.create(
                title="Autre", start_date=date(2026, 12, 5), end_date=date(2026, 12, 6)
            ), max_members=2,
        )
        self.assertFalse(team.is_full)
        TeamMember.objects.create(team=team, user=self.outsider)
        self.assertTrue(team.is_full)


# --------------------------------------------------------------- Services
class ServiceTests(BaseTeamTestCase):
    def test_join_team(self):
        services.join_team(team=self.team, user=self.member, role="backend", skills="python")
        self.assertTrue(self.team.members.filter(user=self.member).exists())

    def test_join_twice_fails(self):
        services.join_team(team=self.team, user=self.member, role="backend")
        with self.assertRaises(services.TeamError):
            services.join_team(team=self.team, user=self.member, role="backend")

    def test_join_full_team_fails(self):
        self.team.max_members = 2
        self.team.save()
        services.join_team(team=self.team, user=self.member, role="backend")
        with self.assertRaises(services.TeamError):
            services.join_team(team=self.team, user=self.outsider, role="frontend")

    def test_one_team_per_hackathon(self):
        other = services.create_team(
            leader=self.member, name="Beta Team", description="",
            hackathon=self.hackathon, max_members=4,
        )
        with self.assertRaises(services.TeamError):
            services.join_team(team=self.team, user=self.member, role="backend")
        self.assertEqual(other.members.count(), 1)

    def test_leader_cannot_create_second_team_same_hackathon(self):
        with self.assertRaises(services.TeamError):
            services.create_team(
                leader=self.leader, name="Gamma", description="",
                hackathon=self.hackathon, max_members=4,
            )

    def test_leader_cannot_leave(self):
        with self.assertRaises(services.TeamError):
            services.leave_team(team=self.team, user=self.leader)

    def test_leave_team(self):
        services.join_team(team=self.team, user=self.member, role="backend")
        services.leave_team(team=self.team, user=self.member)
        self.assertFalse(self.team.members.filter(user=self.member).exists())

    def test_leave_when_not_member_fails(self):
        with self.assertRaises(services.TeamError):
            services.leave_team(team=self.team, user=self.outsider)


# ----------------------------------------------------------------- Forms
class FormTests(BaseTeamTestCase):
    def test_max_members_cannot_go_below_current_members(self):
        services.join_team(team=self.team, user=self.member, role="backend")
        services.join_team(team=self.team, user=self.outsider, role="frontend")
        form = TeamForm(
            data={"name": "Alpha Team", "description": "", "hackathon": self.hackathon.pk, "max_members": 2},
            instance=self.team,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("max_members", form.errors)

    def test_join_form_excludes_leader_role(self):
        values = [value for value, _ in JoinTeamForm().fields["role"].choices]
        self.assertNotIn(TeamMember.Role.LEADER, values)

    def test_join_form_rejects_leader_role(self):
        form = JoinTeamForm(data={"role": "leader", "skills": ""})
        self.assertFalse(form.is_valid())


# ------------------------------------------------- Vues publiques (lecture)
class PublicViewTests(BaseTeamTestCase):
    def test_list_is_public(self):
        response = self.client.get(reverse("teams:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Team")

    def test_detail_is_public(self):
        response = self.client.get(reverse("teams:detail", args=[self.team.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Team")

    def test_detail_unknown_team_is_404(self):
        response = self.client.get(reverse("teams:detail", args=[9999]))
        self.assertEqual(response.status_code, 404)

    def test_search_filters_results(self):
        services.create_team(
            leader=self.member, name="Zeta Squad", description="",
            hackathon=Hackathon.objects.create(
                title="Autre", start_date=date(2026, 12, 5), end_date=date(2026, 12, 6)
            ), max_members=4,
        )
        response = self.client.get(reverse("teams:list"), {"q": "Zeta"})
        self.assertContains(response, "Zeta Squad")
        self.assertNotContains(response, "Alpha Team")

    def test_filter_by_hackathon(self):
        response = self.client.get(reverse("teams:list"), {"hackathon": self.hackathon.pk})
        self.assertContains(response, "Alpha Team")


# -------------------------------------------- Permissions (accès restreint)
class PermissionTests(BaseTeamTestCase):
    def assertRedirectsToLogin(self, response, url):
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False
        )

    def test_anonymous_cannot_open_create(self):
        url = reverse("teams:create")
        self.assertRedirectsToLogin(self.client.get(url), url)

    def test_anonymous_cannot_post_create(self):
        url = reverse("teams:create")
        response = self.client.post(url, {"name": "Hack", "hackathon": self.hackathon.pk, "max_members": 4})
        self.assertRedirectsToLogin(response, url)
        self.assertEqual(Team.objects.count(), 1)

    def test_anonymous_cannot_update(self):
        url = reverse("teams:update", args=[self.team.pk])
        self.assertRedirectsToLogin(self.client.get(url), url)

    def test_anonymous_cannot_delete(self):
        url = reverse("teams:delete", args=[self.team.pk])
        self.assertRedirectsToLogin(self.client.post(url), url)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_non_leader_gets_403_on_update_get(self):
        self.login(self.outsider)
        response = self.client.get(reverse("teams:update", args=[self.team.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_leader_cannot_update_via_post(self):
        self.login(self.outsider)
        response = self.client.post(
            reverse("teams:update", args=[self.team.pk]),
            {"name": "Hacked", "description": "", "hackathon": self.hackathon.pk, "max_members": 4},
        )
        self.assertEqual(response.status_code, 403)
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Alpha Team")

    def test_non_leader_gets_403_on_delete(self):
        self.login(self.outsider)
        response = self.client.post(reverse("teams:delete", args=[self.team.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_regular_member_cannot_edit_or_delete(self):
        services.join_team(team=self.team, user=self.member, role="backend")
        self.login(self.member)
        self.assertEqual(self.client.get(reverse("teams:update", args=[self.team.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("teams:delete", args=[self.team.pk])).status_code, 403)

    def test_anonymous_cannot_join(self):
        url = reverse("teams:join", args=[self.team.pk])
        self.assertRedirectsToLogin(self.client.post(url, {"role": "backend"}), url)
        self.assertEqual(self.team.members.count(), 1)

    def test_anonymous_cannot_leave(self):
        url = reverse("teams:leave", args=[self.team.pk])
        self.assertRedirectsToLogin(self.client.post(url), url)

    def test_join_requires_post(self):
        self.login(self.member)
        response = self.client.get(reverse("teams:join", args=[self.team.pk]))
        self.assertEqual(response.status_code, 405)

    def test_leave_requires_post(self):
        self.login(self.member)
        response = self.client.get(reverse("teams:leave", args=[self.team.pk]))
        self.assertEqual(response.status_code, 405)


# ------------------------------------------------------------ CRUD (leader)
class CrudTests(BaseTeamTestCase):
    def test_create_team(self):
        self.login(self.member)
        response = self.client.post(
            reverse("teams:create"),
            {"name": "Beta Team", "description": "Desc", "hackathon": self.hackathon.pk, "max_members": 3},
        )
        team = Team.objects.get(name="Beta Team")
        self.assertRedirects(response, reverse("teams:detail", args=[team.pk]))
        self.assertEqual(team.leader, self.member)
        self.assertTrue(team.members.filter(user=self.member, role="leader").exists())

    def test_create_with_invalid_data_shows_errors(self):
        self.login(self.member)
        response = self.client.post(
            reverse("teams:create"),
            {"name": "ab", "description": "", "hackathon": self.hackathon.pk, "max_members": 4},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "name", "Le nom doit contenir au moins 3 caractères.")

    def test_create_second_team_same_hackathon_is_rejected(self):
        self.login(self.leader)
        response = self.client.post(
            reverse("teams:create"),
            {"name": "Another", "description": "", "hackathon": self.hackathon.pk, "max_members": 4},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Team.objects.count(), 1)

    def test_leader_can_update(self):
        self.login(self.leader)
        response = self.client.post(
            reverse("teams:update", args=[self.team.pk]),
            {"name": "Alpha Renamed", "description": "Nouvelle", "hackathon": self.hackathon.pk, "max_members": 5},
        )
        self.assertRedirects(response, reverse("teams:detail", args=[self.team.pk]))
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Alpha Renamed")
        self.assertEqual(self.team.max_members, 5)

    def test_leader_can_delete(self):
        self.login(self.leader)
        response = self.client.post(reverse("teams:delete", args=[self.team.pk]))
        self.assertRedirects(response, reverse("teams:list"))
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())
        self.assertEqual(TeamMember.objects.count(), 0)  # cascade

    def test_join_and_leave_via_views(self):
        self.login(self.member)
        self.client.post(reverse("teams:join", args=[self.team.pk]), {"role": "backend", "skills": "django"})
        self.assertTrue(self.team.members.filter(user=self.member, skills="django").exists())
        self.client.post(reverse("teams:leave", args=[self.team.pk]))
        self.assertFalse(self.team.members.filter(user=self.member).exists())

    def test_join_full_team_via_view_is_rejected(self):
        self.team.max_members = 2
        self.team.save()
        services.join_team(team=self.team, user=self.member, role="backend")
        self.login(self.outsider)
        self.client.post(reverse("teams:join", args=[self.team.pk]), {"role": "frontend"})
        self.assertFalse(self.team.members.filter(user=self.outsider).exists())

    def test_cannot_join_as_leader_role_via_post(self):
        self.login(self.member)
        self.client.post(reverse("teams:join", args=[self.team.pk]), {"role": "leader"})
        self.assertFalse(self.team.members.filter(user=self.member).exists())

    def test_csrf_is_enforced(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.leader)
        response = client.post(reverse("teams:delete", args=[self.team.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())



class MatchingTests(BaseTeamTestCase):
    def setUp(self):
        super().setUp()
        SkillProfile.objects.create(user=self.leader, main_role="backend", skills="python, django")
        self.designer = User.objects.create_user("designer", "d@example.com", self.password)
        self.designer_profile = SkillProfile.objects.create(
            user=self.designer, main_role="designer", skills="figma, ui"
        )
        self.backend2 = User.objects.create_user("backend2", "b2@example.com", self.password)
        SkillProfile.objects.create(user=self.backend2, main_role="backend", skills="python, django")

    def test_parse_skills_normalizes_and_deduplicates(self):
        self.assertEqual(services.parse_skills(" Python, django ,python,, "), ["python", "django"])
        self.assertEqual(services.parse_skills(""), [])

    def test_role_fit_beats_skill_novelty(self):
        role_score, _ = services.score_candidate(
            role="designer", skills=[], missing_roles=["designer"], team_skills=set()
        )
        skill_score, _ = services.score_candidate(
            role="backend", skills=["a", "b", "c", "d"], missing_roles=["designer"], team_skills=set()
        )
        self.assertGreater(role_score, skill_score)

    def test_analyze_team_uses_leader_profile_role(self):
        analysis = services.analyze_team(self.team)
        self.assertIn("backend", analysis["roles"])
        self.assertEqual(set(analysis["missing_roles"]), {"frontend", "designer", "data"})

    def test_missing_role_candidate_ranked_first(self):
        _, results = services.suggest_candidates(self.team)
        self.assertEqual(results[0]["user"], self.designer)

    def test_redundant_candidate_is_not_suggested(self):
        _, results = services.suggest_candidates(self.team)
        self.assertNotIn(self.backend2, [r["user"] for r in results])

    def test_user_already_in_a_team_is_excluded(self):
        services.join_team(team=self.team, user=self.designer, role="designer")
        _, results = services.suggest_candidates(self.team)
        self.assertNotIn(self.designer, [r["user"] for r in results])

    def test_user_not_looking_for_team_is_excluded(self):
        self.designer_profile.looking_for_team = False
        self.designer_profile.save()
        _, results = services.suggest_candidates(self.team)
        self.assertNotIn(self.designer, [r["user"] for r in results])