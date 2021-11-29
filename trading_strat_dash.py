import streamlit as st 
import numpy as np
import pandas as pd
import requests
import config
import tweepy
import matplotlib.pyplot as plt
import yfinance as yf 
import datetime
import ta

auth = tweepy.OAuthHandler(config.TWITTER_API_KEY, config.TWITTER_API_SECRET)
auth.set_access_token(config.TWITTER_ACCESS_TOKEN, config.TWITTER_ACCESS_TOTKEN_SECRET)
api = tweepy.API(auth)

option = st.sidebar.selectbox(
 'Which Dashboard',
  ('Twitter', 'Stocktwits', 'Trading Strategies'))
st.write('You selected:', option)
st.header(option)

if option == 'Twitter':
    for username in config.TWITTER_USERNAMES:

        user = api.get_user(screen_name=username)
        tweets = api.user_timeline(screen_name=username)
        st.subheader(username)
        st.image(user.profile_image_url)
        
        for tweet in tweets:
            if '$' in tweet.text:
                words = tweet.text.split(' ') # split on the spaces to get a list of all the words
                for word in words:
                    if word.startswith('$') and word[1:].isalpha(): # look for words that start with $ and contains letters after
                        symbol = word[1:]
                        st.write(symbol)
                        st.write(tweet.text)
                        st.image(f"https://finviz.com/chart.ashx?t={symbol}")


if option == 'Stocktwits':
    symbol = st.sidebar.text_input("Symbol", value="AAPL", max_chars=5)
    
    r = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json")
    data = r.json()
    
    for message in data['messages']:
        st.image(message['user']['avatar_url'])
        st.write(message['user']['username'])
        st.write(message['created_at'])
        st.write(message['body'])
    
if option == 'Trading Strategies':
    symbol = st.sidebar.text_input("Symbol", value="BTC-USD", max_chars=8)
    datefrom = st.sidebar.date_input("When do you want to start", value=datetime.date(2021,10,1), min_value=datetime.date(2021,9,28))
    strats = st.sidebar.selectbox('Which Strategy', ('Stochastic_RSI_MACD', 'MACD_PSAR_200EMA', 'MACD_PSAR_Stochastic'))
    st.write('You selected:', strats)

    df = yf.download(f'{symbol}', start=f'{datefrom}', interval='30m') 

    if strats == 'Stochastic_RSI_MACD':
        df['%K'] = ta.momentum.stoch(df.High, df.Low, df.Close, window=14, smooth_window=3)
        df['%D'] = df['%K'].rolling(3).mean()
        df['rsi'] = ta.momentum.rsi(df.Close, window=14)
        df['macd']= ta.trend.macd_diff(df.Close) 

        df.dropna(inplace=True)

        
        def gettriggers(df, lags, buy=True):
            df2 = pd.DataFrame()
            for i in range(1, lags+1):
                if buy:
                    mask= (df['%K'].shift(i) < 25) & (df['%D'].shift(i) < 25)
                else: 
                    mask= (df['%K'].shift(i) > 75) & (df['%D'].shift(i) > 75)
                df2 = df2.append(mask,ignore_index=True)
            return df2.sum(axis=0)
        
        df['Buytrigger'] = np.where(gettriggers(df, 4),1,0) 
        df['Selltrigger'] = np.where(gettriggers(df,4, False),1,0)
        df['Buy'] = np.where((df.Buytrigger) & (df["%K"].between(25,75)) & (df["%D"].between(25,75)) & (df.rsi<50) & (df.macd > 0),1,0)
        df['Sell'] = np.where((df.Selltrigger) & (df['%K'].between(25,75)) & (df['%D'].between(25,75)) & (df.rsi>50) & (df.macd > 0),1,0)
       
        Buying_dates, Selling_dates = [], []
        
        for i in range(len(df) - 1): 
            if df.Buy.iloc[i]: # checking if each row has a buy signal
                Buying_dates.append(df.iloc[i +1].name) # if condition is met, you buy at the next timepoint (next row)
                for num,j in enumerate(df.Sell[i:]): # checking from the buying date if the selling conditions are fulfilled.
                    if j: # j is the signal if its 1 or 0 
                        Selling_dates.append(df.iloc[i + num + 1].name) # i + num because num is the number of iterations.
                        break
        
        cutoff =len(Buying_dates) - len(Selling_dates)
        if cutoff:
            Buying_dates = Buying_dates[:-cutoff]
        
        frame = pd.DataFrame({'Buying_dates':Buying_dates, 'Selling_dates': Selling_dates})
        actuals = frame[frame.Buying_dates > frame.Selling_dates.shift(1)]

        def profitcalc():
            Buyprices = df.loc[actuals.Buying_dates].Open
            Sellprices = df.loc[actuals.Selling_dates].Open
            return (Sellprices.values - Buyprices.values)/Buyprices.values
        
        profits = profitcalc()
        mean_prof = profits.mean() 
        st.write("Mean profit per trade: ", mean_prof)
        cumprof = (profits +1).prod()
        st.write("Cumulative profits: ", cumprof)

        fig= plt.figure(figsize=(20,10))
        plt.plot(df.Close, color='k',alpha=0.7)
        plt.scatter(actuals.Buying_dates, df.Open[actuals.Buying_dates], marker='^', color='g', s=500)
        plt.scatter(actuals.Selling_dates, df.Open[actuals.Selling_dates], marker='v', color='r', s=500)
        plt.ylabel(ylabel= 'Price (USD)', fontsize=15)
        plt.xlabel(xlabel='Date', fontsize=15)
        
        st.pyplot(fig)
    
    if strats == 'MACD_PSAR_200EMA':
        df['macd']= ta.trend.macd_diff(df.Close)
        df['200EMA']= ta.trend.ema_indicator(df.Close, window=200)
        df['psarup'] = ta.trend.psar_up(df.High, df.Low, df.Close, step=0.03, max_step=0.2)
        df['psardown'] = ta.trend.psar_down(df.High, df.Low, df.Close, step=0.03, max_step=0.2)

        df.dropna(subset = ['macd', '200EMA'], inplace=True)

        buyconditions = [
                (df['psarup'] < df['Low']), 
                (df['psarup'] > df['Low'])
            ]
        buyvalues = [1, 0]
        df['buysignal'] = np.select(buyconditions,buyvalues)

        sellconditions = [
                (df['psardown'] > df['High']), 
                (df['psardown'] < df['High'])
            ]
        sellvalues = [1, 0]
        df['sellsignal'] = np.select(sellconditions,sellvalues)

        df['Buy'] = np.where((df.buysignal) & (df['200EMA'] < df.Close) & (df.macd > 0),1,0)
        df['Sell'] = np.where((df.sellsignal) & (df['200EMA'] > df.Close) & (df.macd < 0),1,0)
        Buying_dates, Selling_dates = [], []
        for i in range(len(df) - 1): 
            if df.Buy.iloc[i]: # checking if each row has a buy signal
                Buying_dates.append(df.iloc[i +1].name) # if condition is met, you buy at the next timepoint (next row)
                for num,j in enumerate(df.Sell[i:]): # checking from the buying date if the selling conditions are fulfilled.
                    if j: # j is the signal if its 1 or 0 
                        Selling_dates.append(df.iloc[i + num + 1].name) # i + num because num is the number of iterations.
                        break
        cutoff =len(Buying_dates) - len(Selling_dates)
        if cutoff:
            Buying_dates = Buying_dates[:-cutoff] # removing the buying dates if the selling conditions have not been fulfilled.
        frame = pd.DataFrame({'Buying_dates':Buying_dates, 'Selling_dates': Selling_dates})
        actuals = frame[frame.Buying_dates > frame.Selling_dates.shift(1)]
        def profitcalc():
            Buyprices = df.loc[actuals.Buying_dates].Open
            Sellprices = df.loc[actuals.Selling_dates].Open
            return (Sellprices.values - Buyprices.values)/Buyprices.values
        profits = profitcalc()
        mean_prof = profits.mean() 
        st.write("Mean profit per trade: ", mean_prof)
        cum_prof= (profits +1).prod()
        st.write("Cumulative profits: ", cum_prof)

        fig = plt.figure(figsize=(20,10))
        plt.plot(df.Close, color='k',alpha=0.7)
        plt.scatter(actuals.Buying_dates, df.Open[actuals.Buying_dates], marker='^', color='g', s=500)
        plt.scatter(actuals.Selling_dates, df.Open[actuals.Selling_dates], marker='v', color='r', s=500)
        plt.ylabel(ylabel= 'Price (USD)', fontsize=15)
        plt.xlabel(xlabel='Date', fontsize=15)

        st.pyplot(fig)


    if strats == 'MACD_PSAR_Stochastic':
        df['macd']= ta.trend.macd_diff(df.Close)
        df['%K'] = ta.momentum.stoch(df.High, df.Low, df.Close, window=14, smooth_window=3)
        df['%D'] = df['%K'].rolling(3).mean()
        df['psarup'] = ta.trend.psar_up(df.High, df.Low, df.Close, step=0.03, max_step=0.2)
        df['psardown'] = ta.trend.psar_down(df.High, df.Low, df.Close, step=0.03, max_step=0.2)
        df.dropna(subset = ['macd', '%K', '%D'], inplace=True)

        buyconditions = [
                (df['psarup'] < df['Low']), 
                (df['psarup'] > df['Low']) 
            ]
        buyvalues = [1, 0]
        df['buysignal'] = np.select(buyconditions,buyvalues)
        
        sellconditions = [
                (df['psardown'] > df['High']), 
                (df['psardown'] < df['High'])
            ]
        sellvalues = [1, 0]
        df['sellsignal'] = np.select(sellconditions,sellvalues)

        def gettriggers(df, lags, buy=True):
            df2 = pd.DataFrame()
            for i in range(1, lags+1):
                if buy:
                    mask= (df['%K'].shift(i) < 25) & (df['%D'].shift(i) < 25)
                else: 
                    mask= (df['%K'].shift(i) > 75) & (df['%D'].shift(i) > 75)
                df2 = df2.append(mask,ignore_index=True)
            return df2.sum(axis=0)

        df['Buytrigger'] = np.where(gettriggers(df, 3),1,0) # if we get a buy signal (sum is larger than 0) we get a 1, if we dont we get a 0.
        df['Selltrigger'] = np.where(gettriggers(df,3, False),1,0)

        df['Buy'] = np.where((df.buysignal) & (df.Buytrigger) & (df.macd > 0),1,0)
        df['Sell'] = np.where((df.sellsignal) & (df.Selltrigger) & (df.macd < 0),1,0)

        Buying_dates, Selling_dates = [], []
        for i in range(len(df) - 1): 
            if df.Buy.iloc[i]: # checking if each row has a buy signal
                Buying_dates.append(df.iloc[i +1].name) # if condition is met, you buy at the next timepoint (next row)
                for num,j in enumerate(df.Sell[i:]): # checking from the buying date if the selling conditions are fulfilled.
                    if j: # j is the signal if its 1 or 0 
                        Selling_dates.append(df.iloc[i + num + 1].name) # i + num because num is the number of iterations.
                        break

        cutoff =len(Buying_dates) - len(Selling_dates)
        if cutoff:
            Buying_dates = Buying_dates[:-cutoff] # removing the buying dates if the selling conditions have not been fulfilled.

        frame = pd.DataFrame({'Buying_dates':Buying_dates, 'Selling_dates': Selling_dates})
        actuals = frame[frame.Buying_dates > frame.Selling_dates.shift(1)]
        def profitcalc():
            Buyprices = df.loc[actuals.Buying_dates].Open
            Sellprices = df.loc[actuals.Selling_dates].Open
            return (Sellprices.values - Buyprices.values)/Buyprices.values
        profits = profitcalc()
        mean_prof = profits.mean() 
        st.write("Mean profits per trade: ", mean_prof)
        cum_prof = (profits +1).prod()
        st.write("Cumulative profits: ",cum_prof)

        fig = plt.figure(figsize=(20,10))
        plt.plot(df.Close, color='k',alpha=0.7)
        plt.scatter(actuals.Buying_dates, df.Open[actuals.Buying_dates], marker='^', color='g', s=500)
        plt.scatter(actuals.Selling_dates, df.Open[actuals.Selling_dates], marker='v', color='r', s=500)
        plt.ylabel(ylabel= 'Price (USD)', fontsize=15)
        plt.xlabel(xlabel='Date', fontsize=15)
        
        st.pyplot(fig)



