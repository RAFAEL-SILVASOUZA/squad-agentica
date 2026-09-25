from minio import Minio

c = Minio('garage:3900', access_key='adminkey01', secret_key='change-me-in-prod', secure=False)
buckets = c.list_buckets()
print('Buckets:', [b.name for b in buckets])

# Test PUT/GET
test_key = 'test-object.txt'
test_content = b'Hello, Garage!'
c.put_object('agents', test_key, __import__('io').BytesIO(test_content), len(test_content))
response = c.get_object('agents', test_key)
content = response.read()
print('PUT/GET OK:', content.decode())
response.close()
response.release_conn()
c.remove_object('agents', test_key)
print('Object removed')
