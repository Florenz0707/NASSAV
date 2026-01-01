from django.test import TestCase
from rest_framework.test import APIClient

from nassav.models import AVResource, Actor


class ActorsAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        # create actors
        a1 = Actor.objects.create(name='Alice')
        a2 = Actor.objects.create(name='Bob')

        # create resources and link actors
        r1 = AVResource.objects.create(avid='ACT-1', title='With Alice', source='S1', file_exists=True)
        r1.actors.add(a1)

        r2 = AVResource.objects.create(avid='ACT-2', title='With Bob', source='S1', file_exists=False)
        r2.actors.add(a2)

        r3 = AVResource.objects.create(avid='ACT-3', title='Alice and Bob', source='S2', file_exists=True)
        r3.actors.add(a1, a2)

    def test_actor_filter_by_name(self):
        resp = self.client.get('/nassav/api/resources/', {'actor': 'Alice'})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        names = [item['title'] for item in body['data']]
        self.assertTrue(any('Alice' in n for n in names))

    def test_actor_filter_by_id(self):
        alice = Actor.objects.get(name='Alice')
        resp = self.client.get('/nassav/api/resources/', {'actor': str(alice.id)})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        # should include both resources linked to Alice
        self.assertGreaterEqual(len(body['data']), 2)

    def test_actors_list_api(self):
        resp = self.client.get('/nassav/api/actors/', {'page_size': 10, 'page': 1})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body['code'], 200)
        self.assertIsInstance(body['data'], list)
        # Each actor entry should contain resource_count
        for item in body['data']:
            self.assertIn('resource_count', item)
