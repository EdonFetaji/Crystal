import io
import os
import boto3
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()


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

    def fetch_data(self, key: str):
        cloud_key = f"Stock_Data/{key}.csv"

        try:
            file_response = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
            file_content = file_response['Body'].read().decode('utf-8')  # Fix typo
            return pd.read_csv(io.StringIO(file_content))
        except ClientError as e:
            print(f"Error fetching data: {e}")
            return None

    def update_or_create(self, code: str, new_df: pd.DataFrame):
        cloud_key = f"Stock_Data/{code}.csv"

        try:
            try:
                existing_file = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
                existing_df = pd.read_csv(io.StringIO(existing_file['Body'].read().decode('utf-8')))
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchKey':
                    existing_df = None
                else:
                    print(f"Error fetching existing data: {e}")
                    return False

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


    def fetch_articles(self, code: str):
        cloud_key = f"Articles/{code}.csv"
        try:
            file_response = self.s3_client.get_object(Bucket=self.bucket, Key=cloud_key)
            file_content = file_response['Body'].read().decode('utf-8')  # Fix typo
            return pd.read_csv(io.StringIO(file_content))
        except ClientError as e:
            print(f"Error fetching data: {e}")
            return None

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
