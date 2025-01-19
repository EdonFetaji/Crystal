import io
import json
import logging
import os
from ast import Index
from datetime import datetime, timedelta
import boto3
import pandas as pd
from utils.StockTechnicalAnalyzer import StockTechnicalAnalyzer
from .models import Stock
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.core.management import call_command
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from utils.WassabiClient import get_wassabi_client, WasabiClient
from django.contrib.auth.decorators import login_required
from concurrent.futures import ThreadPoolExecutor
import os
import requests

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

    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)

    if start_date and end_date:
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)

        filtered_df = df.loc[(df['Date'] >= start_date) & (df['Date'] <= end_date)].copy()
        filtered_df['Date'] = filtered_df['Date'].dt.strftime('%d.%m.%Y')
    else:
        current_date = datetime.now()
        one_month_ago = current_date - timedelta(days=30)

        filtered_df = df.loc[(df['Date'] >= one_month_ago) & (df['Date'] <= current_date)].copy()
        filtered_df['Date'] = filtered_df['Date'].dt.strftime('%d.%m.%Y')

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


def technical_analysis(request, code):
    try:

        df = CloudClient.fetch_data(code)
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
                'rsi': StockTechnicalAnalyzer.calculate_RSI_indicator(close_prices, window_size),
                'Stochastic_Oscillator': StockTechnicalAnalyzer.calculate_Stochastic_Oscillator_indicator(close_prices,
                                                                                                          high_prices,
                                                                                                          low_prices,
                                                                                                          window_size),
                'MACD': StockTechnicalAnalyzer.calculate_MACD_indicator(close_prices),
                'CCI': StockTechnicalAnalyzer.calculate_CCI_indicator(high_prices, low_prices, close_prices,
                                                                      window_size),
                'Chaikin_Oscillator': StockTechnicalAnalyzer.calculate_Chaikin_money_flow(close_prices, high_prices,
                                                                                          low_prices, volume_data,
                                                                                          window_size),
                'EMA': StockTechnicalAnalyzer.calculate_EMA_indicator(close_prices, window_size),
                'SMA': StockTechnicalAnalyzer.calculate_SMA_indicator(close_prices, window_size),
                'WMA': StockTechnicalAnalyzer.calculate_WMA_indicator(close_prices),
                'KAMA': StockTechnicalAnalyzer.calculate_Kama_indicator(close_prices, window_size + 1),
                'OBV': StockTechnicalAnalyzer.calculate_OBV_indicator(close_prices, volume_data),
                'Bollinger_upper_band': StockTechnicalAnalyzer.calculate_Bollinger_upper_band(close_prices,
                                                                                              window_size),
                'Bollinger_lower_band': StockTechnicalAnalyzer.calculate_Bollinger_lower_band(close_prices,
                                                                                              window_size),
                'Bollinger_middle_band': StockTechnicalAnalyzer.calculate_Bollinger_middle_band(close_prices,
                                                                                                window_size),
                'VMA': StockTechnicalAnalyzer.calculate_VMA_indicator(close_prices, volume_data),
                'date': data['Date']
            }

            rsi = indicators['rsi'].iloc[-1] if not indicators['rsi'].isna().all() else None
            bollinger_upper = indicators['Bollinger_upper_band'].iloc[-1] if not indicators[
                'Bollinger_upper_band'].isna().all() else None
            bollinger_lower = indicators['Bollinger_lower_band'].iloc[-1] if not indicators[
                'Bollinger_lower_band'].isna().all() else None
            close_price = close_prices.iloc[-1]

            signal = StockTechnicalAnalyzer.determine_signal(rsi, bollinger_upper, bollinger_lower, close_price)

            response[range_label] = {key: value.dropna().tolist() if not value.dropna().empty else 'N/A' for key, value
                                     in indicators.items()}
            response[range_label]['signal'] = signal

        sentiment_df = CloudClient.READ_ARTICLES(str(code))

        return JsonResponse({
            'analysis': response if response is not None else {},
            'historical_data': (
                df[['Date', 'Last trade price']].to_dict(orient='records')
                if df is not None
                else []
            ),
            'sentiment_analysis': (
                sentiment_df.to_dict(orient='records')
                if sentiment_df is not None
                else []
            )
        }, status=200)


    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f"An error occurred: {str(e)}"}, status=500)


def sentiment_analysis(request, code):
    print('anything bro')
    df = CloudClient.fetch_articles(code.code)
    return JsonResponse({
        'sentiment_data': df.to_dict(orient='records')
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


def predictions(request, code):


    ml_module_url = 'http://ml_module:8000'
    endpoint = f"{ml_module_url}/stock/ALK/predict/1"
    response = requests.get(endpoint)

    print(response.json())

    return render(request, 'backend/predictions.html', {'code': code})


def predictions_base(request):

    query = request.GET.get('stock_code')
    stocks = Stock.objects.all()


    return render(request, 'backend/predictions_base.html', {'stocks': stocks})
