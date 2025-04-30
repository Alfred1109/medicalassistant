import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NWYwNmM3NjZiYTMyYjA0NTk5ODVkNmUiLCJleHAiOjE3MjM0OTA4ODEsImVtYWlsIjoiYWRtaW5AZXhhbXBsZS5jb20iLCJyb2xlIjoiYWRtaW4iLCJwZXJtaXNzaW9ucyI6W119.SiXF9pxoJtlndIRgmqqKFCgq-7dM1U4EYiUOCrMF9j8"
headers = {"Authorization": f"Bearer {token}"}

response = requests.get("http://localhost:5502/api/admin/doctors", headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")
