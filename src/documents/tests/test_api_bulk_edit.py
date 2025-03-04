import json
from unittest import mock

from django.contrib.auth.models import User
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APITestCase

from documents import bulk_edit
from documents.models import Correspondent
from documents.models import Document
from documents.models import DocumentType
from documents.models import StoragePath
from documents.models import Tag
from documents.tests.utils import DirectoriesMixin


class TestBulkEdit(DirectoriesMixin, APITestCase):
    def setUp(self):
        super().setUp()

        user = User.objects.create_superuser(username="temp_admin")
        self.client.force_authenticate(user=user)

        patcher = mock.patch("documents.bulk_edit.bulk_update_documents.delay")
        self.async_task = patcher.start()
        self.addCleanup(patcher.stop)
        self.c1 = Correspondent.objects.create(name="c1")
        self.c2 = Correspondent.objects.create(name="c2")
        self.dt1 = DocumentType.objects.create(name="dt1")
        self.dt2 = DocumentType.objects.create(name="dt2")
        self.t1 = Tag.objects.create(name="t1")
        self.t2 = Tag.objects.create(name="t2")
        self.doc1 = Document.objects.create(checksum="A", title="A")
        self.doc2 = Document.objects.create(
            checksum="B",
            title="B",
            correspondent=self.c1,
            document_type=self.dt1,
        )
        self.doc3 = Document.objects.create(
            checksum="C",
            title="C",
            correspondent=self.c2,
            document_type=self.dt2,
        )
        self.doc4 = Document.objects.create(checksum="D", title="D")
        self.doc5 = Document.objects.create(checksum="E", title="E")
        self.doc2.tags.add(self.t1)
        self.doc3.tags.add(self.t2)
        self.doc4.tags.add(self.t1, self.t2)
        self.sp1 = StoragePath.objects.create(name="sp1", path="Something/{checksum}")

    def test_set_correspondent(self):
        self.assertEqual(Document.objects.filter(correspondent=self.c2).count(), 1)
        bulk_edit.set_correspondent(
            [self.doc1.id, self.doc2.id, self.doc3.id],
            self.c2.id,
        )
        self.assertEqual(Document.objects.filter(correspondent=self.c2).count(), 3)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc1.id, self.doc2.id])

    def test_unset_correspondent(self):
        self.assertEqual(Document.objects.filter(correspondent=self.c2).count(), 1)
        bulk_edit.set_correspondent([self.doc1.id, self.doc2.id, self.doc3.id], None)
        self.assertEqual(Document.objects.filter(correspondent=self.c2).count(), 0)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc2.id, self.doc3.id])

    def test_set_document_type(self):
        self.assertEqual(Document.objects.filter(document_type=self.dt2).count(), 1)
        bulk_edit.set_document_type(
            [self.doc1.id, self.doc2.id, self.doc3.id],
            self.dt2.id,
        )
        self.assertEqual(Document.objects.filter(document_type=self.dt2).count(), 3)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc1.id, self.doc2.id])

    def test_unset_document_type(self):
        self.assertEqual(Document.objects.filter(document_type=self.dt2).count(), 1)
        bulk_edit.set_document_type([self.doc1.id, self.doc2.id, self.doc3.id], None)
        self.assertEqual(Document.objects.filter(document_type=self.dt2).count(), 0)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc2.id, self.doc3.id])

    def test_set_document_storage_path(self):
        """
        GIVEN:
            - 5 documents without defined storage path
        WHEN:
            - Bulk edit called to add storage path to 1 document
        THEN:
            - Single document storage path update
        """
        self.assertEqual(Document.objects.filter(storage_path=None).count(), 5)

        bulk_edit.set_storage_path(
            [self.doc1.id],
            self.sp1.id,
        )

        self.assertEqual(Document.objects.filter(storage_path=None).count(), 4)

        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args

        self.assertCountEqual(kwargs["document_ids"], [self.doc1.id])

    def test_unset_document_storage_path(self):
        """
        GIVEN:
            - 4 documents without defined storage path
            - 1 document with a defined storage
        WHEN:
            - Bulk edit called to remove storage path from 1 document
        THEN:
            - Single document storage path removed
        """
        self.assertEqual(Document.objects.filter(storage_path=None).count(), 5)

        bulk_edit.set_storage_path(
            [self.doc1.id],
            self.sp1.id,
        )

        self.assertEqual(Document.objects.filter(storage_path=None).count(), 4)

        bulk_edit.set_storage_path(
            [self.doc1.id],
            None,
        )

        self.assertEqual(Document.objects.filter(storage_path=None).count(), 5)

        self.async_task.assert_called()
        args, kwargs = self.async_task.call_args

        self.assertCountEqual(kwargs["document_ids"], [self.doc1.id])

    def test_add_tag(self):
        self.assertEqual(Document.objects.filter(tags__id=self.t1.id).count(), 2)
        bulk_edit.add_tag(
            [self.doc1.id, self.doc2.id, self.doc3.id, self.doc4.id],
            self.t1.id,
        )
        self.assertEqual(Document.objects.filter(tags__id=self.t1.id).count(), 4)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc1.id, self.doc3.id])

    def test_remove_tag(self):
        self.assertEqual(Document.objects.filter(tags__id=self.t1.id).count(), 2)
        bulk_edit.remove_tag([self.doc1.id, self.doc3.id, self.doc4.id], self.t1.id)
        self.assertEqual(Document.objects.filter(tags__id=self.t1.id).count(), 1)
        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        self.assertCountEqual(kwargs["document_ids"], [self.doc4.id])

    def test_modify_tags(self):
        tag_unrelated = Tag.objects.create(name="unrelated")
        self.doc2.tags.add(tag_unrelated)
        self.doc3.tags.add(tag_unrelated)
        bulk_edit.modify_tags(
            [self.doc2.id, self.doc3.id],
            add_tags=[self.t2.id],
            remove_tags=[self.t1.id],
        )

        self.assertCountEqual(list(self.doc2.tags.all()), [self.t2, tag_unrelated])
        self.assertCountEqual(list(self.doc3.tags.all()), [self.t2, tag_unrelated])

        self.async_task.assert_called_once()
        args, kwargs = self.async_task.call_args
        # TODO: doc3 should not be affected, but the query for that is rather complicated
        self.assertCountEqual(kwargs["document_ids"], [self.doc2.id, self.doc3.id])

    def test_delete(self):
        self.assertEqual(Document.objects.count(), 5)
        bulk_edit.delete([self.doc1.id, self.doc2.id])
        self.assertEqual(Document.objects.count(), 3)
        self.assertCountEqual(
            [doc.id for doc in Document.objects.all()],
            [self.doc3.id, self.doc4.id, self.doc5.id],
        )

    @mock.patch("documents.serialisers.bulk_edit.set_correspondent")
    def test_api_set_correspondent(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_correspondent",
                    "parameters": {"correspondent": self.c1.id},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["correspondent"], self.c1.id)

    @mock.patch("documents.serialisers.bulk_edit.set_correspondent")
    def test_api_unset_correspondent(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_correspondent",
                    "parameters": {"correspondent": None},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertIsNone(kwargs["correspondent"])

    @mock.patch("documents.serialisers.bulk_edit.set_document_type")
    def test_api_set_type(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_document_type",
                    "parameters": {"document_type": self.dt1.id},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["document_type"], self.dt1.id)

    @mock.patch("documents.serialisers.bulk_edit.set_document_type")
    def test_api_unset_type(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_document_type",
                    "parameters": {"document_type": None},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertIsNone(kwargs["document_type"])

    @mock.patch("documents.serialisers.bulk_edit.add_tag")
    def test_api_add_tag(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "add_tag",
                    "parameters": {"tag": self.t1.id},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["tag"], self.t1.id)

    @mock.patch("documents.serialisers.bulk_edit.remove_tag")
    def test_api_remove_tag(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "remove_tag",
                    "parameters": {"tag": self.t1.id},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["tag"], self.t1.id)

    @mock.patch("documents.serialisers.bulk_edit.modify_tags")
    def test_api_modify_tags(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id, self.doc3.id],
                    "method": "modify_tags",
                    "parameters": {
                        "add_tags": [self.t1.id],
                        "remove_tags": [self.t2.id],
                    },
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertListEqual(args[0], [self.doc1.id, self.doc3.id])
        self.assertEqual(kwargs["add_tags"], [self.t1.id])
        self.assertEqual(kwargs["remove_tags"], [self.t2.id])

    @mock.patch("documents.serialisers.bulk_edit.modify_tags")
    def test_api_modify_tags_not_provided(self, m):
        """
        GIVEN:
            - API data to modify tags is missing modify_tags field
        WHEN:
            - API to edit tags is called
        THEN:
            - API returns HTTP 400
            - modify_tags is not called
        """
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id, self.doc3.id],
                    "method": "modify_tags",
                    "parameters": {
                        "add_tags": [self.t1.id],
                    },
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        m.assert_not_called()

    @mock.patch("documents.serialisers.bulk_edit.delete")
    def test_api_delete(self, m):
        m.return_value = "OK"
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {"documents": [self.doc1.id], "method": "delete", "parameters": {}},
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertEqual(args[0], [self.doc1.id])
        self.assertEqual(len(kwargs), 0)

    @mock.patch("documents.serialisers.bulk_edit.set_storage_path")
    def test_api_set_storage_path(self, m):
        """
        GIVEN:
            - API data to set the storage path of a document
        WHEN:
            - API is called
        THEN:
            - set_storage_path is called with correct document IDs and storage_path ID
        """
        m.return_value = "OK"

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_storage_path",
                    "parameters": {"storage_path": self.sp1.id},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args

        self.assertListEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["storage_path"], self.sp1.id)

    @mock.patch("documents.serialisers.bulk_edit.set_storage_path")
    def test_api_unset_storage_path(self, m):
        """
        GIVEN:
            - API data to clear/unset the storage path of a document
        WHEN:
            - API is called
        THEN:
            - set_storage_path is called with correct document IDs and None storage_path
        """
        m.return_value = "OK"

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_storage_path",
                    "parameters": {"storage_path": None},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()
        args, kwargs = m.call_args

        self.assertListEqual(args[0], [self.doc1.id])
        self.assertEqual(kwargs["storage_path"], None)

    def test_api_invalid_storage_path(self):
        """
        GIVEN:
            - API data to set the storage path of a document
            - Given storage_path ID isn't valid
        WHEN:
            - API is called
        THEN:
            - set_storage_path is called with correct document IDs and storage_path ID
        """
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_storage_path",
                    "parameters": {"storage_path": self.sp1.id + 10},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.async_task.assert_not_called()

    def test_api_set_storage_path_not_provided(self):
        """
        GIVEN:
            - API data to set the storage path of a document
            - API data is missing storage path ID
        WHEN:
            - API is called
        THEN:
            - set_storage_path is called with correct document IDs and storage_path ID
        """
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id],
                    "method": "set_storage_path",
                    "parameters": {},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.async_task.assert_not_called()

    def test_api_invalid_doc(self):
        self.assertEqual(Document.objects.count(), 5)
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps({"documents": [-235], "method": "delete", "parameters": {}}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Document.objects.count(), 5)

    def test_api_invalid_method(self):
        self.assertEqual(Document.objects.count(), 5)
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "exterminate",
                    "parameters": {},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Document.objects.count(), 5)

    def test_api_invalid_correspondent(self):
        self.assertEqual(self.doc2.correspondent, self.c1)
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "set_correspondent",
                    "parameters": {"correspondent": 345657},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        doc2 = Document.objects.get(id=self.doc2.id)
        self.assertEqual(doc2.correspondent, self.c1)

    def test_api_no_correspondent(self):
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "set_correspondent",
                    "parameters": {},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_invalid_document_type(self):
        self.assertEqual(self.doc2.document_type, self.dt1)
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "set_document_type",
                    "parameters": {"document_type": 345657},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        doc2 = Document.objects.get(id=self.doc2.id)
        self.assertEqual(doc2.document_type, self.dt1)

    def test_api_no_document_type(self):
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "set_document_type",
                    "parameters": {},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_add_invalid_tag(self):
        self.assertEqual(list(self.doc2.tags.all()), [self.t1])
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "add_tag",
                    "parameters": {"tag": 345657},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(list(self.doc2.tags.all()), [self.t1])

    def test_api_add_tag_no_tag(self):
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {"documents": [self.doc2.id], "method": "add_tag", "parameters": {}},
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_delete_invalid_tag(self):
        self.assertEqual(list(self.doc2.tags.all()), [self.t1])
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "remove_tag",
                    "parameters": {"tag": 345657},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(list(self.doc2.tags.all()), [self.t1])

    def test_api_delete_tag_no_tag(self):
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {"documents": [self.doc2.id], "method": "remove_tag", "parameters": {}},
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_modify_invalid_tags(self):
        self.assertEqual(list(self.doc2.tags.all()), [self.t1])
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "modify_tags",
                    "parameters": {
                        "add_tags": [self.t2.id, 1657],
                        "remove_tags": [1123123],
                    },
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_modify_tags_no_tags(self):
        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "modify_tags",
                    "parameters": {"remove_tags": [1123123]},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id],
                    "method": "modify_tags",
                    "parameters": {"add_tags": [self.t2.id, 1657]},
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_selection_data_empty(self):
        response = self.client.post(
            "/api/documents/selection_data/",
            json.dumps({"documents": []}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for field, Entity in [
            ("selected_correspondents", Correspondent),
            ("selected_tags", Tag),
            ("selected_document_types", DocumentType),
        ]:
            self.assertEqual(len(response.data[field]), Entity.objects.count())
            for correspondent in response.data[field]:
                self.assertEqual(correspondent["document_count"], 0)
            self.assertCountEqual(
                map(lambda c: c["id"], response.data[field]),
                map(lambda c: c["id"], Entity.objects.values("id")),
            )

    def test_api_selection_data(self):
        response = self.client.post(
            "/api/documents/selection_data/",
            json.dumps(
                {"documents": [self.doc1.id, self.doc2.id, self.doc4.id, self.doc5.id]},
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertCountEqual(
            response.data["selected_correspondents"],
            [
                {"id": self.c1.id, "document_count": 1},
                {"id": self.c2.id, "document_count": 0},
            ],
        )
        self.assertCountEqual(
            response.data["selected_tags"],
            [
                {"id": self.t1.id, "document_count": 2},
                {"id": self.t2.id, "document_count": 1},
            ],
        )
        self.assertCountEqual(
            response.data["selected_document_types"],
            [
                {"id": self.c1.id, "document_count": 1},
                {"id": self.c2.id, "document_count": 0},
            ],
        )

    @mock.patch("documents.serialisers.bulk_edit.set_permissions")
    def test_set_permissions(self, m):
        m.return_value = "OK"
        user1 = User.objects.create(username="user1")
        user2 = User.objects.create(username="user2")
        permissions = {
            "view": {
                "users": [user1.id, user2.id],
                "groups": None,
            },
            "change": {
                "users": [user1.id],
                "groups": None,
            },
        }

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id, self.doc3.id],
                    "method": "set_permissions",
                    "parameters": {"set_permissions": permissions},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        m.assert_called_once()
        args, kwargs = m.call_args
        self.assertCountEqual(args[0], [self.doc2.id, self.doc3.id])
        self.assertEqual(len(kwargs["set_permissions"]["view"]["users"]), 2)

    @mock.patch("documents.serialisers.bulk_edit.set_permissions")
    def test_insufficient_permissions_ownership(self, m):
        """
        GIVEN:
            - Documents owned by user other than logged in user
        WHEN:
            - set_permissions bulk edit API endpoint is called
        THEN:
            - User is not able to change permissions
        """
        m.return_value = "OK"
        self.doc1.owner = User.objects.get(username="temp_admin")
        self.doc1.save()
        user1 = User.objects.create(username="user1")
        self.client.force_authenticate(user=user1)

        permissions = {
            "owner": user1.id,
        }

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id, self.doc2.id, self.doc3.id],
                    "method": "set_permissions",
                    "parameters": {"set_permissions": permissions},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        m.assert_not_called()
        self.assertEqual(response.content, b"Insufficient permissions")

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc2.id, self.doc3.id],
                    "method": "set_permissions",
                    "parameters": {"set_permissions": permissions},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        m.assert_called_once()

    @mock.patch("documents.serialisers.bulk_edit.set_storage_path")
    def test_insufficient_permissions_edit(self, m):
        """
        GIVEN:
            - Documents for which current user only has view permissions
        WHEN:
            - API is called
        THEN:
            - set_storage_path only called if user can edit all docs
        """
        m.return_value = "OK"
        self.doc1.owner = User.objects.get(username="temp_admin")
        self.doc1.save()
        user1 = User.objects.create(username="user1")
        assign_perm("view_document", user1, self.doc1)
        self.client.force_authenticate(user=user1)

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id, self.doc2.id, self.doc3.id],
                    "method": "set_storage_path",
                    "parameters": {"storage_path": self.sp1.id},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        m.assert_not_called()
        self.assertEqual(response.content, b"Insufficient permissions")

        assign_perm("change_document", user1, self.doc1)

        response = self.client.post(
            "/api/documents/bulk_edit/",
            json.dumps(
                {
                    "documents": [self.doc1.id, self.doc2.id, self.doc3.id],
                    "method": "set_storage_path",
                    "parameters": {"storage_path": self.sp1.id},
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        m.assert_called_once()
