from django.test import TestCase
from rest_framework.test import APIClient
from nassav.models import AVResource


class ResourcesListTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # create several resources
        AVResource.objects.create(avid='A-1', title='A1', source='S1', file_exists=True)
        AVResource.objects.create(avid='A-2', title='A2', source='S2', file_exists=False)
        AVResource.objects.create(avid='B-1', title='B1', source='S1', file_exists=True)

    def test_resources_list_no_filter(self):
        resp = self.client.get('/nassav/api/resources/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        self.assertIsInstance(body['data'], list)
        self.assertGreaterEqual(len(body['data']), 3)

    def test_resources_filter_file_exists(self):
        resp = self.client.get('/nassav/api/resources/', {'file_exists': 'true'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all(item['has_video'] for item in body['data']))

    def test_resources_filter_source(self):
        resp = self.client.get('/nassav/api/resources/', {'source': 'S2'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(all(item['source'] == 'S2' for item in body['data']))

    def test_resources_pagination(self):
        resp = self.client.get('/nassav/api/resources/', {'page_size': 1, 'page': 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body['data']), 1)
