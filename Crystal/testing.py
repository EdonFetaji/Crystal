import os
import requests

ml_module_url = 'http:/ml_module:8000'
e = 'http://localhost:8002/stock/STB/predict/5'
response = requests.get(e)

print(response.json())
