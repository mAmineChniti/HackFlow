from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase, Client
from django.utils import timezone

from accounts.models import Profile
from projects.models import Project, ProjectMember, ConseilMentor
from projects.forms import ProjectForm
from projects import services

User = get_user_model()


class ProjectPermissionsTestCase(TestCase):
    def setUp(self):
        # 1. Comptes avec rôles globaux
        self.admin_user = User.objects.create_user(
            username="admin_test", email="admin@test.com", password="pwd", is_superuser=True, is_staff=True
        )
        self.admin_user.profile.role = Profile.Role.ADMIN
        self.admin_user.profile.save()

        self.organizer_user = User.objects.create_user(
            username="organizer_test", email="org@test.com", password="pwd", is_staff=True
        )
        self.organizer_user.profile.role = Profile.Role.ORGANIZER
        self.organizer_user.profile.save()

        self.judge_user = User.objects.create_user(
            username="judge_test", email="judge@test.com", password="pwd"
        )
        self.judge_user.profile.role = Profile.Role.JUDGE
        self.judge_user.profile.save()

        self.mentor_user = User.objects.create_user(
            username="mentor_test", email="mentor@test.com", password="pwd"
        )
        self.mentor_user.profile.role = Profile.Role.MENTOR
        self.mentor_user.profile.save()

        self.student_lead = User.objects.create_user(
            username="student_lead", email="lead@test.com", password="pwd"
        )
        self.student_lead.profile.role = Profile.Role.STUDENT
        self.student_lead.profile.save()

        self.student_dev = User.objects.create_user(
            username="student_dev", email="dev@test.com", password="pwd"
        )
        self.student_dev.profile.role = Profile.Role.STUDENT
        self.student_dev.profile.save()

        self.student_other = User.objects.create_user(
            username="student_other", email="other@test.com", password="pwd"
        )
        self.student_other.profile.role = Profile.Role.STUDENT
        self.student_other.profile.save()

        # 2. Projet test (brouillon au départ)
        self.project_draft = Project.objects.create(
            title="Projet IA Test",
            tagline="Solution IA",
            description="Description détaillée",
            created_by=self.student_lead,
            status=Project.Status.DRAFT,
            deadline=timezone.now() + timedelta(days=2),
        )
        # Créateur devient chef_de_projet
        ProjectMember.objects.create(
            project=self.project_draft,
            user=self.student_lead,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )
        # Membre développeur
        ProjectMember.objects.create(
            project=self.project_draft,
            user=self.student_dev,
            role=ProjectMember.Role.DEVELOPPEUR,
        )

        # Projet validé (status = accepted)
        self.project_accepted = Project.objects.create(
            title="Projet Validé",
            tagline="Solution validée",
            description="Description validée",
            created_by=self.student_lead,
            status=Project.Status.ACCEPTED,
        )

        # Projet soumis (status = submitted)
        self.project_submitted = Project.objects.create(
            title="Projet Soumis",
            tagline="Solution soumise",
            description="Description soumise",
            created_by=self.student_lead,
            status=Project.Status.SUBMITTED,
        )

        # Projet refusé (status = rejected) avec motif
        self.project_rejected = Project.objects.create(
            title="Projet Refusé Test",
            tagline="Solution rejetée temporairement",
            description="Description du projet à corriger",
            created_by=self.student_lead,
            status=Project.Status.REJECTED,
            rejection_reason="Cahier des charges incomplet",
            reviewed_by=self.organizer_user,
            reviewed_at=timezone.now(),
        )
        ProjectMember.objects.create(
            project=self.project_rejected,
            user=self.student_lead,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )
        ProjectMember.objects.create(
            project=self.project_rejected,
            user=self.student_dev,
            role=ProjectMember.Role.DEVELOPPEUR,
        )

        # Projet en cours d'évaluation (status = under_review)
        self.project_under_review = Project.objects.create(
            title="Projet En Revue Test",
            tagline="Solution sous revue",
            description="Description en cours d'analyse",
            created_by=self.student_lead,
            status=Project.Status.UNDER_REVIEW,
        )
        ProjectMember.objects.create(
            project=self.project_under_review,
            user=self.student_lead,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )

    # --------------------------------------------------------------------------
    # RÈGLE 1 : STUDENT PERMISSIONS
    # --------------------------------------------------------------------------
    def test_student_can_edit_own_draft_project_before_deadline(self):
        """Un étudiant de l'équipe peut modifier son projet en brouillon avant deadline."""
        self.assertTrue(services.can_edit_project(self.student_lead, self.project_draft))
        self.assertTrue(services.can_edit_project(self.student_dev, self.project_draft))

    def test_student_cannot_edit_other_student_project(self):
        """Un étudiant non membre ne peut pas modifier le projet."""
        self.assertFalse(services.can_edit_project(self.student_other, self.project_draft))

    def test_student_cannot_edit_after_submission_or_acceptance(self):
        """Un étudiant ne peut pas modifier un projet soumis ou accepté."""
        self.assertFalse(services.can_edit_project(self.student_lead, self.project_submitted))
        self.assertFalse(services.can_edit_project(self.student_lead, self.project_accepted))

    def test_student_cannot_edit_after_deadline(self):
        """Un étudiant ne peut plus modifier si la date limite est dépassée."""
        self.project_draft.deadline = timezone.now() - timedelta(hours=1)
        self.project_draft.save()
        self.assertFalse(services.can_edit_project(self.student_lead, self.project_draft))

    def test_only_chef_de_projet_can_manage_members_and_delete(self):
        """Seul le chef de projet peut gérer les membres et supprimer le projet."""
        # Chef de projet
        self.assertTrue(services.can_manage_members(self.student_lead, self.project_draft))
        self.assertTrue(services.can_delete_project(self.student_lead, self.project_draft))

        # Développeur (membre d'équipe mais pas lead)
        self.assertFalse(services.can_manage_members(self.student_dev, self.project_draft))
        self.assertFalse(services.can_delete_project(self.student_dev, self.project_draft))

        # Étudiant externe
        self.assertFalse(services.can_manage_members(self.student_other, self.project_draft))
        self.assertFalse(services.can_delete_project(self.student_other, self.project_draft))

    # --------------------------------------------------------------------------
    # RÈGLE 2 : ORGANIZER PERMISSIONS
    # --------------------------------------------------------------------------
    def test_organizer_can_view_all_projects_including_drafts(self):
        """L'organisateur voit tous les projets, y compris les brouillons."""
        self.assertTrue(services.can_view_project(self.organizer_user, self.project_draft))
        self.assertTrue(services.can_view_project(self.organizer_user, self.project_submitted))
        self.assertTrue(services.can_view_project(self.organizer_user, self.project_accepted))

    def test_organizer_can_review_submitted_projects(self):
        """L'organisateur peut valider ou refuser un projet soumis."""
        self.assertTrue(services.can_review_project(self.organizer_user, self.project_submitted))

    def test_organizer_cannot_modify_content_or_members(self):
        """L'organisateur ne modifie ni le contenu ni les membres du projet."""
        self.assertFalse(services.can_edit_project(self.organizer_user, self.project_draft))
        self.assertFalse(services.can_manage_members(self.organizer_user, self.project_draft))

    # --------------------------------------------------------------------------
    # RÈGLE 3 : JUDGE PERMISSIONS
    # --------------------------------------------------------------------------
    def test_judge_can_only_view_accepted_projects(self):
        """Le jury ne voit UNIQUEMENT que les projets validés."""
        self.assertTrue(services.can_view_project(self.judge_user, self.project_accepted))
        self.assertFalse(services.can_view_project(self.judge_user, self.project_draft))
        self.assertFalse(services.can_view_project(self.judge_user, self.project_submitted))

    def test_judge_cannot_edit_or_review(self):
        """Le jury est en lecture seule : pas de modification ni de validation."""
        self.assertFalse(services.can_edit_project(self.judge_user, self.project_accepted))
        self.assertFalse(services.can_review_project(self.judge_user, self.project_submitted))

    # --------------------------------------------------------------------------
    # RÈGLE 4 : MENTOR PERMISSIONS
    # --------------------------------------------------------------------------
    def test_mentor_can_view_accompanied_projects(self):
        """Le mentor voit les projets des équipes qu'il accompagne."""
        # Non rattaché à l'équipe -> ne voit pas le brouillon
        self.assertFalse(services.can_view_project(self.mentor_user, self.project_draft))

        # Rattaché à l'équipe
        ProjectMember.objects.create(
            project=self.project_draft,
            user=self.mentor_user,
            role=ProjectMember.Role.DEVELOPPEUR,
        )
        self.assertTrue(services.can_view_project(self.mentor_user, self.project_draft))
        self.assertTrue(services.can_comment_as_mentor(self.mentor_user, self.project_draft))

    def test_mentor_cannot_edit_or_validate(self):
        """Le mentor ne peut ni modifier le contenu ni valider."""
        self.assertFalse(services.can_edit_project(self.mentor_user, self.project_draft))
        self.assertFalse(services.can_review_project(self.mentor_user, self.project_submitted))

    # --------------------------------------------------------------------------
    # RÈGLE 5 : ADMIN PERMISSIONS
    # --------------------------------------------------------------------------
    def test_admin_permissions_restricted_to_team_membership(self):
        """
        Admin has full view and review permissions globally.
        However, for edit, submit, member management and delete, admin must be a project team member.
        """
        # Non-member admin: can view and review, but cannot edit, submit, manage members, or delete
        self.assertTrue(services.can_view_project(self.admin_user, self.project_draft))
        self.assertTrue(services.can_review_project(self.admin_user, self.project_submitted))
        self.assertFalse(services.can_edit_project(self.admin_user, self.project_draft))
        self.assertFalse(services.can_submit_project(self.admin_user, self.project_draft))
        self.assertFalse(services.can_manage_members(self.admin_user, self.project_draft))
        self.assertFalse(services.can_delete_project(self.admin_user, self.project_draft))

        # Admin who IS a project team lead: has edit, submit, manage members, and delete permissions
        admin_project = Project.objects.create(
            title="Admin Lead Project",
            slug="admin-lead-project",
            tagline="Admin project",
            description="Description",
            created_by=self.admin_user,
            status=Project.Status.DRAFT,
        )
        ProjectMember.objects.create(
            project=admin_project,
            user=self.admin_user,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )
        self.assertTrue(services.can_edit_project(self.admin_user, admin_project))
        self.assertTrue(services.can_submit_project(self.admin_user, admin_project))
        self.assertTrue(services.can_manage_members(self.admin_user, admin_project))
        self.assertTrue(services.can_delete_project(self.admin_user, admin_project))

    # --------------------------------------------------------------------------
    # VÉRIFICATION HTTP 403 SUR LES VUES
    # --------------------------------------------------------------------------
    def test_http_403_when_unauthorized_user_edits(self):
        """Vérifie le code HTTP 403 si un utilisateur non autorisé tente de modifier."""
        c = Client()
        c.force_login(self.student_other)
        resp = c.get(f"/projects/{self.project_draft.slug}/edit/")
        self.assertEqual(resp.status_code, 403)

    def test_http_403_when_judge_tries_to_view_draft(self):
        """Vérifie le code HTTP 403 si un juge tente d'accéder à un brouillon."""
        c = Client()
        c.force_login(self.judge_user)
        resp = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp.status_code, 403)

    def test_http_403_when_student_tries_to_review(self):
        """Vérifie le code HTTP 403 si un étudiant tente de valider/refuser."""
        c = Client()
        c.force_login(self.student_lead)
        resp = c.post(f"/projects/admin-dashboard/{self.project_submitted.slug}/review/", {
            "decision": "accept"
        })
        self.assertEqual(resp.status_code, 403)

    # --------------------------------------------------------------------------
    # RÈGLE 6 : RESTRICTIONS STATUT & FORMULAIRE POUR ÉTUDIANTS
    # --------------------------------------------------------------------------
    def test_project_form_excludes_status_for_students(self):
        """Le champ 'status' doit être retiré du formulaire pour les étudiants."""
        student_form = ProjectForm(user=self.student_lead)
        self.assertNotIn("status", student_form.fields)

        dev_form = ProjectForm(user=self.student_dev)
        self.assertNotIn("status", dev_form.fields)

        # Les organisateurs et administrateurs conservent le champ statut
        org_form = ProjectForm(user=self.organizer_user)
        self.assertIn("status", org_form.fields)

        admin_form = ProjectForm(user=self.admin_user)
        self.assertIn("status", admin_form.fields)

    def test_services_can_set_status_permissions(self):
        """Vérifie dans services.py que seuls Organizer/Admin peuvent définir les statuts réservés."""
        restricted_statuses = [
            Project.Status.UNDER_REVIEW,
            Project.Status.ACCEPTED,
            Project.Status.REJECTED,
            Project.Status.FINALIST,
            Project.Status.WINNER,
        ]

        # Les étudiants ne peuvent attribuer aucun de ces statuts
        for st in restricted_statuses:
            self.assertFalse(services.can_set_status(self.student_lead, st))
            with self.assertRaises(PermissionDenied):
                services.validate_status_permission(self.student_lead, st)

        # Les étudiants ne peuvent pas non plus forcer le statut 'submitted' via formulaire
        self.assertFalse(services.can_set_status(self.student_lead, Project.Status.SUBMITTED))
        with self.assertRaises(PermissionDenied):
            services.validate_status_permission(self.student_lead, Project.Status.SUBMITTED)

        # Seul le statut 'draft' est valide pour un étudiant
        self.assertTrue(services.can_set_status(self.student_lead, Project.Status.DRAFT))

        # Les Organisateurs et Administrateurs peuvent définir tous les statuts d'évaluation
        for st in restricted_statuses:
            self.assertTrue(services.can_set_status(self.organizer_user, st))
            self.assertTrue(services.can_set_status(self.admin_user, st))

    def test_http_403_when_student_sends_forbidden_status_on_create(self):
        """Vérifie le code HTTP 403 si un étudiant envoie un statut interdit à la création."""
        c = Client()
        c.force_login(self.student_lead)

        forbidden_statuses = [
            Project.Status.ACCEPTED,
            Project.Status.UNDER_REVIEW,
            Project.Status.REJECTED,
            Project.Status.FINALIST,
            Project.Status.WINNER,
            Project.Status.SUBMITTED,
        ]
        for st in forbidden_statuses:
            resp = c.post("/projects/create/", {
                "title": f"Projet Test {st}",
                "tagline": "Pitch test",
                "description": "Description complète du projet pour tester",
                "category": Project.Category.WEB,
                "status": st,
            })
            self.assertEqual(resp.status_code, 403)

    def test_http_403_when_student_sends_forbidden_status_on_update(self):
        """Vérifie le code HTTP 403 si un étudiant envoie un statut interdit lors de la modification."""
        c = Client()
        c.force_login(self.student_lead)

        # Tentative d'envoyer 'accepted'
        resp = c.post(f"/projects/{self.project_draft.slug}/edit/", {
            "title": "Titre Modifié",
            "tagline": "Pitch modifié",
            "description": "Description modifiée",
            "category": Project.Category.WEB,
            "status": Project.Status.ACCEPTED,
        })
        self.assertEqual(resp.status_code, 403)

        # Tentative d'envoyer 'under_review'
        resp_review = c.post(f"/projects/{self.project_draft.slug}/edit/", {
            "title": "Titre Modifié",
            "tagline": "Pitch modifié",
            "description": "Description modifiée",
            "category": Project.Category.WEB,
            "status": Project.Status.UNDER_REVIEW,
        })
        self.assertEqual(resp_review.status_code, 403)

    def test_project_created_as_draft_automatically(self):
        """Un projet créé par un étudiant est automatiquement au statut brouillon (draft)."""
        c = Client()
        c.force_login(self.student_lead)

        resp = c.post("/projects/create/", {
            "title": "Nouveau Projet Automatique",
            "tagline": "Slogan du projet",
            "description": "Description du nouveau projet créé",
            "category": Project.Category.WEB,
        })
        self.assertEqual(resp.status_code, 302)
        created_project = Project.objects.get(title="Nouveau Projet Automatique")
        self.assertEqual(created_project.status, Project.Status.DRAFT)

    def test_project_submission_only_via_submit_button(self):
        """Le passage à 'soumis' se fait uniquement via le bouton / action dédiée de soumission."""
        c = Client()
        c.force_login(self.student_lead)

        # Le projet est d'abord en brouillon
        self.assertEqual(self.project_draft.status, Project.Status.DRAFT)

        # Action bouton 'Soumettre le projet'
        resp = c.post(f"/projects/{self.project_draft.slug}/submit/")
        self.assertEqual(resp.status_code, 302)

        self.project_draft.refresh_from_db()
        self.assertEqual(self.project_draft.status, Project.Status.SUBMITTED)

    # --------------------------------------------------------------------------
    # RÈGLE 7 : DASHBOARD ADMIN - STATISTIQUES CATÉGORIES & BOUTONS ÉVALUATION
    # --------------------------------------------------------------------------
    def test_admin_dashboard_category_distribution(self):
        """Vérifie le calcul et l'affichage de la répartition des projets par catégorie."""
        c = Client()
        c.force_login(self.organizer_user)
        resp = c.get("/projects/admin-dashboard/")
        self.assertEqual(resp.status_code, 200)

        # Vérifier la présence des catégories avec label, count et percentage
        cat_stats = resp.context["stats"]["categories"]
        self.assertGreater(len(cat_stats), 0)
        for cat in cat_stats:
            self.assertIn("label", cat)
            self.assertIn("count", cat)
            self.assertIn("percentage", cat)

        # Vérifier la présence de la barre de progression dans le HTML
        self.assertContains(resp, 'role="progressbar"')
        self.assertContains(resp, "Répartition des projets par catégorie")

    def test_review_buttons_only_for_submitted_and_under_review_projects(self):
        """
        Dans l'admin dashboard, les boutons Accepter et Refuser n'apparaissent
        QUE pour les projets au statut 'submitted' ou 'under_review', jamais pour un 'draft'.
        """
        c = Client()
        c.force_login(self.organizer_user)

        # Projet en cours d'évaluation
        project_under_review = Project.objects.create(
            title="Projet En Revue",
            tagline="Sous revue",
            description="Description en cours d'évaluation",
            created_by=self.student_lead,
            status=Project.Status.UNDER_REVIEW,
        )

        resp = c.get("/projects/admin-dashboard/")
        self.assertEqual(resp.status_code, 200)

        content = resp.content.decode("utf-8")

        # Pour le projet soumis : les boutons accepter et refuser doivent être présents
        self.assertIn(f"/projects/admin-dashboard/{self.project_submitted.slug}/review/", content)
        self.assertIn(f"openRejectModal('{self.project_submitted.slug}'", content)

        # Pour le projet sous revue : les boutons doivent être présents
        self.assertIn(f"/projects/admin-dashboard/{project_under_review.slug}/review/", content)
        self.assertIn(f"openRejectModal('{project_under_review.slug}'", content)

        # Pour le projet en brouillon : AUCUN bouton accepter ou refuser
        self.assertNotIn(f"/projects/admin-dashboard/{self.project_draft.slug}/review/", content)
        self.assertNotIn(f"openRejectModal('{self.project_draft.slug}'", content)

    def test_server_side_cannot_review_draft_project(self):
        """
        Côté serveur (services.py & views.py) : tenter d'évaluer un projet en brouillon
        doit renvoyer une erreur 403 / PermissionDenied, même pour un Organisateur ou Admin.
        """
        # 1. Test unitaire services.py
        self.assertFalse(services.can_review_project(self.organizer_user, self.project_draft))
        self.assertFalse(services.can_review_project(self.admin_user, self.project_draft))
        with self.assertRaises(PermissionDenied):
            services.validate_review_permission(self.organizer_user, self.project_draft)

        # 2. Test HTTP sur la vue de review
        c = Client()
        c.force_login(self.organizer_user)
        resp = c.post(f"/projects/admin-dashboard/{self.project_draft.slug}/review/", {
            "decision": "accept"
        })
        self.assertEqual(resp.status_code, 403)

        resp_reject = c.post(f"/projects/admin-dashboard/{self.project_draft.slug}/review/", {
            "decision": "reject",
            "rejection_reason": "Non prêt",
        })
        self.assertEqual(resp_reject.status_code, 403)

    def test_server_side_can_review_submitted_and_under_review(self):
        """Vérifie que services.py autorise l'évaluation uniquement sur submitted et under_review."""
        self.assertTrue(services.can_review_project(self.organizer_user, self.project_submitted))

        project_under_review = Project.objects.create(
            title="Projet Revue",
            tagline="Pitch",
            description="Desc",
            created_by=self.student_lead,
            status=Project.Status.UNDER_REVIEW,
        )
        self.assertTrue(services.can_review_project(self.organizer_user, project_under_review))

        # Accepter un projet soumis fonctionne pour l'organisateur
        c = Client()
        c.force_login(self.organizer_user)
        resp = c.post(f"/projects/admin-dashboard/{self.project_submitted.slug}/review/", {
            "decision": "accept"
        })
        self.assertEqual(resp.status_code, 302)
        self.project_submitted.refresh_from_db()
        self.assertEqual(self.project_submitted.status, Project.Status.ACCEPTED)

    # --------------------------------------------------------------------------
    # RÈGLE 8 : PROJET REFUSÉ MODIFIABLE, RESOUMISSION & HISTORIQUE DES DÉCISIONS
    # --------------------------------------------------------------------------
    def test_student_can_edit_rejected_project(self):
        """Un projet au statut 'refusé' doit rester modifiable par son équipe."""
        # Vérification permissions services.py
        self.assertTrue(services.can_edit_project(self.student_lead, self.project_rejected))
        self.assertTrue(services.can_edit_project(self.student_dev, self.project_rejected))

        # Modification via la vue HTTP
        c = Client()
        c.force_login(self.student_lead)
        resp = c.post(f"/projects/{self.project_rejected.slug}/edit/", {
            "title": "Projet Refusé Corrigé",
            "tagline": "Pitch corrigé et enrichi",
            "description": "Nouvelle description répondant aux remarques",
            "category": Project.Category.WEB,
        })
        self.assertEqual(resp.status_code, 302)

        self.project_rejected.refresh_from_db()
        self.assertEqual(self.project_rejected.title, "Projet Refusé Corrigé")
        # Le statut reste 'rejected' tant qu'il n'a pas été explicitement resoumis
        self.assertEqual(self.project_rejected.status, Project.Status.REJECTED)

    def test_locked_projects_cannot_be_edited_server_side_403(self):
        """Les projets soumis, en cours d'évaluation et acceptés restent strictement verrouillés (403)."""
        locked_projects = [
            self.project_submitted,
            self.project_under_review,
            self.project_accepted,
        ]

        c = Client()
        c.force_login(self.student_lead)

        for p in locked_projects:
            # 1. Services.py renvoie False
            self.assertFalse(services.can_edit_project(self.student_lead, p))
            with self.assertRaises(PermissionDenied):
                services.validate_edit_permission(self.student_lead, p)

            # 2. Accès GET en modification renvoie HTTP 403
            resp_get = c.get(f"/projects/{p.slug}/edit/")
            self.assertEqual(resp_get.status_code, 403)

            # 3. Accès POST en modification renvoie HTTP 403
            resp_post = c.post(f"/projects/{p.slug}/edit/", {
                "title": "Tentative Piratage",
                "tagline": "Pitch",
                "description": "Desc",
                "category": Project.Category.WEB,
            })
            self.assertEqual(resp_post.status_code, 403)

            # 4. Accès POST en soumission renvoie HTTP 403
            resp_submit = c.post(f"/projects/{p.slug}/submit/")
            self.assertEqual(resp_submit.status_code, 403)

    def test_rejected_project_detail_shows_banner_and_buttons(self):
        """Un projet refusé affiche la bannière du motif de refus et les boutons 'Modifier' et 'Soumettre à nouveau'."""
        c = Client()
        c.force_login(self.student_lead)

        resp = c.get(f"/projects/{self.project_rejected.slug}/")
        self.assertEqual(resp.status_code, 200)

        # 1. Bannière du motif de refus
        self.assertContains(resp, "Projet Refusé")
        self.assertContains(resp, "Cahier des charges incomplet")

        # 2. Boutons Modifier et Soumettre à nouveau
        self.assertContains(resp, "Modifier")
        self.assertContains(resp, "Soumettre à nouveau")

    def test_resubmit_rejected_project_flow_and_history(self):
        """
        La resoumission fait repasser le projet à 'soumis', met à jour la date de soumission,
        masque la bannière de refus et enrichit l'historique des décisions.
        """
        c = Client()
        c.force_login(self.student_lead)

        # Date de soumission initiale vide
        self.assertIsNone(self.project_rejected.submitted_at)

        # Clic sur 'Soumettre à nouveau'
        resp = c.post(f"/projects/{self.project_rejected.slug}/submit/")
        self.assertEqual(resp.status_code, 302)

        self.project_rejected.refresh_from_db()

        # 1. Statut repasse à 'submitted'
        self.assertEqual(self.project_rejected.status, Project.Status.SUBMITTED)

        # 2. Date de soumission mise à jour
        self.assertIsNotNone(self.project_rejected.submitted_at)

        # 3. Historique contient l'action de resoumission
        self.assertTrue(len(self.project_rejected.review_history) > 0)
        last_entry = self.project_rejected.review_history[-1]
        self.assertEqual(last_entry.get("type"), "resubmission")
        self.assertEqual(last_entry.get("user"), self.student_lead.username)

        # 4. Consultation de la page : la bannière de refus n'est plus active pour un projet soumis
        detail_resp = c.get(f"/projects/{self.project_rejected.slug}/")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertNotContains(detail_resp, "Action requise : modifiez votre projet et soumettez-le à nouveau")
        # Mais l'historique complet reste affiché
        self.assertContains(detail_resp, "Historique des décisions et soumissions")
        self.assertContains(detail_resp, "Projet soumis à nouveau par")

    def test_complete_decision_history_cycle(self):
        """Vérifie le cycle complet : refus initial avec motif, resoumission, puis acceptation finale."""
        # 1. Refus par l'organisateur
        self.project_draft.status = Project.Status.SUBMITTED
        self.project_draft.save()
        self.project_draft.reject(self.organizer_user, "Besoin d'approfondir la sécurité")
        self.assertEqual(self.project_draft.status, Project.Status.REJECTED)

        # 2. Resoumission par l'équipe
        c = Client()
        c.force_login(self.student_lead)
        c.post(f"/projects/{self.project_draft.slug}/submit/")
        self.project_draft.refresh_from_db()
        self.assertEqual(self.project_draft.status, Project.Status.SUBMITTED)

        # 3. Acceptation par l'organisateur
        self.project_draft.accept(self.organizer_user)
        self.project_draft.refresh_from_db()
        self.assertEqual(self.project_draft.status, Project.Status.ACCEPTED)

        # Vérifier que toutes les étapes sont présentes dans review_history
        history = self.project_draft.review_history
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["decision"], "reject")
        self.assertEqual(history[0]["reason"], "Besoin d'approfondir la sécurité")
        self.assertEqual(history[1]["type"], "resubmission")
        self.assertEqual(history[2]["decision"], "accept")

    def test_ai_evaluation_permission_and_visibility(self):
        """
        Règle :
        - Le bouton "Évaluer avec l'IA" est masqué pour les rôles judge et mentor.
        - Il reste visible pour student (membres de l'équipe) et organizer.
        - Côté serveur : appel à /projects/<slug>/ai-analyze/ renvoie 403 pour judge, mentor et étudiants hors équipe.
        """
        # 1. Vérification au niveau du service
        self.assertFalse(services.can_run_ai_evaluation(self.judge_user, self.project_accepted))
        self.assertFalse(services.can_run_ai_evaluation(self.mentor_user, self.project_draft))
        self.assertFalse(services.can_run_ai_evaluation(self.student_other, self.project_draft))
        self.assertTrue(services.can_run_ai_evaluation(self.student_lead, self.project_draft))
        self.assertTrue(services.can_run_ai_evaluation(self.student_dev, self.project_draft))
        self.assertTrue(services.can_run_ai_evaluation(self.organizer_user, self.project_draft))

        # 2. validate_ai_evaluation_permission lève PermissionDenied pour judge, mentor et student hors équipe
        with self.assertRaises(PermissionDenied):
            services.validate_ai_evaluation_permission(self.judge_user, self.project_accepted)

        with self.assertRaises(PermissionDenied):
            services.validate_ai_evaluation_permission(self.mentor_user, self.project_draft)

        with self.assertRaises(PermissionDenied):
            services.validate_ai_evaluation_permission(self.student_other, self.project_draft)

        # 3. Vérification de la visibilité dans le template project_detail
        c = Client()

        # Student membre (créateur / lead) : bouton visible
        c.force_login(self.student_lead)
        resp_lead = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_lead.status_code, 200)
        self.assertContains(resp_lead, "Évaluer avec l'IA")
        self.assertContains(resp_lead, 'id="btn-run-ai"')

        # Organizer : bouton visible
        c.force_login(self.organizer_user)
        resp_org = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_org.status_code, 200)
        self.assertContains(resp_org, "Évaluer avec l'IA")
        self.assertContains(resp_org, 'id="btn-run-ai"')

        # Judge : sur un projet validé, le bouton doit être masqué
        c.force_login(self.judge_user)
        resp_judge = c.get(f"/projects/{self.project_accepted.slug}/")
        self.assertEqual(resp_judge.status_code, 200)
        self.assertNotContains(resp_judge, "Évaluer avec l'IA")
        self.assertNotContains(resp_judge, 'id="btn-run-ai"')

        # Mentor : sur un projet qu'il accompagne, le bouton doit être masqué
        ProjectMember.objects.create(
            project=self.project_draft,
            user=self.mentor_user,
            role=ProjectMember.Role.DEVELOPPEUR,
        )
        c.force_login(self.mentor_user)
        resp_mentor = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_mentor.status_code, 200)
        self.assertNotContains(resp_mentor, "Évaluer avec l'IA")
        self.assertNotContains(resp_mentor, 'id="btn-run-ai"')

        # 4. Vérification côté serveur : code HTTP 403 sur l'endpoint /ai-analyze/
        # Judge -> 403
        c.force_login(self.judge_user)
        resp_judge_ai = c.get(f"/projects/{self.project_accepted.slug}/ai-analyze/")
        self.assertEqual(resp_judge_ai.status_code, 403)

        # Mentor -> 403
        c.force_login(self.mentor_user)
        resp_mentor_ai = c.get(f"/projects/{self.project_draft.slug}/ai-analyze/")
        self.assertEqual(resp_mentor_ai.status_code, 403)

        # Student hors équipe -> 403
        c.force_login(self.student_other)
        resp_other_ai = c.get(f"/projects/{self.project_draft.slug}/ai-analyze/")
        self.assertEqual(resp_other_ai.status_code, 403)

        # Student membre -> 200
        c.force_login(self.student_lead)
        resp_lead_ai = c.get(f"/projects/{self.project_draft.slug}/ai-analyze/")
        self.assertEqual(resp_lead_ai.status_code, 200)

        # Organizer -> 200
        c.force_login(self.organizer_user)
        resp_org_ai = c.get(f"/projects/{self.project_draft.slug}/ai-analyze/")
        self.assertEqual(resp_org_ai.status_code, 200)

    def test_mentor_advice_permissions_and_restrictions(self):
        """
        Vérifie toutes les règles liées aux conseils du mentor :
        1. Modèle ConseilMentor : création avec projet, mentor, texte, date.
        2. Visibilité de la section : visible pour mentor et membres de l'équipe, masquée pour judge et étudiants tiers.
        3. Formulaire : seul le mentor a accès au formulaire d'envoi. Les membres de l'équipe ont un affichage en lecture seule.
        4. Côté serveur : 403 pour tout rôle non-mentor tentant de soumettre un conseil.
        5. Restrictions mentor : le mentor ne peut NI modifier, NI valider, NI refuser le projet.
        """
        # --- 1. Restrictions strictes sur le rôle Mentor ---
        # Le mentor ne peut pas modifier le projet
        self.assertFalse(services.can_edit_project(self.mentor_user, self.project_draft))
        self.assertFalse(services.can_edit_project(self.mentor_user, self.project_accepted))

        # Le mentor ne peut pas évaluer (valider/refuser) le projet
        self.assertFalse(services.can_review_project(self.mentor_user, self.project_submitted))

        # Vérification serveur des restrictions du mentor
        c = Client()
        c.force_login(self.mentor_user)

        # Tentative de modification par le mentor -> 403 Forbidden
        resp_edit = c.post(f"/projects/{self.project_draft.slug}/edit/", {"title": "Hack Modifié"})
        self.assertEqual(resp_edit.status_code, 403)

        # Tentative de validation par le mentor -> 403 Forbidden
        resp_validate = c.post(f"/projects/admin-dashboard/{self.project_submitted.slug}/review/", {"decision": "accept"})
        self.assertEqual(resp_validate.status_code, 403)

        # Tentative de refus par le mentor -> 403 Forbidden
        resp_refuse = c.post(
            f"/projects/admin-dashboard/{self.project_submitted.slug}/review/",
            {"decision": "reject", "rejection_reason": "Refus mentor"}
        )
        self.assertEqual(resp_refuse.status_code, 403)

        # --- 2. Permissions sur ConseilMentor dans services.py ---
        # can_add_mentor_advice : seul mentor est True
        self.assertTrue(services.can_add_mentor_advice(self.mentor_user, self.project_draft))
        self.assertFalse(services.can_add_mentor_advice(self.student_lead, self.project_draft))
        self.assertFalse(services.can_add_mentor_advice(self.student_dev, self.project_draft))
        self.assertFalse(services.can_add_mentor_advice(self.judge_user, self.project_draft))
        self.assertFalse(services.can_add_mentor_advice(self.organizer_user, self.project_draft))

        # can_view_mentor_advice : mentor et membres de l'équipe sont True, judge et student_other sont False
        self.assertTrue(services.can_view_mentor_advice(self.mentor_user, self.project_draft))
        self.assertTrue(services.can_view_mentor_advice(self.student_lead, self.project_draft))
        self.assertTrue(services.can_view_mentor_advice(self.student_dev, self.project_draft))
        self.assertFalse(services.can_view_mentor_advice(self.student_other, self.project_draft))
        self.assertFalse(services.can_view_mentor_advice(self.judge_user, self.project_draft))

        # validate_add_mentor_advice_permission lève PermissionDenied si non-mentor
        with self.assertRaises(PermissionDenied):
            services.validate_add_mentor_advice_permission(self.student_lead, self.project_draft)

        with self.assertRaises(PermissionDenied):
            services.validate_add_mentor_advice_permission(self.judge_user, self.project_draft)

        # --- 3. Envoi de conseil côté serveur et code 403 ---
        # Étudiant membre tente d'envoyer un conseil -> 403 Forbidden
        c.force_login(self.student_lead)
        resp_student_post = c.post(
            f"/projects/{self.project_draft.slug}/mentor-advice/",
            {"texte": "Conseil par un étudiant"}
        )
        self.assertEqual(resp_student_post.status_code, 403)

        # Judge tente d'envoyer un conseil -> 403 Forbidden
        c.force_login(self.judge_user)
        resp_judge_post = c.post(
            f"/projects/{self.project_draft.slug}/mentor-advice/",
            {"texte": "Conseil par un juge"}
        )
        self.assertEqual(resp_judge_post.status_code, 403)

        # Mentor envoie un conseil -> 302 (succès et redirection)
        c.force_login(self.mentor_user)
        resp_mentor_post = c.post(
            f"/projects/{self.project_draft.slug}/mentor-advice/",
            {"texte": "Pensez à structurer votre API REST et à ajouter des tests."}
        )
        self.assertEqual(resp_mentor_post.status_code, 302)

        # Vérifier création dans le modèle ConseilMentor
        conseils = ConseilMentor.objects.filter(project=self.project_draft)
        self.assertEqual(conseils.count(), 1)
        conseil = conseils.first()
        self.assertEqual(conseil.mentor, self.mentor_user)
        self.assertIn("structurer votre API REST", conseil.texte)
        self.assertIsNotNone(conseil.date)
        self.assertIn("Conseil de", str(conseil))

        # --- 4. Visibilité et affichage dans le template project_detail ---
        # Le mentor accompagne le projet test
        ProjectMember.objects.create(
            project=self.project_draft,
            user=self.mentor_user,
            role=ProjectMember.Role.DEVELOPPEUR,
        )

        # Mentor : voit la section ET le formulaire avec le bouton "Envoyer le conseil"
        c.force_login(self.mentor_user)
        resp_mentor_detail = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_mentor_detail.status_code, 200)
        self.assertContains(resp_mentor_detail, "Conseils du mentor")
        self.assertContains(resp_mentor_detail, 'id="btn-submit-mentor-advice"')
        self.assertContains(resp_mentor_detail, "Envoyer le conseil")
        self.assertContains(resp_mentor_detail, "Pensez à structurer votre API REST")

        # Étudiant membre : voit la section en lecture seule (pas de bouton d'envoi de conseil)
        c.force_login(self.student_lead)
        resp_lead_detail = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_lead_detail.status_code, 200)
        self.assertContains(resp_lead_detail, "Conseils du mentor")
        self.assertNotContains(resp_lead_detail, 'id="btn-submit-mentor-advice"')
        self.assertNotContains(resp_lead_detail, "Envoyer le conseil")
        # Mais voit le conseil avec le nom du mentor et le texte
        self.assertContains(resp_lead_detail, self.mentor_user.username)
        self.assertContains(resp_lead_detail, "Pensez à structurer votre API REST")

        # Juge : sur un projet validé, ne voit PAS la section "Conseils du mentor"
        c.force_login(self.judge_user)
        resp_judge_detail = c.get(f"/projects/{self.project_accepted.slug}/")
        self.assertEqual(resp_judge_detail.status_code, 200)
        self.assertNotContains(resp_judge_detail, 'id="mentor-advices-section"')
        self.assertNotContains(resp_judge_detail, "Conseils du mentor")

    def test_team_management_locked_by_status(self):
        """
        Règles de gestion d'équipe :
        1. L'ajout et le retrait de membres ne sont autorisés que pour le chef de projet
           quand le projet est en 'brouillon' (draft) ou 'refusé' (rejected).
        2. Pour 'soumis' (submitted), 'en cours d'évaluation' (under_review), 'accepté' (accepted),
           'finaliste' (finalist) et 'lauréat' (winner), les boutons 'Retirer' et le formulaire
           'Ajouter un étudiant' sont masqués et l'accès côté serveur renvoie une erreur 403.
        """
        locked_statuses = [
            Project.Status.SUBMITTED,
            Project.Status.UNDER_REVIEW,
            Project.Status.ACCEPTED,
            Project.Status.FINALIST,
            Project.Status.WINNER,
        ]

        # 1. Vérification services.can_manage_members
        # Brouillon et Refusé -> Autorisés pour le chef de projet
        self.assertTrue(services.can_manage_members(self.student_lead, self.project_draft))
        self.assertTrue(services.can_manage_members(self.student_lead, self.project_rejected))

        # Statuts verrouillés -> Interdits (False)
        for st in locked_statuses:
            self.project_draft.status = st
            self.project_draft.save()
            self.assertFalse(
                services.can_manage_members(self.student_lead, self.project_draft),
                f"La gestion d'équipe devrait être interdite pour le statut {st}"
            )
            with self.assertRaises(PermissionDenied):
                services.validate_manage_members_permission(self.student_lead, self.project_draft)

        # 2. Côté serveur (HTTP 403 sur member_add et member_remove pour les statuts verrouillés)
        c = Client()
        c.force_login(self.student_lead)

        # Projet soumis (submitted) -> 403 sur member_add
        resp_add_submitted = c.post(
            f"/projects/{self.project_submitted.slug}/members/add/",
            {"user": self.student_other.id, "role": ProjectMember.Role.DEVELOPPEUR}
        )
        self.assertEqual(resp_add_submitted.status_code, 403)

        # Membre sur le projet soumis pour tester member_remove
        m_submitted = ProjectMember.objects.create(
            project=self.project_submitted,
            user=self.student_dev,
            role=ProjectMember.Role.DEVELOPPEUR
        )
        resp_remove_submitted = c.post(
            f"/projects/{self.project_submitted.slug}/members/{m_submitted.id}/remove/"
        )
        self.assertEqual(resp_remove_submitted.status_code, 403)

        # Projet validé (accepted) -> 403 sur member_add et member_remove
        resp_add_accepted = c.post(
            f"/projects/{self.project_accepted.slug}/members/add/",
            {"user": self.student_other.id, "role": ProjectMember.Role.DEVELOPPEUR}
        )
        self.assertEqual(resp_add_accepted.status_code, 403)

        m_accepted = ProjectMember.objects.create(
            project=self.project_accepted,
            user=self.student_dev,
            role=ProjectMember.Role.DEVELOPPEUR
        )
        resp_remove_accepted = c.post(
            f"/projects/{self.project_accepted.slug}/members/{m_accepted.id}/remove/"
        )
        self.assertEqual(resp_remove_accepted.status_code, 403)

        # 3. Côté serveur (succès sur draft et rejected)
        # Remise en brouillon
        self.project_draft.status = Project.Status.DRAFT
        self.project_draft.save()

        # Ajout sur projet brouillon -> Succès (302)
        resp_add_draft = c.post(
            f"/projects/{self.project_draft.slug}/members/add/",
            {"user": self.student_other.id, "role": ProjectMember.Role.DEVELOPPEUR}
        )
        self.assertEqual(resp_add_draft.status_code, 302)
        self.assertTrue(ProjectMember.objects.filter(project=self.project_draft, user=self.student_other).exists())

        # Retrait sur projet brouillon -> Succès (302)
        m_draft = ProjectMember.objects.get(project=self.project_draft, user=self.student_other)
        resp_remove_draft = c.post(
            f"/projects/{self.project_draft.slug}/members/{m_draft.id}/remove/"
        )
        self.assertEqual(resp_remove_draft.status_code, 302)
        self.assertFalse(ProjectMember.objects.filter(project=self.project_draft, user=self.student_other).exists())

        # Ajout sur projet refusé -> Succès (302)
        resp_add_rejected = c.post(
            f"/projects/{self.project_rejected.slug}/members/add/",
            {"user": self.student_other.id, "role": ProjectMember.Role.DEVELOPPEUR}
        )
        self.assertEqual(resp_add_rejected.status_code, 302)
        self.assertTrue(ProjectMember.objects.filter(project=self.project_rejected, user=self.student_other).exists())

        # Retrait sur projet refusé -> Succès (302)
        m_rejected = ProjectMember.objects.get(project=self.project_rejected, user=self.student_other)
        resp_remove_rejected = c.post(
            f"/projects/{self.project_rejected.slug}/members/{m_rejected.id}/remove/"
        )
        self.assertEqual(resp_remove_rejected.status_code, 302)

        # 4. Vérification de l'affichage dans le template project_detail
        # Sur projet brouillon : boutons Retirer et formulaire Ajouter un étudiant présents
        resp_draft_ui = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_draft_ui.status_code, 200)
        self.assertContains(resp_draft_ui, "Ajouter un étudiant")
        self.assertContains(resp_draft_ui, "Retirer")
        self.assertNotContains(resp_draft_ui, "🔒 Équipe verrouillée")

        # Sur projet refusé : boutons Retirer et formulaire Ajouter un étudiant présents (student_dev déjà membre dans setUp)
        resp_rejected_ui = c.get(f"/projects/{self.project_rejected.slug}/")
        self.assertEqual(resp_rejected_ui.status_code, 200)
        self.assertContains(resp_rejected_ui, "Ajouter un étudiant")
        self.assertContains(resp_rejected_ui, "Retirer")
        self.assertNotContains(resp_rejected_ui, "🔒 Équipe verrouillée")

        # Sur projet soumis : boutons Retirer et formulaire masqués, badge verrouillé présent
        resp_submitted_ui = c.get(f"/projects/{self.project_submitted.slug}/")
        self.assertEqual(resp_submitted_ui.status_code, 200)
        self.assertNotContains(resp_submitted_ui, "Ajouter un étudiant")
        self.assertNotContains(resp_submitted_ui, "Retirer")
        self.assertContains(resp_submitted_ui, "🔒 Équipe verrouillée")

        # Sur projet accepté : boutons Retirer et formulaire masqués, badge verrouillé présent
        resp_accepted_ui = c.get(f"/projects/{self.project_accepted.slug}/")
        self.assertEqual(resp_accepted_ui.status_code, 200)
        self.assertNotContains(resp_accepted_ui, "Ajouter un étudiant")
        self.assertNotContains(resp_accepted_ui, "Retirer")
        self.assertContains(resp_accepted_ui, "🔒 Équipe verrouillée")

    def test_delete_locked_by_status(self):
        """
        Règles de suppression d'un projet :
        1. can_delete_project retourne False pour les statuts verrouillés.
        2. validate_delete_permission lève PermissionDenied pour les statuts verrouillés.
        3. HTTP GET et POST sur project_delete renvoient 403 pour les statuts verrouillés.
        4. HTTP 200 (page de confirmation) et 302 (suppression réelle) pour draft et rejected.
        5. Le bouton "Supprimer" est masqué dans le template pour les statuts verrouillés.
        6. Le verrouillage de l'équipe ne supprime aucun membre existant.
        """
        locked_statuses = [
            Project.Status.SUBMITTED,
            Project.Status.UNDER_REVIEW,
            Project.Status.ACCEPTED,
            Project.Status.FINALIST,
            Project.Status.WINNER,
        ]

        # ── 1. Vérification services.can_delete_project ───────────────────────
        # Brouillon et Refusé -> Autorisés pour le chef de projet
        self.assertTrue(services.can_delete_project(self.student_lead, self.project_draft))
        self.assertTrue(services.can_delete_project(self.student_lead, self.project_rejected))

        # Membre simple (non chef) -> Interdit même en brouillon
        self.assertFalse(services.can_delete_project(self.student_dev, self.project_draft))

        # Non-membre -> Interdit
        self.assertFalse(services.can_delete_project(self.student_other, self.project_draft))

        # Non-member (even Admin or Organizer) -> Forbidden
        self.assertFalse(services.can_delete_project(self.admin_user, self.project_draft))
        self.assertFalse(services.can_delete_project(self.organizer_user, self.project_draft))

        # Statuts verrouillés -> Interdits (False) pour tout le monde, y compris le chef
        for st in locked_statuses:
            self.project_draft.status = st
            self.project_draft.save()
            self.assertFalse(
                services.can_delete_project(self.student_lead, self.project_draft),
                f"La suppression devrait être interdite pour le statut {st}"
            )
            self.assertFalse(
                services.can_delete_project(self.admin_user, self.project_draft),
                f"Même l'admin ne peut pas supprimer un projet au statut {st}"
            )

        # ── 2. validate_delete_permission lève PermissionDenied ───────────────
        for st in locked_statuses:
            self.project_draft.status = st
            self.project_draft.save()
            with self.assertRaises(PermissionDenied,
                                   msg=f"PermissionDenied attendu pour statut {st}"):
                services.validate_delete_permission(self.student_lead, self.project_draft)

        # Remettre en brouillon
        self.project_draft.status = Project.Status.DRAFT
        self.project_draft.save()

        # Brouillon OK pour le chef -> pas d'exception
        try:
            services.validate_delete_permission(self.student_lead, self.project_draft)
        except PermissionDenied:
            self.fail("validate_delete_permission ne devrait pas lever PermissionDenied pour un brouillon")

        # ── 3. HTTP 403 côté serveur pour les statuts verrouillés ─────────────
        c = Client()
        c.force_login(self.student_lead)

        for st in locked_statuses:
            self.project_draft.status = st
            self.project_draft.save()

            resp_get = c.get(f"/projects/{self.project_draft.slug}/delete/")
            self.assertEqual(resp_get.status_code, 403,
                             f"GET /delete/ devrait renvoyer 403 pour statut {st}")

            resp_post = c.post(f"/projects/{self.project_draft.slug}/delete/")
            self.assertEqual(resp_post.status_code, 403,
                             f"POST /delete/ devrait renvoyer 403 pour statut {st}")

        # Vérifier que le projet soumis retourne aussi 403
        resp_submitted = c.post(f"/projects/{self.project_submitted.slug}/delete/")
        self.assertEqual(resp_submitted.status_code, 403)

        resp_accepted = c.post(f"/projects/{self.project_accepted.slug}/delete/")
        self.assertEqual(resp_accepted.status_code, 403)

        # ── 4. Suppression réelle : draft et rejected ─────────────────────────
        # Remettre en brouillon
        self.project_draft.status = Project.Status.DRAFT
        self.project_draft.save()

        # GET /delete/ sur brouillon -> page de confirmation (200)
        resp_confirm = c.get(f"/projects/{self.project_draft.slug}/delete/")
        self.assertEqual(resp_confirm.status_code, 200)

        # POST /delete/ sur projet refusé -> suppression et redirection (302)
        rejected_slug = self.project_rejected.slug
        rejected_pk = self.project_rejected.pk
        resp_delete_rejected = c.post(f"/projects/{rejected_slug}/delete/")
        self.assertEqual(resp_delete_rejected.status_code, 302)
        self.assertFalse(Project.objects.filter(pk=rejected_pk).exists(),
                         "Le projet refusé aurait dû être supprimé.")

        # ── 5. Template : bouton Supprimer masqué pour statuts verrouillés ─────
        # Remettre en brouillon -> bouton Supprimer visible
        self.project_draft.status = Project.Status.DRAFT
        self.project_draft.save()

        # Ajouter student_lead comme membre chef si non présent (après d'éventuelles suppressions)
        if not ProjectMember.objects.filter(
            project=self.project_draft, user=self.student_lead
        ).exists():
            ProjectMember.objects.create(
                project=self.project_draft,
                user=self.student_lead,
                role=ProjectMember.Role.CHEF_DE_PROJET,
            )

        resp_draft_ui = c.get(f"/projects/{self.project_draft.slug}/")
        self.assertEqual(resp_draft_ui.status_code, 200)
        self.assertContains(resp_draft_ui, "Supprimer",
                            msg_prefix="Le bouton Supprimer doit être visible en brouillon")

        # Projet soumis -> bouton Supprimer masqué
        resp_submitted_ui = c.get(f"/projects/{self.project_submitted.slug}/")
        self.assertEqual(resp_submitted_ui.status_code, 200)
        self.assertNotContains(resp_submitted_ui, "Supprimer",
                               msg_prefix="Le bouton Supprimer ne doit pas apparaître pour un projet soumis")

        # Projet accepté -> bouton Supprimer masqué
        resp_accepted_ui = c.get(f"/projects/{self.project_accepted.slug}/")
        self.assertEqual(resp_accepted_ui.status_code, 200)
        self.assertNotContains(resp_accepted_ui, "Supprimer",
                               msg_prefix="Le bouton Supprimer ne doit pas apparaître pour un projet accepté")

        # ── 6. Verrouillage de l'équipe ne supprime aucun membre existant ──────
        # Passer en soumis -> l'équipe est verrouillée
        self.project_draft.status = Project.Status.SUBMITTED
        self.project_draft.save()

        members_before = list(
            ProjectMember.objects.filter(project=self.project_draft).values_list("user_id", flat=True)
        )
        self.assertTrue(len(members_before) >= 1,
                        "Il doit y avoir au moins un membre avant verrouillage")

        # Tentative d'ajout -> 403 mais l'équipe actuelle reste intacte
        c.post(
            f"/projects/{self.project_draft.slug}/members/add/",
            {"user": self.student_other.id, "role": ProjectMember.Role.DEVELOPPEUR}
        )

        members_after = list(
            ProjectMember.objects.filter(project=self.project_draft).values_list("user_id", flat=True)
        )
        self.assertEqual(
            sorted(members_before), sorted(members_after),
            "Le verrouillage ne doit supprimer aucun membre existant"
        )

    def test_non_member_organizer_and_admin_forbidden_403_and_buttons_hidden(self):
        """
        Verify that on the project detail page and across all service actions:
        - Buttons 'Submit', 'Resubmit', 'Edit', 'Delete', 'Remove', and 'Add Student'
          ONLY appear for team members according to status.
        - Non-member organizers and admins DO NOT see these buttons.
        - Non-member organizers and admins receive HTTP 403 (PermissionDenied)
          on edit, delete, submit, and member management.
        - Organizers and admins who ARE team members can access these actions according to their role.
        """
        c = Client()

        # ── 1. Services logic: Non-member Organizer & Admin ───────────────────
        for non_member in (self.organizer_user, self.admin_user):
            self.assertFalse(services.can_edit_project(non_member, self.project_draft))
            self.assertFalse(services.can_submit_project(non_member, self.project_draft))
            self.assertFalse(services.can_delete_project(non_member, self.project_draft))
            self.assertFalse(services.can_manage_members(non_member, self.project_draft))

            with self.assertRaises(PermissionDenied):
                services.validate_edit_permission(non_member, self.project_draft)

            with self.assertRaises(PermissionDenied):
                services.validate_submit_permission(non_member, self.project_draft)

            with self.assertRaises(PermissionDenied):
                services.validate_delete_permission(non_member, self.project_draft)

            with self.assertRaises(PermissionDenied):
                services.validate_manage_members_permission(non_member, self.project_draft)

        # ── 2. Server-side HTTP 403 on all action endpoints for Organizer ─────
        c.force_login(self.organizer_user)
        slug = self.project_draft.slug
        dev_membership = ProjectMember.objects.get(project=self.project_draft, user=self.student_dev)

        # Edit -> 403
        resp_edit_get = c.get(f"/projects/{slug}/edit/")
        self.assertEqual(resp_edit_get.status_code, 403)
        resp_edit_post = c.post(f"/projects/{slug}/edit/", {"title": "Hacked Title"})
        self.assertEqual(resp_edit_post.status_code, 403)

        # Submit -> 403
        resp_submit = c.post(f"/projects/{slug}/submit/")
        self.assertEqual(resp_submit.status_code, 403)

        # Delete -> 403
        resp_del_get = c.get(f"/projects/{slug}/delete/")
        self.assertEqual(resp_del_get.status_code, 403)
        resp_del_post = c.post(f"/projects/{slug}/delete/")
        self.assertEqual(resp_del_post.status_code, 403)

        # Team Management (Add & Remove) -> 403
        resp_add_member = c.post(f"/projects/{slug}/members/add/", {
            "user": self.student_other.id,
            "role": ProjectMember.Role.DEVELOPPEUR,
        })
        self.assertEqual(resp_add_member.status_code, 403)

        resp_remove_member = c.post(f"/projects/{slug}/members/{dev_membership.id}/remove/")
        self.assertEqual(resp_remove_member.status_code, 403)

        # ── 3. Server-side HTTP 403 for non-member Admin ──────────────────────
        c.force_login(self.admin_user)
        self.assertEqual(c.get(f"/projects/{slug}/edit/").status_code, 403)
        self.assertEqual(c.post(f"/projects/{slug}/edit/", {"title": "Admin Edit"}).status_code, 403)
        self.assertEqual(c.post(f"/projects/{slug}/submit/").status_code, 403)
        self.assertEqual(c.get(f"/projects/{slug}/delete/").status_code, 403)
        self.assertEqual(c.post(f"/projects/{slug}/delete/").status_code, 403)
        self.assertEqual(c.post(f"/projects/{slug}/members/add/", {
            "user": self.student_other.id,
            "role": ProjectMember.Role.DEVELOPPEUR,
        }).status_code, 403)
        self.assertEqual(c.post(f"/projects/{slug}/members/{dev_membership.id}/remove/").status_code, 403)

        # ── 4. UI check: Buttons hidden for non-member Organizer and Admin ────
        for non_member in (self.organizer_user, self.admin_user):
            c.force_login(non_member)
            resp_detail = c.get(f"/projects/{slug}/")
            self.assertEqual(resp_detail.status_code, 200)

            # Team management buttons must NOT appear
            self.assertNotContains(resp_detail, "Add Student")
            self.assertNotContains(resp_detail, "Ajouter un étudiant")
            self.assertNotContains(resp_detail, "Remove")
            self.assertNotContains(resp_detail, "Retirer")

            # Project actions must NOT appear
            self.assertNotContains(resp_detail, "Edit")
            self.assertNotContains(resp_detail, "Modifier")
            self.assertNotContains(resp_detail, "Submit Project")
            self.assertNotContains(resp_detail, "Soumettre")
            self.assertNotContains(resp_detail, "Resubmit")
            self.assertNotContains(resp_detail, "Soumettre à nouveau")
            self.assertNotContains(resp_detail, "Delete")
            self.assertNotContains(resp_detail, "Supprimer")

        # ── 5. When Organizer IS a team member, buttons appear properly ───────
        org_project = Project.objects.create(
            title="Organizer Team Project",
            slug="organizer-team-project",
            tagline="Organizer team project",
            description="Detailed description",
            created_by=self.organizer_user,
            status=Project.Status.DRAFT,
            deadline=timezone.now() + timedelta(days=3),
        )
        ProjectMember.objects.create(
            project=org_project,
            user=self.organizer_user,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )

        self.assertTrue(services.can_edit_project(self.organizer_user, org_project))
        self.assertTrue(services.can_submit_project(self.organizer_user, org_project))
        self.assertTrue(services.can_manage_members(self.organizer_user, org_project))
        self.assertTrue(services.can_delete_project(self.organizer_user, org_project))

        c.force_login(self.organizer_user)
        resp_org_detail = c.get(f"/projects/{org_project.slug}/")
        self.assertEqual(resp_org_detail.status_code, 200)
        self.assertContains(resp_org_detail, "Edit")
        self.assertContains(resp_org_detail, "Submit Project")
        self.assertContains(resp_org_detail, "Delete")
        self.assertContains(resp_org_detail, "Add Student")


# ─────────────────────────────────────────────────────────────────────────────
# HistoriqueProjet tests
# ─────────────────────────────────────────────────────────────────────────────

class HistoriqueProjetTestCase(TestCase):
    """
    Tests for the HistoriqueProjet audit-log model, services, and admin.
    """

    def setUp(self):
        # Student (project lead)
        self.student = User.objects.create_user(
            username="hist_student", email="hist_s@test.com", password="pwd"
        )
        self.student.profile.role = Profile.Role.STUDENT
        self.student.profile.save()

        # Organizer (reviewer)
        self.organizer = User.objects.create_user(
            username="hist_org", email="hist_o@test.com", password="pwd", is_staff=True
        )
        self.organizer.profile.role = Profile.Role.ORGANIZER
        self.organizer.profile.save()

        # Admin (Django superuser, for admin panel tests)
        self.admin = User.objects.create_user(
            username="hist_admin", email="hist_a@test.com", password="pwd",
            is_superuser=True, is_staff=True
        )
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save()

        # Draft project created by student
        self.project = Project.objects.create(
            title="History Test Project",
            tagline="Testing history",
            description="A project for testing HistoriqueProjet.",
            category=Project.Category.WEB,
            status=Project.Status.DRAFT,
            created_by=self.student,
        )
        # Student is the team lead (in team_memberships)
        ProjectMember.objects.create(
            project=self.project,
            user=self.student,
            role=ProjectMember.Role.CHEF_DE_PROJET,
        )

        self.client = Client()

    # ── 1. Submission creates a history row ───────────────────────────────────

    def test_submit_creates_history_entry(self):
        from projects.models import HistoriqueProjet
        before = HistoriqueProjet.objects.filter(project=self.project).count()
        services.submit_project(self.project, self.student)
        after = HistoriqueProjet.objects.filter(project=self.project).count()
        self.assertEqual(after, before + 1)
        entry = HistoriqueProjet.objects.filter(project=self.project).latest("date")
        self.assertEqual(entry.action, HistoriqueProjet.Action.SUBMITTED)
        self.assertEqual(entry.acteur, self.student)

    # ── 2. Re-submission creates a resubmission history row ───────────────────

    def test_resubmit_creates_resubmission_entry(self):
        from projects.models import HistoriqueProjet
        # First submission
        services.submit_project(self.project, self.student)
        # Organizer rejects it
        services.review_project(self.project, self.organizer, "reject", "Not ready yet.")
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.REJECTED)

        before = HistoriqueProjet.objects.filter(project=self.project).count()
        services.submit_project(self.project, self.student)
        after = HistoriqueProjet.objects.filter(project=self.project).count()
        self.assertEqual(after, before + 1)

        entry = HistoriqueProjet.objects.filter(project=self.project).latest("date")
        self.assertEqual(entry.action, HistoriqueProjet.Action.RESUBMITTED)

    # ── 3. Acceptance creates an 'accepte' history row ────────────────────────

    def test_accept_creates_accepted_entry(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)
        services.review_project(self.project, self.organizer, "accept")
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.ACCEPTED)

        entry = HistoriqueProjet.objects.filter(
            project=self.project, action=HistoriqueProjet.Action.ACCEPTED
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.acteur, self.organizer)
        self.assertEqual(entry.commentaire, "")

    # ── 4. Rejection creates a 'refuse' history row with reason ──────────────

    def test_reject_creates_rejected_entry_with_reason(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)
        reason = "Project scope is too large."
        services.review_project(self.project, self.organizer, "reject", reason)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.REJECTED)

        entry = HistoriqueProjet.objects.filter(
            project=self.project, action=HistoriqueProjet.Action.REJECTED
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.acteur, self.organizer)
        self.assertEqual(entry.commentaire, reason)

    # ── 5. Rejection without reason raises ValueError ─────────────────────────

    def test_reject_without_reason_raises_value_error(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)
        before = HistoriqueProjet.objects.filter(project=self.project).count()

        with self.assertRaises(ValueError) as ctx:
            services.review_project(self.project, self.organizer, "reject", "")
        self.assertIn("reason", str(ctx.exception).lower())

        # No new history entry should have been created
        after = HistoriqueProjet.objects.filter(project=self.project).count()
        self.assertEqual(after, before)

    # ── 6. History is ordered chronologically ─────────────────────────────────

    def test_history_is_chronological(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)
        services.review_project(self.project, self.organizer, "reject", "Too early.")
        self.project.refresh_from_db()
        services.submit_project(self.project, self.student)

        entries = list(HistoriqueProjet.objects.filter(project=self.project).order_by("date"))
        dates = [e.date for e in entries]
        self.assertEqual(dates, sorted(dates))

    # ── 7. HistoriqueProjet admin is read-only (no add/change/delete) ─────────

    def test_historiqueprojet_admin_is_read_only(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)
        entry = HistoriqueProjet.objects.filter(project=self.project).first()

        self.client.force_login(self.admin)

        # Cannot add
        resp_add = self.client.get("/admin/projects/historiqueprojet/add/")
        self.assertEqual(resp_add.status_code, 403)

        # Change view redirects to list (read-only, no edit form)
        resp_change = self.client.get(f"/admin/projects/historiqueprojet/{entry.pk}/change/")
        self.assertEqual(resp_change.status_code, 302)

        # Cannot delete
        resp_delete = self.client.get(f"/admin/projects/historiqueprojet/{entry.pk}/delete/")
        self.assertEqual(resp_delete.status_code, 403)

    # ── 8. History inline appears on project admin page ───────────────────────

    def test_history_inline_in_project_admin(self):
        from projects.models import HistoriqueProjet
        services.submit_project(self.project, self.student)

        self.client.force_login(self.admin)
        resp = self.client.get(f"/admin/projects/project/{self.project.pk}/change/")
        self.assertEqual(resp.status_code, 200)
        # The inline table heading should appear
        self.assertContains(resp, "Project History")

    # ── 9. Submit then reject creates two lines with distinct dates in chronological order ──

    def test_submit_then_reject_creates_two_entries_with_different_dates_in_chronological_order(self):
        """
        Soumettre puis refuser un projet crée deux lignes dans HistoriqueProjet
        avec deux dates différentes, dans l'ordre chronologique.
        """
        import time
        from projects.models import HistoriqueProjet

        # 1. Soumission par l'étudiant
        services.submit_project(self.project, self.student)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.SUBMITTED)

        # Pause courte pour garantir que l'horodatage de la décision est strictement postérieur
        time.sleep(0.02)

        # 2. Refus par l'organisateur avec motif
        services.review_project(self.project, self.organizer, "reject", reason="Dossier incomplet")
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, Project.Status.REJECTED)

        # 3. Vérification des lignes créées
        history_entries = list(self.project.historique.all().order_by("date"))
        self.assertEqual(len(history_entries), 2)

        submission_entry, rejection_entry = history_entries

        # Actions attendues
        self.assertEqual(submission_entry.action, HistoriqueProjet.Action.SUBMITTED)
        self.assertEqual(rejection_entry.action, HistoriqueProjet.Action.REJECTED)
        self.assertEqual(rejection_entry.commentaire, "Dossier incomplet")

        # Dates différentes
        self.assertNotEqual(submission_entry.date, rejection_entry.date)

        # Ordre chronologique strict (submission < rejection)
        self.assertLess(submission_entry.date, rejection_entry.date)

        # Les dates correspondent aux vraies dates du projet
        self.assertEqual(submission_entry.date, self.project.submitted_at)
        self.assertEqual(rejection_entry.date, self.project.reviewed_at)
        self.assertEqual(submission_entry.date, self.project.date_soumission)
        self.assertEqual(rejection_entry.date, self.project.date_decision)

