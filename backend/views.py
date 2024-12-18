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

# tech analysis - Oscilators
from ta.momentum import RSIIndicator
from ta.momentum import StochasticOscillator
from ta.trend import MACD
from ta.trend import CCIIndicator
from ta.volume import ChaikinMoneyFlowIndicator

# tech analusis - Moving Averages
from ta.trend import EMAIndicator
from ta.trend import SMAIndicator
from ta.trend import WMAIndicator
from ta.volume import OnBalanceVolumeIndicator
from ta.volatility import BollingerBands

load_dotenv()

# Access environment variables
access_key = os.getenv("WASABI_ACCESS_KEY")
secret_key = os.getenv("WASABI_SECRET_KEY")
bucket_name = os.getenv("WASABI_BUCKET_NAME")


# Utility function to prepare stock data from CSV

# Home view
def home(request):
    stocks = Stock.objects.all().order_by('-price')[:9]
    return render(request, 'backend/home.html', {'stocks': stocks})


# Stock list view

def stock_list(request):
    stocks = Stock.objects.all()
    paginator = Paginator(stocks, 9)  # Show 10 stocks per page
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


# @login_required()
# def profile(request):
#     all_stocks = Stock.objects.all()
#     stocks_watchlist = request.user.app_user.watchlist.all().order_by('code')
#     return render(request, 'backend/profile.html', {'stocks': stocks_watchlist, 'all_stocks': all_stocks}, )


from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def profile(request):
    all_stocks = Stock.objects.all()
    stocks_watchlist = request.user.app_user.watchlist.all().order_by('code')

    def process_stock(stock):
        df = get_stock_csv_data(stock.code)

        if df is not None and not df.empty:
            df = prepare_stock_data_analysis(df)

            # Select the latest stock data (first row after sorting)
            last = df['Last trade price'].iloc[0] if 'Last trade price' in df.columns else None
            change = df['%chg.'].iloc[0] if '%chg.' in df.columns else None
            high = df['Max'].iloc[0] if 'Max' in df.columns else None
            low = df['Min'].iloc[0] if 'Min' in df.columns else None
            time = df['Date'].iloc[0] if 'Date' in df.columns else None

            return {
                'code': stock.code,
                'last': last,
                'change': change,
                'high': high,
                'low': low,
                'time': time
            }
        else:
            return {
                'code': stock.code,
                'last': None,
                'change': None,
                'high': None,
                'low': None,
                'time': None
            }

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor() as executor:
        stock_data = list(executor.map(process_stock, stocks_watchlist))

    return render(
        request,
        'backend/profile.html',
        {
            'stocks': stock_data,
            'all_stocks': all_stocks,
        }
    )


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
    return redirect('home')


@login_required
def remove_from_watchlist(request, code):
    stock = get_object_or_404(Stock, code=code)
    request.user.app_user.watchlist.remove(stock)
    messages.success(request, f'{stock.code} removed from your watchlist.')
    return redirect('stock_detail', code=code)


def get_stock_csv_data(code):
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

        # print(pd.read_csv(io.StringIO(file_content)))

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

        return df
    except Exception as e:
        return None


# def technical_analysis(request, code):
#     try:
#         # Fetch stock data
#         df = get_stock_csv_data(code)
#         df = prepare_stock_data_analysis(df)
#         if df is None:
#             return JsonResponse({'error': 'Stock data not found'}, status=404)
#
#         # Validate required columns
#         if 'Last trade price' not in df.columns or 'Date' not in df.columns:
#             return JsonResponse({'error': 'Required columns not found in stock data'}, status=500)
#
#         # Handle missing data
#         df['Last trade price'] = df['Last trade price'].fillna(method='ffill').fillna(method='bfill')
#
#         # Calculate technical indicators
#         close_prices = df['Last trade price']
#         sma_20 = SMAIndicator(close=close_prices, window=20).sma_indicator()
#         sma_50 = SMAIndicator(close=close_prices, window=50).sma_indicator()
#         rsi = RSIIndicator(close=close_prices).rsi()
#         bollinger = BollingerBands(close=close_prices)
#         upper_band = bollinger.bollinger_hband()
#         lower_band = bollinger.bollinger_lband()
#
#         # Create Plotly figure
#         fig = make_subplots(rows=2, cols=1)
#         fig.add_trace(go.Scatter(x=df['Date'], y=close_prices, name="Price"))
#         fig.add_trace(go.Scatter(x=df['Date'], y=sma_20, name="SMA 20"))
#         fig.add_trace(go.Scatter(x=df['Date'], y=sma_50, name="SMA 50"))
#
#         # Return analysis and plot
#         return JsonResponse({
#             'plot': fig.to_json(),
#             'analysis': {
#                 'trend': {'sma20': round(sma_20.iloc[-1], 2), 'sma50': round(sma_50.iloc[-1], 2)},
#                 'momentum': {'rsi': round(rsi.iloc[-1], 2)},
#                 'volatility': {
#                     'upper_band': round(upper_band.iloc[-1], 2),
#                     'lower_band': round(lower_band.iloc[-1], 2),
#                 },
#             },
#         })
#
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return JsonResponse({'error': str(e)}, status=500)


# PLOTS FUNCTION
# def technical_analysis(request, code):
#     try:
#         df = get_stock_csv_data(code)
#         if df is None or df.empty:
#             return JsonResponse({'error': 'Stock data not found'}, status=404)
#
#         # Prepare data for analysis
#         df = prepare_stock_data_analysis(df)
#         if df is None or 'Last trade price' not in df.columns or 'Date' not in df.columns:
#             return JsonResponse({'error': 'Required columns not found in stock data'}, status=500)
#
#         # Handle missing data
#         df['Last trade price'] = df['Last trade price'].ffill().bfill()
#
#         df.sort_values('Date', inplace=True)
#         df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, format='%d.%m.%Y', errors='coerce')
#
#         # Calculate technical indicators
#         close_prices = df['Last trade price']
#         sma_20 = SMAIndicator(close=close_prices, window=20).sma_indicator()
#         sma_50 = SMAIndicator(close=close_prices, window=50).sma_indicator()
#         rsi = RSIIndicator(close=close_prices).rsi()
#         bollinger = BollingerBands(close=close_prices)
#         upper_band = bollinger.bollinger_hband()
#         lower_band = bollinger.bollinger_lband()
#
#         # Create Plotly figure
#         fig = make_subplots(rows=2, cols=1, subplot_titles=("Stock Prices with SMA", "RSI and Bollinger Bands"))
#         # Plot stock prices and moving averages
#         fig.add_trace(go.Scatter(x=df['Date'], y=close_prices, name="Price"), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df['Date'], y=sma_20, name="SMA 20"), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df['Date'], y=sma_50, name="SMA 50"), row=1, col=1)
#
#         # Plot RSI
#         fig.add_trace(go.Scatter(x=df['Date'], y=rsi, name="RSI"), row=2, col=1)
#
#         # Plot Bollinger Bands
#         fig.add_trace(go.Scatter(x=df['Date'], y=upper_band, name="Upper Band", line=dict(dash='dash')), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df['Date'], y=lower_band, name="Lower Band", line=dict(dash='dash')), row=1, col=1)
#
#         # Update layout
#         fig.update_layout(height=800, width=1200, title_text=f"Technical Analysis for {code}")
#
#         # Return analysis and plot
#         return JsonResponse({
#             'plot': fig.to_json(),
#             'analysis': {
#                 'trend': {'sma20': round(sma_20.iloc[-1], 2), 'sma50': round(sma_50.iloc[-1], 2)},
#                 'momentum': {'rsi': round(rsi.iloc[-1], 2)},
#                 'volatility': {
#                     'upper_band': round(upper_band.iloc[-1], 2),
#                     'lower_band': round(lower_band.iloc[-1], 2),
#                 },
#             },
#         })
#
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         return JsonResponse({'error': str(e)}, status=500)

# TABLE VIEW FUNCTION


def technical_analysis(request, code):
    try:
        # Fetch and prepare stock data
        df = get_stock_csv_data(code)
        if df is None or df.empty:
            return JsonResponse({'error': f"No data found for stock: {code}"}, status=404)

        df = prepare_stock_data_analysis(df)
        df['Last trade price'] = df['Last trade price'].ffill().bfill()

        # Define ranges
        ranges = {
            '1d': df.iloc[:1],
            '1w': df.iloc[:7],
            '1m': df.iloc[:30]
        }

        response = {}

        for range_label, data in ranges.items():
            if data.empty:
                response[range_label] = {metric: 'N/A' for metric in [
                    'rsi', 'Stochastic Oscillator', 'MACD', 'CCI', 'Chaikin Oscillator',
                    'EMA', 'SMA', 'WMA', 'OBV', 'Bollinger upper band',
                    'Bollinger lower band', 'Bollinger middle'
                ]}
                continue

            # Prepare metrics
            close_prices = data['Last trade price']
            high_prices = data['Max']
            low_prices = data['Min']
            volume_data = data['Volume']

            # Calculate indicators
            window_size = {'1d': 1, '1w': 7, '1m': 30}[range_label]
            indicators = {
                'rsi': RSIIndicator(close=close_prices, window=window_size).rsi(),
                'Stochastic_Oscillator': StochasticOscillator(close=close_prices, high=high_prices, low=low_prices, window=window_size).stoch(),
                'MACD': MACD(close=close_prices, window_slow=26, window_fast=12, window_sign=9).macd(),
                'CCI': CCIIndicator(high=high_prices, low=low_prices, close=close_prices, window=window_size).cci(),
                'Chaikin Oscillator': ChaikinMoneyFlowIndicator(close=close_prices, high=high_prices, low=low_prices, volume=volume_data, window=window_size).chaikin_money_flow(),
                'EMA': EMAIndicator(close=close_prices, window=window_size).ema_indicator(),
                'SMA': SMAIndicator(close=close_prices, window=window_size).sma_indicator(),
                'OBV': OnBalanceVolumeIndicator(close=close_prices, volume=volume_data).on_balance_volume(),
                'Bollinger_upper_band': BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_hband(),
                'Bollinger_lower_band': BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_lband(),
                'Bollinger_middle': BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_mavg(),
            }

            # Add non-NaN results to the response
            response[range_label] = {key: value.dropna().tolist() if not value.dropna().empty else 'N/A' for key, value in indicators.items()}

        # Return response as JSON
        print(response)
        return JsonResponse({'analysis': response})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f"An error occurred: {str(e)}"}, status=500)


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
