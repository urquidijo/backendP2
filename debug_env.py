import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
import django
django.setup()
from django.conf import settings
print("bucket", settings.AWS_S3_BUCKET_NAME)
print("region", settings.AWS_REGION)
print("has key", bool(settings.AWS_ACCESS_KEY_ID))
print("has secret", bool(settings.AWS_SECRET_ACCESS_KEY))
