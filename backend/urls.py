from django.urls import path
from .views import (
    home,
    stock_list,
    stock_detail,
    technical_analysis,
    watchlist,
    add_to_watchlist,
    remove_from_watchlist,
    profile,
    add_to_watchlist_from_profile,
    historical_data,
    sentiment_analysis,
    predictions,
    predictions_base,
)

urlpatterns = [
    path('', home, name='home'),
    path('stocks/', stock_list, name='stock_list'),
    path('stocks/predictions_base/', predictions_base, name='predictions_base'),  # Moved above stock_detail
    path('stocks/<str:code>/', stock_detail, name='stock_detail'),
    path('stocks/historical_data/<str:code>/', historical_data, name='historical_data'),
    path('stocks/predictions/<str:code>/', predictions, name='predictions'),
    path('stocks/<str:code>/technical-analysis/', technical_analysis, name='technical_analysis'),
    path('stocks/<str:code>/sentiment-analysis/', sentiment_analysis, name='sentiment_analysis'),
    path('watchlist/', watchlist, name='watchlist'),
    path('profile/', profile, name='profile'),
    path('add-to-watchlist/', add_to_watchlist_from_profile, name='add_to_watchlist_from_profile'),
    path('watchlist/add/<str:code>/', add_to_watchlist, name='add_to_watchlist'),
    path('watchlist/remove/<str:code>/', remove_from_watchlist, name='remove_from_watchlist'),
]
