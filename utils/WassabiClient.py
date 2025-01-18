import io
import os
import pandas as pd
import boto3
import io
from botocore.exceptions import ClientError


class WasabiClient:
    def __init__(self):
        access_key = os.getenv("WASABI_ACCESS_KEY")
        secret_key = os.getenv("WASABI_SECRET_KEY")
        self.bucket = os.getenv("WASABI_BUCKET_NAME")
        self.s3_client = boto3.client(
            's3',
            endpoint_url='https://s3.eu-central-2.wasabisys.com',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def does_key_exist(self, key: str) -> bool:
        """
        Check if a given key exists in the Wasabi bucket.
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                # print(f"Unexpected error when checking key existence: {e}")
                return False

    def fetch_data(self, key: str):
        cloud_key = f"Stock_Data/{key}.csv"

        if self.does_key_exist(cloud_key):
            file_response = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
            file_content = file_response['Body'].read().decode('utf-8')  # Fix typo
            return pd.read_csv(io.StringIO(file_content))
        else:
            print(f"Error fetching data: {cloud_key}")
            return None

    def update_or_create(self, code: str, new_df: pd.DataFrame):
        cloud_key = f"Stock_Data/{code}.csv"
        try:
            existing_df = None

            if self.does_key_exist(cloud_key):
                existing_file = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
                existing_df = pd.read_csv(io.StringIO(existing_file['Body'].read().decode('utf-8')))

            combined_df = pd.concat([new_df, existing_df]).drop_duplicates() if existing_df is not None else new_df
            csv_buffer = io.StringIO()
            combined_df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            self.s3_client.put_object(Bucket=self.bucket, Key=cloud_key, Body=csv_buffer.getvalue())
            print(f"Successfully appended and uploaded data for {code}.")
        except ClientError as e:
            print(f"Error uploading data: {e}")

    def create_articles(self, code: str, df: pd.DataFrame):
        cloud_key = f"Articles/{code}.csv"

        try:
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            self.s3_client.put_object(Bucket=self.bucket, Key=cloud_key, Body=csv_buffer.getvalue())
            print(f"Successfully appended and uploaded data for {code}.")
        except ClientError as e:
            print(f"Error uploading data: {e}")

    def update_or_create_ARTICLES(self, code: str, new_df: pd.DataFrame):
        cloud_key = f"Articles/{code}.csv"
        try:
            existing_df = None

            if self.does_key_exist(cloud_key):
                existing_file = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
                existing_df = pd.read_csv(io.StringIO(existing_file['Body'].read().decode('utf-8')))

            combined_df = pd.concat([new_df, existing_df]).drop_duplicates() if existing_df is not None else new_df
            csv_buffer = io.StringIO()
            combined_df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            self.s3_client.put_object(Bucket=self.bucket, Key=cloud_key, Body=csv_buffer.getvalue())
            print(f"Successfully appended and uploaded data for {code}.")
        except ClientError as e:
            print(f"Error uploading data: {e}")

    def READ_ARTICLES(self, code: str):
        cloud_key = f"Articles/{code}.csv"
        if self.does_key_exist(cloud_key):
            file_response = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
            file_content = file_response['Body'].read().decode('utf-8')  # Fix typo
            return pd.read_csv(io.StringIO(file_content))
        else:
            print(f"Error fetching data: {cloud_key}")
            return None

    # def save_model_to_cloud(self, code: str, model):
    #     cloud_key = f"Models/{code}.keras"
    #
    #     try:
    #         # Create a temporary file
    #         with tempfile.NamedTemporaryFile(suffix=".keras", delete=True) as temp_file:
    #             # Save the model to the temporary file
    #             model.save(temp_file.name)
    #             temp_file.seek(0)  # Reset file pointer to the beginning
    #
    #             # Read the content of the temporary file into memory
    #             model_buffer = temp_file.read()
    #
    #         # Upload the file content to S3
    #         self.s3_client.put_object(Bucket=self.bucket,
    #                                   Key=cloud_key,
    #                                   Body=model_buffer,
    #                                   ContentType='application/octet-stream'
    #                                   )
    #         print(f"Successfully uploaded model for {code} to {cloud_key}.")
    #     except ClientError as e:
    #         print(f"Error uploading model: {e}")
    #     except Exception as e:
    #         print(f"Unexpected error: {e}")
    #
    # def fetch_model(self, code: str):
    #     cloud_key = f"Models/{code}.keras"
    #     if not self.does_key_exist(cloud_key):
    #         print(f"Model for {code} does not exist in Wasabi.")
    #         return None
    #
    #     try:
    #         file_response = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
    #         model_content = io.BytesIO(file_response['Body'].read())
    #
    #         # Ensure the file is not empty
    #         if model_content.getbuffer().nbytes == 0:
    #             print(f"Model for {code} is empty in Wasabi.")
    #             return None
    #
    #         # Save to temporary file
    #         with tempfile.NamedTemporaryFile(suffix=".keras", delete=True) as temp_file:
    #             temp_file.write(model_content.getvalue())
    #             temp_file.seek(0)
    #
    #             # Check if file is a valid .keras model
    #             try:
    #                 model = load_model(temp_file.name)
    #             except Exception as e:
    #                 print(f"Error loading model for {code}: {e}")
    #                 return None
    #
    #         print(f"Successfully loaded model for {code}.")
    #         return model
    #     except ClientError as e:
    #         print(f"Error fetching model: {e}")
    #         return None
    #     except Exception as e:
    #         print(f"Unexpected error: {e}")
    #         return None


def get_wassabi_client():
    global wassabi_client
    if wassabi_client is None:
        raise Exception("WasabiClient is not initialized. Check BackendConfig or initialization logic.")
    return wassabi_client


# Setter for initialization
def set_wassabi_client(client):
    global wassabi_client
    wassabi_client = client


def initialize_wasabi_client():
    return WasabiClient()


wassabi_client = None