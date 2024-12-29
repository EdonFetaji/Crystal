import io
import json
import logging
import os
from ast import Index
from datetime import datetime, timedelta

import boto3
import pandas as pd
import numpy as np
import ta.trend

from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

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

from utils.WassabiClient import get_wassabi_client, WasabiClient
from django.contrib.auth.decorators import login_required
from concurrent.futures import ThreadPoolExecutor
import asyncio
import aiohttp
from django.utils.decorators import method_decorator



CloudClient: WasabiClient = get_wassabi_client()


# Home view
def home(request):
    stocks = Stock.objects.all().order_by('-price')[:9]
    return render(request, 'backend/home.html', {'stocks': stocks})


# Stock list view

def stock_list(request):
    query = request.GET.get('stock_code')
    stocks = Stock.objects.all()

    if query:
        stocks = stocks.filter(code__contains=query)

    paginator = Paginator(stocks, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'backend/stock_list.html', {'page_obj': page_obj, 'all_stocks': Stock.objects.all()})


# Stock detail view
def stock_detail(request, code):
    stock = get_object_or_404(Stock, code=code)
    return render(request, 'backend/stock_detail.html', {'stock': stock})


def historical_data(request, code):
    df = CloudClient.fetch_data(code)
    if df is None or df.empty:
        return JsonResponse({'error': f"No data found for stock: {code}"}, status=404)

    df = prepare_stock_data_analysis(df)
    df['Last trade price'] = df['Last trade price'].ffill().bfill()
    df.rename(columns={
        'Last trade price': 'Last_trade_price',
        'Avg. Price': 'Avg_price',
        '%chg.': 'change'
    }, inplace=True)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        df['Date'] = pd.to_datetime(df['Date'])
        filtered_df = df[(df['Date'] >= start_date) & (df['Date'] <= end_date)]
        filtered_df['Date'] = pd.to_datetime(filtered_df['Date']).dt.strftime('%d.%m.%Y')
    else:
        df['Date'] = pd.to_datetime(df['Date'])
        current_date = datetime.now()
        one_month_ago = current_date - timedelta(days=30)  # Adjust for exact one-month calculation if needed

        # Filter the DataFrame
        filtered_df = df[(df['Date'] >= one_month_ago) & (df['Date'] <= current_date)]
        filtered_df['Date'] = pd.to_datetime(filtered_df['Date']).dt.strftime('%d.%m.%Y')

    stock = get_object_or_404(Stock, code=code)

    return render(request, 'backend/historical_data.html', {
        'historical_data': filtered_df.to_dict('records'),
        'stock': stock
    })

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


def process_stock(stock):
    """Process individual stock data"""
    try:
        df = CloudClient.fetch_data(stock.code)
        if df is not None and not df.empty:
            df = prepare_stock_data_analysis(df)
            return {
                'code': stock.code,
                'last': df['Last trade price'].iloc[0] if 'Last trade price' in df.columns else None,
                'change': df['%chg.'].iloc[0] if '%chg.' in df.columns else None,
                'max': df['Max'].iloc[0] if 'Max' in df.columns else None,
                'min': df['Min'].iloc[0] if 'Min' in df.columns else None,
                'time': df['Date'].iloc[0] if 'Date' in df.columns else None
            }
    except Exception as e:
        print(f"Error fetching data for {stock.code}: {str(e)}")

    return {
        'code': stock.code,
        'last': None,
        'change': None,
        'max': None,
        'min': None,
        'time': None
    }


@login_required
def profile(request):
    all_stocks = Stock.objects.all()
    stocks_watchlist = list(request.user.app_user.watchlist.all().order_by('code'))

    with ThreadPoolExecutor(max_workers=10) as executor:
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
    referrer = request.META.get('HTTP_REFERER', None)
    return redirect(referrer)


@login_required
def remove_from_watchlist(request, code):
    stock = get_object_or_404(Stock, code=code)
    request.user.app_user.watchlist.remove(stock)
    messages.success(request, f'{stock.code} removed from your watchlist.')
    return redirect('stock_detail', code=code)


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


def hull_moving_average(close_prices, window_size):
    if window_size < 1:
        raise ValueError("Window size must be greater than or equal to 1.")

    ema1_indicator = EMAIndicator(close=close_prices, window=window_size)
    ema1 = ema1_indicator.ema_indicator()  # Get the EMA values

    ema2_indicator = EMAIndicator(ema1, window_size // 2)
    ema2 = ema2_indicator.ema_indicator()  # Get the EMA values for the second EMA

    hma = (2 * ema1 - ema2).apply(lambda x: x ** 0.5)  # Ensure the result is a numeric value
    return hma


def kama(close_prices, window_size, sensitivity=2):
    time_period = window_size / sensitivity
    ema1 = close_prices.ewm(span=window_size, min_periods=1, adjust=False).mean()
    ema2 = close_prices.ewm(span=time_period, min_periods=1, adjust=False).mean()

    kama_values = ema1 + (ema2 - ema1) / (1 + sensitivity)

    return kama_values


def technical_analysis(request, code):
    try:

        df = CloudClient.fetch_data(code)
        # df = get_stock_csv_data(code)
        if df is None or df.empty:
            return JsonResponse({'error': f"No data found for stock: {code}"}, status=404)

        df = prepare_stock_data_analysis(df)
        df['Last trade price'] = df['Last trade price'].ffill().bfill()

        ranges = {
            '1d': df.iloc[:1],
            '1w': df.iloc[:7],
            '1m': df.iloc[:30]
        }

        response = {}

        for range_label, data in ranges.items():
            if data.empty:
                response[range_label] = {metric: 'N/A' for metric in [
                    'rsi', 'Stochastic_Oscillator', 'MACD', 'CCI', 'Chaikin_Oscillator',
                    'EMA', 'SMA', 'WMA', 'OBV', 'Bollinger_upper_band',
                    'Bollinger_lower_band', 'Bollinger_middle_band', 'signal'
                ]}
                continue

            close_prices = data['Last trade price']
            high_prices = data['Max']
            low_prices = data['Min']
            volume_data = data['Volume']

            window_size = {'1d': 1, '1w': 7, '1m': 30}[range_label]
            indicators = {
                'rsi': RSIIndicator(close=close_prices, window=window_size).rsi(),
                'Stochastic_Oscillator': StochasticOscillator(close=close_prices, high=high_prices, low=low_prices,
                                                              window=window_size).stoch(),
                'MACD': MACD(close=close_prices, window_slow=26, window_fast=12, window_sign=9).macd(),
                'CCI': CCIIndicator(high=high_prices, low=low_prices, close=close_prices, window=window_size).cci(),
                'Chaikin_Oscillator': ChaikinMoneyFlowIndicator(close=close_prices, high=high_prices, low=low_prices,
                                                                volume=volume_data,
                                                                window=window_size).chaikin_money_flow(),
                'EMA': EMAIndicator(close=close_prices, window=window_size).ema_indicator(),
                'SMA': SMAIndicator(close=close_prices, window=window_size).sma_indicator(),
                'OBV': OnBalanceVolumeIndicator(close=close_prices, volume=volume_data).on_balance_volume(),
                'Bollinger_upper_band': BollingerBands(close=close_prices, window=window_size,
                                                       window_dev=2).bollinger_hband(),
                'Bollinger_lower_band': BollingerBands(close=close_prices, window=window_size,
                                                       window_dev=2).bollinger_lband(),
                'Bollinger_middle_band': BollingerBands(close=close_prices, window=window_size,
                                                        window_dev=2).bollinger_mavg(),
                'WMA': ta.trend.wma_indicator(close_prices),
                'KAMA': kama(close_prices, window_size + 1),
                'VMA': (close_prices * volume_data).cumsum() / df['Volume'].cumsum(),
                'date': data['Date']
            }

            # Determine signal
            rsi = indicators['rsi'].iloc[-1] if not indicators['rsi'].isna().all() else None
            bollinger_upper = indicators['Bollinger_upper_band'].iloc[-1] if not indicators[
                'Bollinger_upper_band'].isna().all() else None
            bollinger_lower = indicators['Bollinger_lower_band'].iloc[-1] if not indicators[
                'Bollinger_lower_band'].isna().all() else None
            close_price = close_prices.iloc[-1]

            if rsi and bollinger_upper and bollinger_lower:
                if rsi > 70 or close_price >= bollinger_upper:
                    signal = "Sell"
                elif rsi < 30 or close_price <= bollinger_lower:
                    signal = "Buy"
                else:
                    signal = "Hold"
            else:
                signal = "Hold"

            response[range_label] = {key: value.dropna().tolist() if not value.dropna().empty else 'N/A' for key, value
                                     in indicators.items()}
            response[range_label]['signal'] = signal
            print(response)

        # print(df.to_dict(orient='records'))

        return JsonResponse({
            'analysis': response,
            'historical_data': df[['Date', 'Last trade price']].to_dict(orient='records')
        })
        # return JsonResponse({'analysis': response})

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
    df = CloudClient.fetch_data(code)
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
