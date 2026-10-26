"""
Template tags for the projects app using the service layer.
"""
from django import template

from projects.services import (
    can_create_project,
    is_admin,
    is_judge,
    is_mentor,
    is_organizer,
    is_student,
)

register = template.Library()


@register.simple_tag(name="can_create_project")
def can_create_project_tag(user):
    """Check if user can create a project."""
    return can_create_project(user)


@register.simple_tag(name="is_admin")
def is_admin_tag(user):
    """Check if user is admin."""
    return is_admin(user)


@register.simple_tag(name="is_organizer")
def is_organizer_tag(user):
    """Check if user is organizer."""
    return is_organizer(user)


@register.simple_tag(name="is_judge")
def is_judge_tag(user):
    """Check if user is judge."""
    return is_judge(user)


@register.simple_tag(name="is_mentor")
def is_mentor_tag(user):
    """Check if user is mentor."""
    return is_mentor(user)


@register.simple_tag(name="is_student")
def is_student_tag(user):
    """Check if user is student."""
    return is_student(user)