from django.core.management.base import BaseCommand
from pathlib import Path
import json
from django.utils import timezone


class Command(BaseCommand):
    help = '检查数据库（AVResource）与磁盘文件（cover/mp4）的一致性，并可选地修复 DB 字段。'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='将修复写回数据库')
        parser.add_argument('--limit', type=int, default=None, help='仅处理前 N 条记录')
        parser.add_argument('--report', type=str, default=None, help='写入 JSON 报告文件路径')

    def handle(self, *args, **options):
        from nassav.models import AVResource
        from django.conf import settings
        from django.db import transaction

        apply_changes = options.get('apply', False)
        limit = options.get('limit')
        report_path = options.get('report')

        qs = AVResource.objects.all().order_by('id')
        total = qs.count()
        if limit:
            qs = qs[:limit]

        summary = {'total': total, 'checked': 0, 'fixed': 0, 'errors': []}
        details = []

        cover_root = Path(settings.COVER_DIR)
        video_root = Path(settings.VIDEO_DIR)

        for obj in qs:
            try:
                avid = obj.avid
                mp4_path = video_root / f"{avid}.mp4"
                cover_path = cover_root / (obj.cover_filename or f"{avid}.jpg")

                mp4_exists = mp4_path.exists()
                cover_exists = cover_path.exists()
                mp4_size = mp4_path.stat().st_size if mp4_exists else None

                item = {
                    'avid': avid,
                    'db_file_exists': obj.file_exists,
                    'mp4_exists': mp4_exists,
                    'db_file_size': obj.file_size,
                    'mp4_size': mp4_size,
                    'cover_exists': cover_exists,
                }

                # Determine discrepancies
                discrepancies = []
                if bool(obj.file_exists) != bool(mp4_exists):
                    discrepancies.append('file_exists_mismatch')
                if mp4_exists and obj.file_size != mp4_size:
                    discrepancies.append('file_size_mismatch')

                item['discrepancies'] = discrepancies

                if discrepancies and apply_changes:
                    try:
                        with transaction.atomic():
                            obj.file_exists = bool(mp4_exists)
                            obj.file_size = mp4_size
                            if mp4_exists:
                                obj.video_saved_at = timezone.now()
                            else:
                                obj.video_saved_at = None
                            obj.save(update_fields=['file_exists', 'file_size', 'video_saved_at'])
                            item['fixed'] = True
                            summary['fixed'] += 1
                    except Exception as e:
                        item['fixed'] = False
                        item['error'] = str(e)
                        summary['errors'].append({'avid': avid, 'error': str(e)})
                else:
                    item['fixed'] = False

                details.append(item)
                summary['checked'] += 1

            except Exception as e:
                summary['errors'].append({'avid': getattr(obj, 'avid', None), 'error': str(e)})

        result = {'summary': summary, 'details_sample': details[:200]}

        if report_path:
            try:
                with open(report_path, 'w', encoding='utf-8') as rf:
                    json.dump(result, rf, ensure_ascii=False, indent=2)
                self.stdout.write(self.style.SUCCESS(f'Report written to {report_path}'))
            except Exception as e:
                self.stderr.write(f'Failed to write report: {e}')

        self.stdout.write(self.style.SUCCESS(
            f"Checked: {summary['checked']}, Fixed: {summary['fixed']}, Errors: {len(summary['errors'])}"))
