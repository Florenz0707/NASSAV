from django.test import TestCase

from nassav.models import AVResource, Actor, Genre
from nassav.serializers import ResourceSummarySerializer, ResourceSerializer


class SerializersTest(TestCase):
    def setUp(self):
        self.res = AVResource.objects.create(
            avid='TEST-001',
            title='Test Title',
            source='Jable',
            release_date='2025-01-01',
            file_exists=True,
            file_size=12345
        )
        # add relations
        a = Actor.objects.create(name='Actor1')
        g = Genre.objects.create(name='Genre1')
        self.res.actors.add(a)
        self.res.genres.add(g)

    def test_resource_summary_serializer_from_instance(self):
        ser = ResourceSummarySerializer(self.res)
        data = ser.data
        self.assertEqual(data['avid'], 'TEST-001')
        self.assertEqual(data['title'], 'Test Title')
        self.assertEqual(data['source'], 'Jable')
        self.assertTrue(data['has_video'])
        self.assertIn('metadata_create_time', data)

    def test_resource_serializer_from_metadata_dict(self):
        metadata = {
            'avid': 'TEST-002',
            'title': 'Meta Title',
            'm3u8': 'https://example.com/stream.m3u8',
            'source': 'MissAV',
            'release_date': '2025-02-02',
            'duration': 3600,
            'actors': ['A','B'],
            'genres': ['G'] ,
            'file_size': 54321,
            'file_exists': False
        }
        ser = ResourceSerializer(metadata)
        data = ser.data
        self.assertEqual(data['avid'], 'TEST-002')
        self.assertEqual(data['m3u8'], 'https://example.com/stream.m3u8')
        self.assertFalse(data['file_exists'])
