from django.apps import AppConfig
import utils.WassabiClient
from utils.WassabiClient import WasabiClient, wassabi_client, \
    set_wassabi_client  # Import the Client class and global client variable


class BackendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backend'

    def ready(self):
        global wassabi_client  # Use the global client variable
        if wassabi_client is None:  # Initialize only once
            set_wassabi_client(WasabiClient())  # Create a new instance of the Client class
