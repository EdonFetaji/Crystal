import io
import json
import os
from ast import Index

import boto3
import pandas as pd
from aiohttp.web_exceptions import HTTPResetContent
from django.db.models.fields import return_None

from .models import Stock
from django.conf import settings
from ta.trend import SMAIndicator
import plotly.graph_objects as go
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from plotly.subplots import make_subplots
from botocore.exceptions import ClientError
from django.core.paginator import Paginator
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required

from dotenv import load_dotenv

load_dotenv()

# Access environment variables
access_key = os.getenv("WASABI_ACCESS_KEY")
secret_key = os.getenv("WASABI_SECRET_KEY")
bucket_name = os.getenv("WASABI_BUCKET_NAME")


# Utility function to prepare stock data from CSV

# Home view
def home(request):
    stocks = Stock.objects.all().order_by('code')[:10]
    return render(request, 'backend/home.html', {'stocks': stocks})


# Stock list view

def stock_list(request):
    stocks = Stock.objects.all()
    paginator = Paginator(stocks, 10)  # Show 10 stocks per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'backend/stock_list.html', {'page_obj': page_obj})



# Stock detail view
def stock_detail(request, code):
    stock = get_object_or_404(Stock, code=code)
    return render(request, 'backend/stock_detail.html', {'stock': stock})


# Helper function for fetching analysis data
def fetch_analysis_data(request, key, analysis_function):
    try:
        response = analysis_function(request, key)
        return json.loads(response.content) if response.status_code == 200 else None
    except Exception as e:
        print(f"Error fetching analysis data: {e}")
        return None


# Watchlist views
@login_required
def watchlist(request):
    stocks = request.user.app_user.watchlist.all().order_by('code')
    return render(request, 'backend/watchlist.html', {'stocks': stocks})


@login_required()
def profile(request):
    all_stocks = Stock.objects.all()
    stocks_watchlist = request.user.app_user.watchlist.all().order_by('code')
    return render(request, 'backend/profile.html', {'stocks': stocks_watchlist, 'all_stocks': all_stocks}, )


@login_required
def add_to_watchlist_from_profile(request):
    if request.method == "POST":
        stock_code = request.POST.get('stock_code')
        stock = Stock.objects.filter(code=stock_code).first()

        if stock:
            request.user.app_user.watchlist.add(stock)
            messages.success(request, f"{stock.code} has been added to your watchlist.")
        else:
            messages.error(request, "Stock not found. Please check the symbol.")

    return redirect('profile')


@login_required
def add_to_watchlist(request, code):
    stock = get_object_or_404(Stock, code=code)
    request.user.app_user.watchlist.add(stock)
    messages.success(request, f'{stock.code} added to your watchlist.')
    return redirect('stock_detail', code=code)


@login_required
def remove_from_watchlist(request, code):
    stock = get_object_or_404(Stock, code=code)
    request.user.app_user.watchlist.remove(stock)
    messages.success(request, f'{stock.code} removed from your watchlist.')
    return redirect('stock_detail', code=code)


def get_stock_csv_data(code):
    """
    Fetches stock historical data from a Wasabi S3 bucket and returns it as a Pandas DataFrame.

    Args:
        code (str): Stock code used to fetch the corresponding CSV file.

    Returns:
        pd.DataFrame or None: DataFrame containing stock data if successful, None otherwise.
    """
    cloud_key = f"Stock_Data/{code}.csv"
    s3 = boto3.client(
        's3',
        endpoint_url='https://s3.eu-central-2.wasabisys.com',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )
    try:
        # Attempt to fetch the file from the S3 bucket
        file_response = s3.get_object(Bucket=bucket_name, Key=cloud_key)
        file_content = file_response['Body'].read().decode('utf-8')

        # Load the content into a Pandas DataFrame
        return pd.read_csv(io.StringIO(file_content))

    except ClientError as e:
        # Log the error (optional) and return None if an error occurs
        print(f"Error fetching data: {e}")
        return None


def prepare_stock_data_analysis(df):
    try:
        numeric_columns = [
            'Last trade price', 'Max', 'Min', 'Avg. Price',
            '%chg.', 'Volume', 'Turnover in BEST in denars', 'Total turnover in denars'
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('.', '').str.replace(',', '.').astype(float)

        return df.sort_values('Date', ascending=False)  # Sort by date
    except Exception as e:
        return None


def technical_analysis(request, code):
    try:
        # Fetch stock data
        df = get_stock_csv_data(code)
        df = prepare_stock_data_analysis(df)
        if df is None:
            return JsonResponse({'error': 'Stock data not found'}, status=404)

        # Validate required columns
        if 'Last trade price' not in df.columns or 'Date' not in df.columns:
            return JsonResponse({'error': 'Required columns not found in stock data'}, status=500)

        # Handle missing data
        df['Last trade price'] = df['Last trade price'].fillna(method='ffill').fillna(method='bfill')

        # Calculate technical indicators
        close_prices = df['Last trade price']
        sma_20 = SMAIndicator(close=close_prices, window=20).sma_indicator()
        sma_50 = SMAIndicator(close=close_prices, window=50).sma_indicator()
        rsi = RSIIndicator(close=close_prices).rsi()
        bollinger = BollingerBands(close=close_prices)
        upper_band = bollinger.bollinger_hband()
        lower_band = bollinger.bollinger_lband()

        # Create Plotly figure
        fig = make_subplots(rows=2, cols=1)
        fig.add_trace(go.Scatter(x=df['Date'], y=close_prices, name="Price"))
        fig.add_trace(go.Scatter(x=df['Date'], y=sma_20, name="SMA 20"))
        fig.add_trace(go.Scatter(x=df['Date'], y=sma_50, name="SMA 50"))

        # Return analysis and plot
        return JsonResponse({
            'plot': fig.to_json(),
            'analysis': {
                'trend': {'sma20': round(sma_20.iloc[-1], 2), 'sma50': round(sma_50.iloc[-1], 2)},
                'momentum': {'rsi': round(rsi.iloc[-1], 2)},
                'volatility': {
                    'upper_band': round(upper_band.iloc[-1], 2),
                    'lower_band': round(lower_band.iloc[-1], 2),
                },
            },
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


def fundamental_analysis(request, code):
    def calculate_price_trends(df):
        """
        Calculate price trends including percentage change over time.
        """
        df["Price Change"] = df["Last trade price"].pct_change() * 100
        return df

    def calculate_turnover_trends(df):
        """
        Analyze turnover trends.
        """
        avg_turnover = df["Total turnover in denars"].mean()
        max_turnover = df["Total turnover in denars"].max()
        min_turnover = df["Total turnover in denars"].min()

        return {
            "Average Turnover": avg_turnover,
            "Maximum Turnover": max_turnover,
            "Minimum Turnover": min_turnover
        }

    def volume_analysis(df):
        """
        Analyze trading volume trends.
        """
        total_volume = df["Volume"].sum()
        avg_volume = df["Volume"].mean()
        max_volume = df["Volume"].max()
        min_volume = df["Volume"].min()

        return {
            "Total Volume": total_volume,
            "Average Volume": avg_volume,
            "Maximum Volume": max_volume,
            "Minimum Volume": min_volume
        }

    def volatility_analysis(df):
        """
        Calculate volatility using the range of Max and Min prices.
        """
        df["Volatility"] = df["Max"] - df["Min"]
        avg_volatility = df["Volatility"].mean()
        return {
            "Average Volatility": avg_volatility
        }

    # Perform Fundamental Analysis
    df = get_stock_csv_data(code)
    df = prepare_stock_data_analysis(df)
    df['Last trade price'] = df['Last trade price'].fillna(method='ffill').fillna(method='bfill')
    df = calculate_price_trends(df)
    turnover_trends = calculate_turnover_trends(df)
    volume_trends = volume_analysis(df)
    volatility = volatility_analysis(df)

    return JsonResponse({
        'turnover_trends': turnover_trends,
        'volume_trends': volume_trends,
        'volatility': volatility,
    })


# Admin-specific populate stocks
@staff_member_required
@csrf_exempt
def populate_stocks(request):
    if request.method == 'POST':
        try:
            call_command('populate_stocks')
            return JsonResponse({'message': 'Stocks populated successfully!'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=400)
