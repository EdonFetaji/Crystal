import os
import requests

ml_module_url = os.getenv('ML_MODULE_URL')
endpoint = f"{ml_module_url}/stock/ALK/predict/1"
response = requests.get(endpoint)

print(response.json())