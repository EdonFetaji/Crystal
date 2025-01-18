import ta
import ta.trend
from ta.trend import (EMAIndicator, SMAIndicator, MACD)
from ta.momentum import (RSIIndicator, StochasticOscillator)
from ta.volume import (OnBalanceVolumeIndicator, ChaikinMoneyFlowIndicator)
from ta.volatility import BollingerBands
from ta.trend import CCIIndicator


class StockTechnicalAnalyzer:
    def __init__(self):
        pass

    @staticmethod
    def calculate_Hull_Moving_Average_Indicator(close_prices, window_size):
        if window_size < 1:
            raise ValueError("Window size must be greater than or equal to 1.")

        ema1_indicator = EMAIndicator(close=close_prices, window=window_size)
        ema1 = ema1_indicator.ema_indicator()

        ema2_indicator = EMAIndicator(ema1, window=window_size // 2)
        ema2 = ema2_indicator.ema_indicator()

        hma = (2 * ema1 - ema2).apply(lambda x: x ** 0.5)
        return hma

    @staticmethod
    def calculate_Kama_indicator(close_prices, window_size, sensitivity=2):
        time_period = window_size / sensitivity
        ema1 = close_prices.ewm(span=window_size, min_periods=1, adjust=False).mean()
        ema2 = close_prices.ewm(span=time_period, min_periods=1, adjust=False).mean()

        kama_values = ema1 + (ema2 - ema1) / (1 + sensitivity)
        return kama_values

    @staticmethod
    def calculate_RSI_indicator(close_prices, window_size):
        return RSIIndicator(close=close_prices, window=window_size).rsi()

    @staticmethod
    def calculate_Stochastic_Oscillator_indicator(close_prices, high_prices, low_prices, window_size):
        return StochasticOscillator(
            close=close_prices, high=high_prices, low=low_prices, window=window_size
        ).stoch()

    @staticmethod
    def calculate_MACD_indicator(close_prices):
        return MACD(close=close_prices, window_slow=26, window_fast=12, window_sign=9).macd()

    @staticmethod
    def calculate_CCI_indicator(close_prices, high_prices, low_prices, window_size):
        return CCIIndicator(
            high=high_prices, low=low_prices, close=close_prices, window=window_size
        ).cci()

    @staticmethod
    def calculate_Chaikin_Oscillator(close_prices, high_prices, low_prices, volume_data, window_size):
        return ChaikinMoneyFlowIndicator(
            close=close_prices, high=high_prices, low=low_prices, volume=volume_data, window=window_size
        ).chaikin_money_flow()

    @staticmethod
    def calculate_EMA_indicator(close_prices, window_size):
        return EMAIndicator(close=close_prices, window=window_size).ema_indicator()

    @staticmethod
    def calculate_SMA_indicator(close_prices, window_size):
        return SMAIndicator(close=close_prices, window=window_size).sma_indicator()

    @staticmethod
    def calculate_OBV_indicator(close_prices, volume_data):
        return OnBalanceVolumeIndicator(close=close_prices, volume=volume_data).on_balance_volume()

    @staticmethod
    def calculate_Bollinger_upper_band(close_prices, window_size):
        return BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_hband()

    @staticmethod
    def calculate_Bollinger_lower_band(close_prices, window_size):
        return BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_lband()

    @staticmethod
    def calculate_Bollinger_middle_band(close_prices, window_size):
        return BollingerBands(close=close_prices, window=window_size, window_dev=2).bollinger_mavg()

    @staticmethod
    def calculate_WMA_indicator(close_prices):
        return ta.trend.wma_indicator(close_prices)

    @staticmethod
    def calculate_VMA_indicator(close_prices, volume_data):
        return (close_prices * volume_data).cumsum() / volume_data.cumsum()

    @staticmethod
    def calculate_Chaikin_money_flow(close_prices, high_prices, low_prices, volume_data, window_size):
        return ChaikinMoneyFlowIndicator(close=close_prices, high=high_prices, low=low_prices, volume=volume_data,
                                         window=window_size).chaikin_money_flow()

    @staticmethod
    def determine_signal(rsi, bollinger_upper, bollinger_lower, close_price):
        signal = ''
        if rsi and bollinger_upper and bollinger_lower:
            if rsi > 70 or close_price >= bollinger_upper:
                signal = "Sell"
            elif rsi < 30 or close_price <= bollinger_lower:
                signal = "Buy"
            else:
                signal = "Hold"
        else:
            signal = "Hold"

        return signal
