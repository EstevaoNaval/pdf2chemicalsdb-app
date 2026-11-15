from django.contrib.auth.models import Group, Permission
from rest_framework.test import APITestCase

from user.models import User


class ChemicalWritePermissionTests(APITestCase):
    """Who may write /api/chemicals/.

    Anonymous GET stays open. POST and PATCH require add_chemical and
    change_chemical. DELETE stays closed without delete_chemical.
    """

    def setUp(self):
        self.list_url = "/api/chemicals/"
        self.detail_url = "/api/chemicals/missing-id/"

        self.reader = User.objects.create_user(
            username="reader",
            email="reader@example.com",
            password="reader-password",
            first_name="Read",
            last_name="Er",
        )
        self.staff = User.objects.create_user(
            username="staffer",
            email="staff@example.com",
            password="staff-password",
            first_name="Staff",
            last_name="Er",
            is_staff=True,
        )
        self.worker = User.objects.create_user(
            username="worker",
            email="worker@example.com",
            password="worker-password",
            first_name="Work",
            last_name="Er",
        )
        group = Group.objects.create(name="django_worker_chemical_writer")
        permissions = Permission.objects.filter(
            content_type__app_label="chemicals",
            content_type__model="chemical",
            codename__in=("add_chemical", "change_chemical"),
        )
        self.assertEqual(permissions.count(), 2)
        group.permissions.set(permissions)
        self.worker.groups.add(group)

    def test_anonymous_get_is_allowed(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_users_without_chemical_perms_cannot_write(self):
        for user in (self.reader, self.staff):
            self.client.force_authenticate(user)
            self.assertEqual(
                self.client.post(self.list_url, {}, format="json").status_code,
                403,
            )
            self.assertEqual(
                self.client.patch(self.detail_url, {}, format="json").status_code,
                403,
            )
            self.assertEqual(self.client.delete(self.detail_url).status_code, 403)
            self.client.force_authenticate(None)

    def test_worker_group_can_post_and_patch_but_not_delete(self):
        self.client.force_authenticate(self.worker)
        # Unknown user id fails validation after the add permission check.
        post = self.client.post(self.list_url, {"user": 999999}, format="json")
        self.assertEqual(post.status_code, 400)
        # Missing row is 404, which means change_chemical was accepted.
        patch = self.client.patch(self.detail_url, {}, format="json")
        self.assertEqual(patch.status_code, 404)
        delete = self.client.delete(self.detail_url)
        self.assertEqual(delete.status_code, 403)
