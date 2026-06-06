print("SCRIPT STARTED")
import ee

SERVICE_ACCOUNT = "urban-climate-service@ee-amarachipeaceukoha.iam.gserviceaccount.com"

credentials = ee.ServiceAccountCredentials(
    SERVICE_ACCOUNT,
    "ee-amarachipeaceukoha-8f5ff19c8810.json"   
)

ee.Initialize(credentials)

print("Earth Engine Connected Successfully!")

image = ee.Image("USGS/SRTMGL1_003")

print(
    image.getInfo()["type"]
)