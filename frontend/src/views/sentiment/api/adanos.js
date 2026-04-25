const BASE = '/adanos';

function getHeaders() {
  return {
    'X-API-Key': import.meta.env.VITE_ADANOS_API_KEY || '',
    'Accept': 'application/json',
  };
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: getHeaders() });
  if (!res.ok) {
    const err = new Error(`API ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const redditAPI = {
  trending:          (days=7, limit=20, type='all') => get(`/reddit/stocks/v1/trending?days=${days}&limit=${limit}&type=${type}`),
  trendingSectors:   (days=7, limit=20)             => get(`/reddit/stocks/v1/trending/sectors?days=${days}&limit=${limit}`),
  trendingCountries: (days=7, limit=15)             => get(`/reddit/stocks/v1/trending/countries?days=${days}&limit=${limit}`),
  stock:             (ticker, days=7)               => get(`/reddit/stocks/v1/stock/${ticker}?days=${days}`),
  explain:           (ticker)                       => get(`/reddit/stocks/v1/stock/${ticker}/explain`),
  compare:           (tickers, days=7)              => get(`/reddit/stocks/v1/compare?tickers=${tickers}&days=${days}`),
  search:            (q, days=7, limit=8)           => get(`/reddit/stocks/v1/search?q=${q}&days=${days}&limit=${limit}`),
  stats:             ()                             => get(`/reddit/stocks/v1/stats`),
};

export const xAPI = {
  trending:          (days=7, limit=20, type='all') => get(`/x/stocks/v1/trending?days=${days}&limit=${limit}&type=${type}`),
  trendingSectors:   (days=7, limit=20)             => get(`/x/stocks/v1/trending/sectors?days=${days}&limit=${limit}`),
  trendingCountries: (days=7, limit=15)             => get(`/x/stocks/v1/trending/countries?days=${days}&limit=${limit}`),
  stock:             (ticker, days=7)               => get(`/x/stocks/v1/stock/${ticker}?days=${days}`),
  compare:           (tickers, days=7)              => get(`/x/stocks/v1/compare?tickers=${tickers}&days=${days}`),
  search:            (q, days=7, limit=8)           => get(`/x/stocks/v1/search?q=${q}&days=${days}&limit=${limit}`),
  stats:             ()                             => get(`/x/stocks/v1/stats`),
};

export const newsAPI = {
  trending:          (days=7, limit=20, type='all') => get(`/news/stocks/v1/trending?days=${days}&limit=${limit}&type=${type}`),
  trendingSectors:   (days=7, limit=20)             => get(`/news/stocks/v1/trending/sectors?days=${days}&limit=${limit}`),
  trendingCountries: (days=7, limit=15)             => get(`/news/stocks/v1/trending/countries?days=${days}&limit=${limit}`),
  stock:             (ticker, days=7)               => get(`/news/stocks/v1/stock/${ticker}?days=${days}`),
  explain:           (ticker)                       => get(`/news/stocks/v1/stock/${ticker}/explain`),
  compare:           (tickers, days=7)              => get(`/news/stocks/v1/compare?tickers=${tickers}&days=${days}`),
  search:            (q, days=7, limit=8)           => get(`/news/stocks/v1/search?q=${q}&days=${days}&limit=${limit}`),
  stats:             ()                             => get(`/news/stocks/v1/stats`),
};
