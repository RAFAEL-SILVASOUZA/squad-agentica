from minio import Minio

# Test anonymous access (should fail)
try:
    c = Minio('garage:3900', secure=False)
    buckets = c.list_buckets()
    print('ERROR: Anonymous access should be denied')
except Exception as e:
    print('OK: Anonymous access denied:', type(e).__name__)
