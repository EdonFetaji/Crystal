from django.urls import path
from .views import (
    home,
    stock_list,
    stock_detail,
    technical_analysis,
    fundamental_analysis,
    watchlist,
    add_to_watchlist,
    remove_from_watchlist, profile, add_to_watchlist_from_profile
)

urlpatterns = [
    path('', home, name='home'),
    path('stocks/', stock_list, name='stock_list'),
    path('stocks/<str:code>/', stock_detail, name='stock_detail'),
    path('stocks/<str:code>/technical-analysis/', technical_analysis, name='technical_analysis'),
    path('stocks/<str:code>/fundamental-analysis/', fundamental_analysis, name='fundamental_analysis'),
    path('watchlist/', watchlist, name='watchlist'),
    path('profile/', profile, name='profile'),
    path('add-to-watchlist/', add_to_watchlist_from_profile, name='add_to_watchlist_from_profile'),

    path('watchlist/add/<str:code>/', add_to_watchlist, name='add_to_watchlist'),
    path('watchlist/remove/<str:code>/', remove_from_watchlist, name='remove_from_watchlist'),
]